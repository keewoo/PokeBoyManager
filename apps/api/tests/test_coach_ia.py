"""Coach IA d'une partie d'entraînement (lot ``j-coach-ia``, jalon J4, DJ7).

Deuxième visage de l'IA du joueur : au lieu de jouer contre l'enfant, elle l'aide — un conseil sur
demande pendant son tour, et un bilan après la partie. Les trois critères du lot, chacun prouvé par
un test qui **échoue sans** le changement :

1. le conseil propose toujours un coup **légal**, ou **dit** qu'il n'en a pas trouvé — jamais un
   coup inventé (``test_conseil_coup_valide``, ``test_conseil_index_hors_bornes``,
   ``test_conseil_propose_un_coup_legal``) ;
2. le conseil n'est **pas disponible** dans une partie entre deux joueurs humains
   (``test_conseil_refuse_entre_deux_humains``) ;
3. le bilan ne cite que des coups **réellement joués**, vérifié contre le journal
   (``test_bilan_ecarte_les_numeros_inventes``, ``test_bilan_cite_des_coups_reellement_joues``).

Plus les garde-fous (coach désactivable, plafond, clé absente), l'**accès croisé** (B reçoit 404 sur
la partie de A, au service et en HTTP) et le câblage des routes. Le fournisseur IA est un **double
factice** : aucun appel réseau, aucune clé réelle, aucun coût.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import date, datetime

import pytest
from pbm_game.actions import actions_legales
from pbm_game.actions.familles_jeu import familles_jeu
from pbm_game.journal.modele import AUTEUR_SYSTEME
from pbm_game.state import vue
from sqlalchemy import select

import pbm_api.games.coach as coachmod
from pbm_api.ai.base import ExtractionUsage
from pbm_api.ai.errors import ProviderUnreachableError
from pbm_api.config import settings
from pbm_api.games.bot import BOT_USER_ID, creer_partie_entrainement, jouer_coups_bot
from pbm_api.games.catalogue_jeu import construire_catalogue_jeu
from pbm_api.games.coach import (
    CleCoachIndisponible,
    CoachDesactive,
    ConseilHorsEntrainement,
    PartieNonTerminee,
    PlafondConseils,
    bilan_de_partie,
    conseil_pour_joueur,
)
from pbm_api.games.coach_ia import (
    BilanIA,
    ConseilIA,
    MomentBilan,
    construire_lignes_journal,
    proposer_conseil,
    resumer_partie,
)
from pbm_api.games.construction import joueur_id_de
from pbm_api.games.errors import PartieIntrouvable
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
PASSWORD = "correct horse battery staple"
_IDENTITY = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


# --- Fabriques (calquées sur test_adversaire_ia) ------------------------------------------------


async def _user(db) -> User:
    u = User(email=_email("coach"), password_hash="x", **_IDENTITY)
    db.add(u)
    await db.flush()
    return u


async def _set(db) -> Set:
    s = Set(code=f"co-{uuid.uuid4().hex[:8]}", name="Set Coach", series="Série test")
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
    deck = Deck(user_id=user.id, name="Deck Coach")
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


# --- Fournisseur FACTICE (aucun réseau, aucune clé, aucun coût) --------------------------------


class _FauxCoach:
    """Double de test d'un ``AIProvider`` : répond ``ConseilIA`` ou ``BilanIA`` selon le schéma
    demandé, et enregistre les messages reçus. Duck-typing : le coach n'appelle qu'``extract``/
    ``aclose``."""

    def __init__(self, *, index=0, explication="Joue ce coup, il protège ton Pokémon.",
                 bilan_resume="Belle partie, tu as bien défendu ton Actif !", moments=None,
                 erreur: Exception | None = None, delai_s: float = 0.0):
        self.index = index
        self.explication = explication
        self.bilan_resume = bilan_resume
        self._moments = moments or []
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
        if schema is ConseilIA:
            return ConseilIA(index=self.index, explication=self.explication), usage
        if schema is BilanIA:
            moments = [MomentBilan(**m) for m in self._moments]
            return BilanIA(resume=self.bilan_resume, moments=moments), usage
        raise AssertionError(f"schéma inattendu : {schema}")

    async def aclose(self):
        return None


def _brancher_coach(monkeypatch, fournisseur, *, provider_enum=AiProvider.anthropic):
    """Branche le fournisseur factice : une clé « existe » et ``create_provider`` rend le double."""
    async def _cred(db, user):
        return (provider_enum, "sk-faux-jamais-utilisee")

    monkeypatch.setattr(coachmod, "get_default_credential", _cred)
    monkeypatch.setattr(coachmod, "create_provider", lambda enum, key, **kw: fournisseur)


# --- 1) Le conseil : un coup légal, ou rien — jamais un coup inventé ----------------------------


async def _etat_de_decision(db):
    """Un état où le bot a des coups légaux, + sa vue, pour tester le conseil unitairement."""
    from pbm_api.games.service import creer_partie, demarrer_partie
    user = await _user(db)
    deck = await _deck_jouable(db, user)
    game = await creer_partie(
        db, joueur_a=(user.id, deck.id), joueur_b=(BOT_USER_ID, deck.id),
        entrainement=True, bot_niveau="correct",
    )
    await demarrer_partie(db, game)
    etat, _ = await reprendre_partie(db, game)
    catalogue = await construire_catalogue_jeu(db, etat)
    legales = list(actions_legales(etat, BOT_JID, familles=familles_jeu(catalogue)))
    assert legales, "aucun coup légal — le cas de test est vide"
    return vue(etat, BOT_JID), legales


async def test_conseil_coup_valide(db_session):
    """Critère 1 — une réponse conforme propose un coup légal, expliqué."""
    vue_j, legales = await _etat_de_decision(db_session)
    faux = _FauxCoach(index=0, explication="Place ton Pikachu, il est solide.")
    res = await proposer_conseil(faux, vue_j, legales)
    assert res.coup is not None and res.coup in legales
    assert res.index == 0
    assert res.explication == "Place ton Pikachu, il est solide."
    assert res.appel_effectue is True and res.usage is not None


async def test_conseil_index_hors_bornes(db_session):
    """Critère 1 — index hors des coups : pas de coup inventé, on dit qu'on n'a rien trouvé."""
    vue_j, legales = await _etat_de_decision(db_session)
    faux = _FauxCoach(index=9999)
    res = await proposer_conseil(faux, vue_j, legales)
    assert res.coup is None
    assert res.appel_effectue is True and res.usage is not None  # réponse obtenue : usage compté
    assert "pas trouvé" in res.raison


async def test_conseil_echec_fournisseur(db_session):
    """Critère 1 — fournisseur injoignable : pas de conseil, et on le dit (jamais silencieux)."""
    vue_j, legales = await _etat_de_decision(db_session)
    faux = _FauxCoach(erreur=ProviderUnreachableError("coupure"))
    res = await proposer_conseil(faux, vue_j, legales)
    assert res.coup is None and res.appel_effectue is True
    assert res.raison


async def test_conseil_aucun_coup_ne_consomme_rien(db_session):
    """Sans coup jouable, aucun appel IA n'est fait (rien à consommer)."""
    faux = _FauxCoach()
    res = await proposer_conseil(faux, {}, [])
    assert res.coup is None and res.appel_effectue is False
    assert faux.appels == 0


