"""Adversaire IA d'une partie d'entraînement (lot ``j-adversaire-ia``, jalon J4, DJ7).

Les quatre critères du lot, chacun prouvé par un test qui **échoue sans** le changement :

1. une partie d'entraînement se joue jusqu'au bout contre « mon IA » (fournisseur **factice**),
   chaque coup de l'IA est légal (rejoué par le moteur) et **expliqué** (commentaire au journal) ;
2. **aucune information cachée** n'est envoyée à l'IA — le message réellement transmis au
   fournisseur ne contient aucun ``instance_id`` de la main ou de la pioche adverse ;
3. un **échec** de l'IA (exception, réponse hors des coups, délai, plafond) fait jouer le **bot** et
   s'affiche (note de repli), jamais un repli silencieux ni un coup inventé ;
4. **sans clé IA**, « mon IA » est refusé en expliquant comment en ajouter une — et le bot joue.

Le fournisseur factice est injecté en surchargeant ``create_provider``/``get_default_credential``
dans l'espace de noms du module ``bot`` : aucun appel réseau, aucune clé réelle, aucun coût.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import date, datetime

import pytest
from pbm_game.actions import actions_legales
from pbm_game.actions.familles_jeu import familles_jeu
from pbm_game.state import vue
from sqlalchemy import select

import pbm_api.games.bot as botmod
from pbm_api.ai.base import ExtractionUsage
from pbm_api.ai.errors import ProviderUnreachableError
from pbm_api.games.adversaire_ia import (
    DecisionIA,
    choisir_coup_ia,
    construire_message,
)
from pbm_api.games.bot import (
    BOT_USER_ID,
    CleIAIndisponible,
    creer_partie_entrainement,
    jouer_coups_bot,
)
from pbm_api.games.catalogue_jeu import construire_catalogue_jeu
from pbm_api.games.construction import joueur_id_de
from pbm_api.games.service import appliquer_action, reprendre_partie
from pbm_api.models import (
    AiProvider,
    Card,
    CollectionItem,
    Deck,
    DeckCard,
    Game,
    GameEvent,
    Set,
    User,
)

BOT_JID = joueur_id_de(BOT_USER_ID)
_IDENTITY = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}


# --- Fabriques (calquées sur test_games_mode_solo) ----------------------------------------------


async def _user(db) -> User:
    u = User(email=f"ia-{uuid.uuid4().hex[:10]}@example.com", password_hash="x", **_IDENTITY)
    db.add(u)
    await db.flush()
    return u


async def _set(db) -> Set:
    s = Set(code=f"ia-{uuid.uuid4().hex[:8]}", name="Set IA", series="Série test")
    db.add(s)
    await db.flush()
    return s


async def _pikachu(db, set_row) -> Card:
    c = Card(
        set_id=set_row.id, number=str(uuid.uuid4().int % 100000), name="Pikachu",
        supertype="Pokémon", energy_type="electrique", element_type="electrique", hp=60,
        stage="Base", retreat_cost=1, prize_marker="ordinaire",
        attacks=[{"name": "Charge", "cost": ["electrique"], "damage": "60", "effect": ""}],
    )
    db.add(c)
    await db.flush()
    return c


async def _energie(db, set_row) -> Card:
    c = Card(
        set_id=set_row.id, number=str(uuid.uuid4().int % 100000), name="Énergie Électrique",
        supertype="Énergie", energy_type="Normal", element_type="electrique",
    )
    db.add(c)
    await db.flush()
    return c


async def _deck(db, user, cartes) -> Deck:
    """Un deck du joueur, dont les Pokémon sont **possédés** en collection (sinon la création d'une
    partie refuse le deck pour possession insuffisante — `verifier_lancable`)."""
    deck = Deck(user_id=user.id, name="Deck IA")
    db.add(deck)
    await db.flush()
    for card, qty in cartes:
        db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=qty))
        if card.supertype == "Pokémon":
            for _ in range(qty):
                db.add(CollectionItem(user_id=user.id, card_id=card.id))
    await db.flush()
    return deck


async def _deck_jouable(db, user) -> Deck:
    s = await _set(db)
    pika = await _pikachu(db, s)
    energie = await _energie(db, s)
    return await _deck(db, user, [(pika, 6), (energie, 14)])


def _choisir_humain(etat, jid, catalogue):
    """Stratégie humaine minimale (promouvoir, placer, attaquer, charger, sinon passer)."""
    legales = actions_legales(etat, jid, familles=familles_jeu(catalogue))
    par_type: dict[str, list] = {}
    for coup in legales:
        par_type.setdefault(coup.action.type, []).append(coup)
    for t in ("promouvoir", "placer_mise_en_place", "declarer_attaque"):
        if t in par_type:
            return par_type[t][0].action
    joueur = next(j for j in etat.joueurs if j.id == jid)
    if "attacher_energie" in par_type and joueur.actif is not None and not joueur.actif.energies:
        actif_id = joueur.actif.cartes[0].instance_id
        sur_actif = [c for c in par_type["attacher_energie"]
                     if c.action.params.get("cible") == actif_id]
        if sur_actif:
            return sur_actif[0].action
    if "avancer_phase" in par_type:
        return par_type["avancer_phase"][0].action
    return legales[0].action if legales else None


# --- Fournisseur FACTICE (aucun réseau, aucune clé, aucun coût) ----------------------------------


class _FauxFournisseur:
    """Double de test d'un ``AIProvider`` : il répond selon un scénario fixé, et **enregistre** les
    messages reçus (pour prouver qu'aucune information cachée n'y figure). Duck-typing : la décision
    n'appelle que ``extract`` et ``aclose``."""

    def __init__(self, *, index=0, explication="Je joue ce coup pour protéger mon Pokémon.",
                 erreur: Exception | None = None, delai_s: float = 0.0):
        self.index = index
        self.explication = explication
        self.erreur = erreur
        self.delai_s = delai_s
        self.messages: list[str] = []
        self.appels = 0

    async def extract(self, images, schema, prompt, *, model=None):
        self.appels += 1
        self.messages.append(prompt)
        if self.delai_s:
            await asyncio.sleep(self.delai_s)
        if self.erreur is not None:
            raise self.erreur
        usage = ExtractionUsage(
            provider=AiProvider.anthropic, model="faux", input_tokens=10, output_tokens=5
        )
        return DecisionIA(index=self.index, explication=self.explication), usage

    async def aclose(self):
        return None