# --- 1 bis) Chemin complet : conseil dans une partie d'entraînement -----------------------------


async def test_conseil_propose_un_coup_legal(db_session, monkeypatch):
    """Critère 1 bout en bout — un conseil dans une partie d'entraînement, budget persisté."""
    faux = _FauxCoach(index=0, explication="Place ton Pokémon le plus solide.")
    _brancher_coach(monkeypatch, faux)
    user = await _user(db_session)
    deck = await _deck_jouable(db_session, user)
    game = await creer_partie_entrainement(
        db_session, user_id=user.id, deck_id=deck.id, niveau="correct", adversaire="bot"
    )
    res = await conseil_pour_joueur(
        db_session, game_id=game.id, user=user, max_conseils=settings.coach_max_conseils
    )
    assert res.conseil.coup is not None, "aucun coup conseillé à la mise en place"
    assert res.conseil.explication == "Place ton Pokémon le plus solide."
    assert res.conseils_utilises == 1
    assert res.conseils_restants == settings.coach_max_conseils - 1
    refreshed = await db_session.get(Game, game.id)
    assert refreshed.conseils_utilises == 1  # budget écrit sur la partie (survit à un F5)


# --- 2) Pas de conseil dans une partie entre deux humains ---------------------------------------


async def test_conseil_refuse_entre_deux_humains(db_session, monkeypatch):
    """Critère 2 — une partie entre deux joueurs humains refuse le conseil, avant tout appel IA."""
    from pbm_api.games.service import creer_partie, demarrer_partie
    faux = _FauxCoach()
    _brancher_coach(monkeypatch, faux)
    user_a = await _user(db_session)
    user_b = await _user(db_session)
    deck_a = await _deck_jouable(db_session, user_a)
    deck_b = await _deck_jouable(db_session, user_b)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )
    await demarrer_partie(db_session, game)
    with pytest.raises(ConseilHorsEntrainement):
        await conseil_pour_joueur(db_session, game_id=game.id, user=user_a, max_conseils=3)
    assert faux.appels == 0, "l'IA a été appelée alors que le conseil est interdit ici"


# --- Garde-fous du conseil ----------------------------------------------------------------------


async def test_conseil_acces_croise_404(db_session, monkeypatch):
    """Accès croisé — B ne reçoit aucun conseil sur la partie de A (404, pas de fuite)."""
    faux = _FauxCoach()
    _brancher_coach(monkeypatch, faux)
    user_a = await _user(db_session)
    user_b = await _user(db_session)
    deck_a = await _deck_jouable(db_session, user_a)
    game = await creer_partie_entrainement(
        db_session, user_id=user_a.id, deck_id=deck_a.id, niveau="correct", adversaire="bot"
    )
    with pytest.raises(PartieIntrouvable):
        await conseil_pour_joueur(db_session, game_id=game.id, user=user_b, max_conseils=3)


async def test_conseil_plafond(db_session, monkeypatch):
    """Le plafond de conseils par partie est respecté (refus nommé)."""
    faux = _FauxCoach()
    _brancher_coach(monkeypatch, faux)
    user = await _user(db_session)
    deck = await _deck_jouable(db_session, user)
    game = await creer_partie_entrainement(
        db_session, user_id=user.id, deck_id=deck.id, niveau="correct", adversaire="bot"
    )
    g = await db_session.get(Game, game.id)
    g.conseils_utilises = 3
    await db_session.flush()
    with pytest.raises(PlafondConseils):
        await conseil_pour_joueur(db_session, game_id=game.id, user=user, max_conseils=3)


async def test_conseil_sans_cle(db_session, monkeypatch):
    """Sans clé IA, le conseil est refusé en expliquant comment en ajouter une."""
    async def _none(db, user):
        return None

    monkeypatch.setattr(coachmod, "get_default_credential", _none)
    user = await _user(db_session)
    deck = await _deck_jouable(db_session, user)
    game = await creer_partie_entrainement(
        db_session, user_id=user.id, deck_id=deck.id, niveau="correct", adversaire="bot"
    )
    with pytest.raises(CleCoachIndisponible):
        await conseil_pour_joueur(db_session, game_id=game.id, user=user, max_conseils=3)