def _brancher_ia(monkeypatch, fournisseur, *, provider_enum=AiProvider.anthropic):
    """Branche le fournisseur factice : une clé « existe » et ``create_provider`` rend le double."""
    async def _cred(db, user):
        return (provider_enum, "sk-faux-jamais-utilisee")

    monkeypatch.setattr(botmod, "get_default_credential", _cred)
    monkeypatch.setattr(botmod, "create_provider", lambda enum, key, **kw: fournisseur)


# --- 1) Partie complète contre « mon IA », chaque coup légal et expliqué ------------------------


async def test_partie_contre_mon_ia_jusqua_la_fin_chaque_coup_explique(db_session, monkeypatch):
    """Critère 1 — une partie se joue de bout en bout contre l'IA ; ses coups sont expliqués."""
    faux = _FauxFournisseur()
    _brancher_ia(monkeypatch, faux)

    user = await _user(db_session)
    deck = await _deck_jouable(db_session, user)
    game = await creer_partie_entrainement(
        db_session, user_id=user.id, deck_id=deck.id, niveau="correct", adversaire="ia"
    )
    assert game.entrainement is True
    human_jid = joueur_id_de(user.id)

    commentaires: list[str] = []
    for _ in range(2000):
        game = await db_session.get(Game, game.id)
        if game.status != "en_cours":
            break
        etat, _rng = await reprendre_partie(db_session, game)
        catalogue = await construire_catalogue_jeu(db_session, etat)
        if etat.mise_en_place is not None:
            idx = next(i for i, j in enumerate(etat.joueurs) if j.id == human_jid)
            if etat.mise_en_place.placements[idx] is not None:
                await jouer_coups_bot(db_session, game.id)
                continue
            acteur = human_jid
        else:
            acteur = etat.tour.joueur_actif
        if acteur != human_jid:
            await jouer_coups_bot(db_session, game.id)
            continue
        action = _choisir_humain(etat, human_jid, catalogue)
        assert action is not None, f"aucun coup humain (phase {etat.tour.phase})"
        resultat = await appliquer_action(
            db_session, game_id=game.id, user_id=user.id,
            type=action.type, params=action.params, numero_attendu=game.current_numero,
        )
        commentaires += [c["texte"] for c in resultat.commentaires]

    game = await db_session.get(Game, game.id)
    assert game.status == "terminee", f"la partie ne s'est pas terminée (statut {game.status})"
    assert game.raison_fin not in (None, "abandon"), f"fin non méritée : {game.raison_fin}"

    # L'IA a été consultée et a expliqué au moins un coup, persisté au journal.
    assert faux.appels > 0, "l'IA n'a jamais été consultée — le test ne prouve rien"
    assert commentaires, "aucune explication renvoyée au client"
    assert any(faux.explication in c for c in commentaires), "l'explication de l'IA ne remonte pas"
    entrees = (
        await db_session.execute(select(GameEvent).where(GameEvent.game_id == game.id))
    ).scalars().all()
    expliques = [e for e in entrees if e.commentaire and e.auteur == BOT_JID]
    assert expliques, "aucun coup de l'IA n'a laissé d'explication au journal (trace J4)"
    # Compteur de budget réel et jetons consommés (base du coût estimé affiché).
    assert game.ia_appels == faux.appels
    assert game.ia_tokens == faux.appels * 15