async def test_conseil_coach_desactive(db_session, monkeypatch):
    """Le joueur a désactivé le coach : le conseil est refusé en le disant."""
    faux = _FauxCoach()
    _brancher_coach(monkeypatch, faux)
    user = await _user(db_session)
    deck = await _deck_jouable(db_session, user)
    game = await creer_partie_entrainement(
        db_session, user_id=user.id, deck_id=deck.id, niveau="correct", adversaire="bot"
    )
    user.coach_actif = False
    await db_session.flush()
    with pytest.raises(CoachDesactive):
        await conseil_pour_joueur(db_session, game_id=game.id, user=user, max_conseils=3)


# --- 3) Le bilan ne cite que des coups réellement joués -----------------------------------------


async def test_lignes_journal_ecarte_les_coups_systeme():
    """Les coups système ne sont pas des « coups joués » : écartés du journal présenté au bilan."""
    entrees = [
        (0, AUTEUR_SYSTEME, "mise_en_place_initiale"),
        (1, "j:aaaa", "declarer_attaque"),
        (2, "j:bbbb", "poser"),
    ]
    lignes, numeros = construire_lignes_journal(entrees, "j:aaaa")
    assert numeros == {1, 2}
    assert any("Toi a attaqué" in ligne for ligne in lignes)
    assert any("Ton adversaire a posé" in ligne for ligne in lignes)
    assert all("mise_en_place_initiale" not in ligne for ligne in lignes)


async def test_bilan_ecarte_les_numeros_inventes():
    """Critère 3 (unitaire) — un moment cité hors du journal est écarté (anti-hallucination)."""
    faux = _FauxCoach(
        bilan_resume="Résumé de la partie.",
        moments=[{"numero": 2, "commentaire": "Bon choix."},
                 {"numero": 777, "commentaire": "Ce coup n'a jamais été joué."}],
    )
    res = await resumer_partie(faux, ["2. Toi a attaqué."], {2}, resultat="tu as gagné (ko)")
    assert res.resume == "Résumé de la partie."
    assert [m.numero for m in res.moments] == [2], "un numéro inventé a survécu"


async def test_bilan_cite_des_coups_reellement_joues(db_session, monkeypatch):
    """Critère 3 (bout en bout) — tout numéro cité par le bilan existe dans le journal."""
    user = await _user(db_session)
    deck = await _deck_jouable(db_session, user)
    game = await creer_partie_entrainement(
        db_session, user_id=user.id, deck_id=deck.id, niveau="correct", adversaire="bot"
    )
    human_jid = joueur_id_de(user.id)
    # Jouer jusqu'à la fin (sans coach pendant la partie).
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
        await appliquer_action(
            db_session, game_id=game.id, user_id=user.id,
            type=action.type, params=action.params, numero_attendu=game.current_numero,
        )

    game = await db_session.get(Game, game.id)
    assert game.status == "terminee", f"la partie ne s'est pas terminée ({game.status})"
    rows = (
        await db_session.execute(select(GameEvent).where(GameEvent.game_id == game.id))
    ).scalars().all()
    numeros_reels = {r.numero for r in rows if r.auteur != AUTEUR_SYSTEME}
    assert numeros_reels, "aucun coup joué — le test ne prouve rien"
    un_vrai = min(numeros_reels)

    faux = _FauxCoach(
        bilan_resume="Tu as bien tenu ton Actif.",
        moments=[{"numero": un_vrai, "commentaire": "Beau coup."},
                 {"numero": 999999, "commentaire": "Coup inventé, jamais joué."}],
    )
    _brancher_coach(monkeypatch, faux)
    res = await bilan_de_partie(db_session, game_id=game.id, user=user)
    assert res.resume == "Tu as bien tenu ton Actif."
    cites = [m["numero"] for m in res.moments]
    assert un_vrai in cites, "le coup réel cité a disparu"
    assert 999999 not in cites, "un numéro inventé a été retenu"
    assert all(n in numeros_reels for n in cites), "un moment cite un coup absent du journal"
    assert res.moments[0]["etiquette"], "le moment n'a pas d'étiquette lisible"