# --- 2) Aucune information cachée dans le message envoyé à l'IA ----------------------------------


async def test_message_ne_fuite_aucune_information_cachee(db_session, monkeypatch):
    """Critère 2 — le message bâti pour l'IA ne porte aucun id de la main/pioche adverse.

    La vérification est **cohérente dans le temps** : on reconstruit un état de milieu de partie,
    on y relève ce que l'humain cache **à cet instant précis** (sa main, sa pioche), puis on bâtit
    le message exactement comme en production (``construire_message(vue(etat, BOT), legales)``) et
    on vérifie qu'aucun de ces identifiants n'y figure. (Un identifiant jadis en main mais depuis
    **joué** est devenu public — d'où la photographie instantanée, jamais un cumul dans le temps.)
    """
    faux = _FauxFournisseur()
    _brancher_ia(monkeypatch, faux)

    user = await _user(db_session)
    deck = await _deck_jouable(db_session, user)
    game = await creer_partie_entrainement(
        db_session, user_id=user.id, deck_id=deck.id, niveau="correct", adversaire="ia"
    )
    human_jid = joueur_id_de(user.id)

    # Quelques coups pour atteindre un milieu de partie riche (cartes en main, en pioche, en jeu).
    for _ in range(12):
        game = await db_session.get(Game, game.id)
        if game.status != "en_cours":
            break
        etat, _rng = await reprendre_partie(db_session, game)
        catalogue = await construire_catalogue_jeu(db_session, etat)
        if etat.mise_en_place is not None:
            idx = next(i for i, j in enumerate(etat.joueurs) if j.id == human_jid)
            if etat.mise_en_place.placements[idx] is not None:
                await jouer_coups_bot(db_session, game.id)
                continue
            acteur = human_jid
        else:
            acteur = etat.tour.joueur_actif
        if acteur != human_jid:
            await jouer_coups_bot(db_session, game.id)
            continue
        action = _choisir_humain(etat, human_jid, catalogue)
        if action is None:
            break
        await appliquer_action(
            db_session, game_id=game.id, user_id=user.id,
            type=action.type, params=action.params, numero_attendu=game.current_numero,
        )

    # Photographie instantanée : l'état courant, ce que l'humain cache MAINTENANT, et le message
    # que l'IA (siège bot) recevrait pour cet état exact.
    game = await db_session.get(Game, game.id)
    etat, _ = await reprendre_partie(db_session, game)
    humain = next(j for j in etat.joueurs if j.id == human_jid)
    ids_caches = {c.instance_id for c in list(humain.main) + list(humain.pioche)}
    assert ids_caches, "aucun identifiant caché relevé — le test ne prouve rien"
    catalogue = await construire_catalogue_jeu(db_session, etat)
    legales = actions_legales(etat, BOT_JID, familles=familles_jeu(catalogue))
    message = construire_message(vue(etat, BOT_JID), [c for c in legales])
    # On cherche l'identifiant **comme jeton JSON entre guillemets** (``"…:d5"``), pas en
    # sous-chaîne : sinon ``:d5`` matcherait ``:d50`` (même préfixe joueur, indices 5 vs 50).
    for identifiant in ids_caches:
        assert f'"{identifiant}"' not in message, (
            f"fuite : l'identifiant caché {identifiant} figure dans le message envoyé à l'IA"
        )
    # Et l'IA a bien été exercée sur le vrai chemin durant la partie (messages réellement transmis).
    assert faux.messages, "l'IA n'a reçu aucun message — le chemin réel n'a pas servi"