async def test_bilan_partie_non_terminee(db_session, monkeypatch):
    """Pas de bilan tant que la partie n'est pas finie (refus nommé)."""
    faux = _FauxCoach()
    _brancher_coach(monkeypatch, faux)
    user = await _user(db_session)
    deck = await _deck_jouable(db_session, user)
    game = await creer_partie_entrainement(
        db_session, user_id=user.id, deck_id=deck.id, niveau="correct", adversaire="bot"
    )
    with pytest.raises(PartieNonTerminee):
        await bilan_de_partie(db_session, game_id=game.id, user=user)
    assert faux.appels == 0


async def test_bilan_acces_croise_404(db_session, monkeypatch):
    """Accès croisé — B ne reçoit aucun bilan sur la partie de A (404, pas de fuite)."""
    faux = _FauxCoach()
    _brancher_coach(monkeypatch, faux)
    user_a = await _user(db_session)
    user_b = await _user(db_session)
    deck_a = await _deck_jouable(db_session, user_a)
    game = await creer_partie_entrainement(
        db_session, user_id=user_a.id, deck_id=deck_a.id, niveau="correct", adversaire="bot"
    )
    with pytest.raises(PartieIntrouvable):
        await bilan_de_partie(db_session, game_id=game.id, user=user_b)


# --- Routes HTTP : câblage + accès croisé (404) -------------------------------------------------


async def _register_verify_login(client, email: str) -> uuid.UUID:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "last_name": "Dresseur",
              "birth_date": "2000-01-01", "accept_terms": True},
    )
    assert response.status_code == 202, response.text
    sent = client.email_sender.sent  # type: ignore[attr-defined]
    match = re.search(r"token=(\S+)", sent[-1]["body"])
    assert match
    await client.post("/auth/verify-email", json={"token": match.group(1)})
    login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return uuid.UUID(login.json()["id"])


async def _accorder_acces_jeu(db, user_id: uuid.UUID) -> None:
    user = await db.get(User, user_id)
    user.game_access = True
    await db.flush()


async def test_route_conseil_happy_et_acces_croise(api_client, db_session, monkeypatch):
    """La route rend un conseil au participant (200), et répond 404 à un non-participant."""
    faux = _FauxCoach(index=0, explication="Place ton Pokémon le plus solide.")
    _brancher_coach(monkeypatch, faux)

    id_a = await _register_verify_login(api_client, _email("coacha"))
    await _accorder_acces_jeu(db_session, id_a)
    user_a = await db_session.get(User, id_a)
    deck_a = await _deck_jouable(db_session, user_a)
    game = await creer_partie_entrainement(
        db_session, user_id=id_a, deck_id=deck_a.id, niveau="correct", adversaire="bot"
    )

    # A (session courante) : un conseil légal.
    reponse = await api_client.post(f"/games/{game.id}/conseil")
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["coup"] is not None
    assert corps["explication"] == "Place ton Pokémon le plus solide."
    assert corps["conseils_restants"] == settings.coach_max_conseils - 1

    # B devient la session courante (register + login) → non-participant → 404 (pas de fuite).
    await _register_verify_login(api_client, _email("coachb"))
    reponse_b = await api_client.post(f"/games/{game.id}/conseil")
    assert reponse_b.status_code == 404, reponse_b.text


async def test_route_bilan_acces_croise(api_client, db_session, monkeypatch):
    """La route du bilan répond 404 à un non-participant (pas de fuite)."""
    faux = _FauxCoach()
    _brancher_coach(monkeypatch, faux)

    id_a = await _register_verify_login(api_client, _email("bilana"))
    await _accorder_acces_jeu(db_session, id_a)
    user_a = await db_session.get(User, id_a)
    deck_a = await _deck_jouable(db_session, user_a)
    game = await creer_partie_entrainement(
        db_session, user_id=id_a, deck_id=deck_a.id, niveau="correct", adversaire="bot"
    )

    # B devient la session courante, puis demande le bilan de la partie de A.
    await _register_verify_login(api_client, _email("bilanb"))
    reponse = await api_client.get(f"/games/{game.id}/bilan")
    assert reponse.status_code == 404, reponse.text