# --- 2 bis) construire_message : unitaire, vue projetée seulement -------------------------------


async def test_construire_message_ne_reprend_que_la_vue(db_session, monkeypatch):
    """Le message est bâti depuis la seule ``vue`` projetée (déjà sans main adverse)."""
    faux = _FauxFournisseur()
    _brancher_ia(monkeypatch, faux)
    user = await _user(db_session)
    deck = await _deck_jouable(db_session, user)
    game = await creer_partie_entrainement(
        db_session, user_id=user.id, deck_id=deck.id, niveau="correct", adversaire="ia"
    )
    etat, _ = await reprendre_partie(db_session, game)
    catalogue = await construire_catalogue_jeu(db_session, etat)
    legales = actions_legales(etat, BOT_JID, familles=familles_jeu(catalogue))
    message = construire_message(vue(etat, BOT_JID), [c for c in legales])
    # L'ordre de la pioche n'est exposé pour personne : la vue n'a que ``pioche_nombre``.
    assert '"pioche":' not in message
    assert '"pioche_nombre"' in message
    assert "coups autorisés" in message


# --- 3) Échec de l'IA → le bot joue, et ça s'affiche (jamais silencieux) -------------------------


async def _etat_de_decision(db_session):
    """Un état où le bot a des coups légaux, + sa vue, pour tester le décideur unitairement."""
    user = await _user(db_session)
    deck = await _deck_jouable(db_session, user)
    # Partie bot pur : jouer_coups_bot place le camp ; on reprend un état avec coups légaux pour le
    # bot pendant la mise en place (placer son Actif).
    from pbm_api.games.service import creer_partie, demarrer_partie
    game = await creer_partie(
        db_session, joueur_a=(user.id, deck.id), joueur_b=(BOT_USER_ID, deck.id),
        entrainement=True, bot_niveau="correct",
    )
    await demarrer_partie(db_session, game)
    etat, _ = await reprendre_partie(db_session, game)
    catalogue = await construire_catalogue_jeu(db_session, etat)
    legales = list(actions_legales(etat, BOT_JID, familles=familles_jeu(catalogue)))
    assert legales, "aucun coup légal pour le bot — le cas de test est vide"
    return vue(etat, BOT_JID), legales


def _repli_premier(vue_j, legales, alea):
    return legales[0]


async def test_repli_sur_exception_du_fournisseur(db_session):
    """Critère 3a — fournisseur injoignable : le bot joue, et la raison est dite."""
    vue_j, legales = await _etat_de_decision(db_session)
    faux = _FauxFournisseur(erreur=ProviderUnreachableError("coupure"))
    res = await choisir_coup_ia(faux, vue_j, legales, repli_bot=_repli_premier,
                                alea=random.Random(0))
    assert res.coup is not None and res.bascule_bot is True
    assert res.appel_effectue is True
    assert "le bot a joué à sa place" in res.commentaire_journal()


async def test_repli_sur_index_hors_bornes(db_session):
    """Critère 3b — réponse hors des coups autorisés : repli bot, usage réel enregistré."""
    vue_j, legales = await _etat_de_decision(db_session)
    faux = _FauxFournisseur(index=9999)
    res = await choisir_coup_ia(faux, vue_j, legales, repli_bot=_repli_premier,
                                alea=random.Random(0))
    assert res.bascule_bot is True and res.coup is not None
    assert res.usage is not None, "une réponse a été obtenue : son usage doit être compté"
    assert "hors des coups autorisés" in res.commentaire_journal()


async def test_repli_sur_delai_depasse(db_session):
    """Critère 3c — l'IA met trop de temps : le bot joue, on ne laisse jamais l'écran muet."""
    vue_j, legales = await _etat_de_decision(db_session)
    faux = _FauxFournisseur(delai_s=1.0)
    res = await choisir_coup_ia(faux, vue_j, legales, repli_bot=_repli_premier,
                                alea=random.Random(0), delai_max_s=0.01)
    assert res.bascule_bot is True and res.coup is not None
    assert "délai dépassé" in res.commentaire_journal()


async def test_coup_valide_est_joue_et_explique(db_session):
    """L'autre face de 3 — une réponse conforme joue le coup choisi et porte l'explication."""
    vue_j, legales = await _etat_de_decision(db_session)
    faux = _FauxFournisseur(index=0, explication="Je place mon Pikachu, il est solide.")
    res = await choisir_coup_ia(faux, vue_j, legales, repli_bot=_repli_premier,
                                alea=random.Random(0))
    assert res.bascule_bot is False
    assert res.coup is legales[0]
    assert res.commentaire_journal() == "Je place mon Pikachu, il est solide."


async def test_plafond_appels_arrete_lia_et_le_dit(db_session, monkeypatch):
    """Critère 3d — le plafond d'appels arrête l'IA proprement, et le journal le dit une fois."""
    monkeypatch.setattr(botmod, "MAX_APPELS_PAR_PARTIE", 1)
    faux = _FauxFournisseur()
    _brancher_ia(monkeypatch, faux)
    user = await _user(db_session)
    deck = await _deck_jouable(db_session, user)
    game = await creer_partie_entrainement(
        db_session, user_id=user.id, deck_id=deck.id, niveau="correct", adversaire="ia"
    )
    human_jid = joueur_id_de(user.id)

    vus: list[str] = []
    for _ in range(2000):
        game = await db_session.get(Game, game.id)
        if game.status != "en_cours":
            break
        etat, _rng = await reprendre_partie(db_session, game)
        catalogue = await construire_catalogue_jeu(db_session, etat)
        if etat.mise_en_place is not None:
            idx = next(i for i, j in enumerate(etat.joueurs) if j.id == human_jid)
            if etat.mise_en_place.placements[idx] is not None:
                await jouer_coups_bot(db_session, game.id)
                continue
            acteur = human_jid
        else:
            acteur = etat.tour.joueur_actif
        if acteur != human_jid:
            await jouer_coups_bot(db_session, game.id)
            continue
        action = _choisir_humain(etat, human_jid, catalogue)
        if action is None:
            break
        resultat = await appliquer_action(
            db_session, game_id=game.id, user_id=user.id,
            type=action.type, params=action.params, numero_attendu=game.current_numero,
        )
        vus += [c["texte"] for c in resultat.commentaires]

    game = await db_session.get(Game, game.id)
    # Le plafond a été respecté : jamais plus d'appels que la limite.
    assert game.ia_appels <= 1
    # Et il a été annoncé (pas de dépassement muet de la clé du joueur).
    assert any("plafond d'appels atteint" in c for c in vus), "le plafond n'a pas été annoncé"


# --- 4) Sans clé IA : refus explicite, le bot reste jouable --------------------------------------


async def test_sans_cle_ia_refuse_en_expliquant(db_session):
    """Critère 4 — « mon IA » sans clé est refusé en disant comment en ajouter une."""
    user = await _user(db_session)  # aucun AiCredential : get_default_credential renverra None
    deck = await _deck_jouable(db_session, user)
    with pytest.raises(CleIAIndisponible) as exc:
        await creer_partie_entrainement(
            db_session, user_id=user.id, deck_id=deck.id, niveau="correct", adversaire="ia"
        )
    message = str(exc.value)
    assert "clé" in message and "bot" in message  # explique, et renvoie vers le bot en attendant


async def test_sans_cle_le_bot_reste_jouable(db_session):
    """Critère 4 — sans clé, la partie contre le bot se crée normalement."""
    user = await _user(db_session)
    deck = await _deck_jouable(db_session, user)
    game = await creer_partie_entrainement(
        db_session, user_id=user.id, deck_id=deck.id, niveau="correct", adversaire="bot"
    )
    assert game.entrainement is True


# --- Isolation : l'IA d'un joueur joue avec SA clé, jamais celle d'un autre ----------------------


async def test_lia_utilise_la_cle_de_lhumain_de_la_partie(db_session, monkeypatch):
    """L'IA d'une partie est résolue sur l'humain de CETTE partie (jamais un autre joueur)."""
    vus: list[uuid.UUID] = []

    async def _cred(db, user):
        vus.append(user.id)
        return (AiProvider.anthropic, "sk-faux")

    monkeypatch.setattr(botmod, "get_default_credential", _cred)
    monkeypatch.setattr(botmod, "create_provider", lambda enum, key, **kw: _FauxFournisseur())

    user_a = await _user(db_session)
    user_b = await _user(db_session)
    deck_a = await _deck_jouable(db_session, user_a)
    await _deck_jouable(db_session, user_b)
    game_a = await creer_partie_entrainement(
        db_session, user_id=user_a.id, deck_id=deck_a.id, niveau="correct", adversaire="ia"
    )
    human_a = joueur_id_de(user_a.id)

    # Un coup de A pour déclencher le tour de son IA.
    for _ in range(30):
        game_a = await db_session.get(Game, game_a.id)
        if game_a.status != "en_cours":
            break
        etat, _ = await reprendre_partie(db_session, game_a)
        catalogue = await construire_catalogue_jeu(db_session, etat)
        if etat.mise_en_place is not None:
            idx = next(i for i, j in enumerate(etat.joueurs) if j.id == human_a)
            if etat.mise_en_place.placements[idx] is not None:
                await jouer_coups_bot(db_session, game_a.id)
                continue
            acteur = human_a
        else:
            acteur = etat.tour.joueur_actif
        if acteur != human_a:
            await jouer_coups_bot(db_session, game_a.id)
            continue
        action = _choisir_humain(etat, human_a, catalogue)
        if action is None:
            break
        await appliquer_action(
            db_session, game_id=game_a.id, user_id=user_a.id,
            type=action.type, params=action.params, numero_attendu=game_a.current_numero,
        )
        if vus:
            break

    assert vus, "l'IA n'a jamais résolu de clé — le test ne prouve rien"
    assert all(uid == user_a.id for uid in vus), "l'IA a résolu la clé d'un autre joueur que A"
    assert user_b.id not in vus
