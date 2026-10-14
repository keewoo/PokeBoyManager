"""Emotes prédéfinies d'une partie (lot `j-echanges-emotes`, jalon J4, décision **DJ10**).

Les trois critères d'acceptation du lot, chacun prouvé ici :

1. **aucune saisie de texte libre** — le serveur n'accepte qu'un **code** d'une liste fermée, et
   aucune route ne reçoit de message de joueur à joueur (`test_code_hors_catalogue_refuse`,
   `test_aucun_texte_ne_traverse`). Le volet écran est gardé par `test_jeu_emotes_parite.py` et
   `apps/web/src/__tests__/emote-bar.test.tsx` ;
2. **couper les emotes est immédiat et mémorisé** — le réglage persiste côté compte, et la
   diffusion le **relit à chaque emote**, donc sans reconnexion ni rafraîchissement
   (`test_coupure_immediate_sans_reconnexion`, `test_reglage_memorise`) ;
3. **le débit est limité et testé** — la règle est pure, donc testée sur des instants décrits et
   non sur une suite qui dort (`test_debit_*`), et le refus **dit** le délai à attendre.

Et le quatrième point de la mission, « ne rien persister au-delà de la partie » :
`test_emote_nentre_pas_dans_le_journal` et `test_limiteur_oublie_la_partie`.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime

import pytest

from pbm_api.games import emotes as regles
from pbm_api.games.emotes_service import (
    LimiteurEmotes,
    charger_reglages,
    comptes_ayant_coupe,
    diffuser_emote,
    enregistrer_reglages,
)
from pbm_api.games.temps_reel import Hub, piloter_canal
from pbm_api.models import JeuEmoteReglages, User

_IDENTITY = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}


async def _make_user(db, *, game_access: bool = True) -> User:
    user = User(
        email=f"em-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="x",
        game_access=game_access,
        **_IDENTITY,
    )
    db.add(user)
    await db.flush()
    return user


# --- La règle de débit, pure --------------------------------------------------


def test_debit_passe_sans_historique() -> None:
    """Première emote : rien à retenir, elle passe."""
    assert regles.debit_autorise([], 100.0) == (True, 0.0)


def test_debit_refuse_deux_emotes_collees() -> None:
    """Deux emotes dans la même seconde : refusé, et le refus **dit** combien attendre.

    Sans cette règle, cinq emotes en un dixième de seconde seraient un clignotement sur l'écran de
    l'adversaire, pas un message.
    """
    autorise, attente = regles.debit_autorise([100.0], 100.2)
    assert autorise is False
    assert attente == pytest.approx(regles.INTERVALLE_MIN_SECONDES - 0.2)


def test_debit_passe_apres_intervalle_minimal() -> None:
    autorise, attente = regles.debit_autorise([100.0], 100.0 + regles.INTERVALLE_MIN_SECONDES)
    assert (autorise, attente) == (True, 0.0)


def test_debit_refuse_au_dela_du_quota_de_fenetre() -> None:
    """Le quota de la fenêtre glissante bloque la (MAX+1)-ième, même espacée correctement."""
    envois = [100.0 + i * 2.0 for i in range(regles.MAX_PAR_FENETRE)]
    maintenant = envois[-1] + regles.INTERVALLE_MIN_SECONDES + 0.1
    autorise, attente = regles.debit_autorise(envois, maintenant)
    assert autorise is False
    # L'attente est le temps qu'il faut à la plus ancienne pour sortir de la fenêtre.
    assert attente == pytest.approx(envois[0] + regles.FENETRE_SECONDES - maintenant)


def test_debit_oublie_ce_qui_est_sorti_de_la_fenetre() -> None:
    """Une emote hors fenêtre ne pèse plus : le quota se reconstitue de lui-même."""
    envois = [100.0 + i * 2.0 for i in range(regles.MAX_PAR_FENETRE)]
    plus_tard = envois[0] + regles.FENETRE_SECONDES + 0.01
    assert regles.debit_autorise(envois, plus_tard)[0] is True


def test_message_trop_rapide_arrondit_vers_le_haut() -> None:
    """Annoncer « 0 s » tout en refusant serait pire que de ne rien dire."""
    assert "1 s" in regles.message_trop_rapide(0.2)
    assert "3 s" in regles.message_trop_rapide(2.4)


def test_catalogue_ferme() -> None:
    """Garde de lecture : la liste est figée, en ajouter une oblige à repasser par la règle.

    La règle, c'est : **une emote parle de son auteur, ou félicite l'autre. Jamais l'inverse.**
    C'est elle qui répond au point 1 de la mission (aucune emote ne peut servir à narguer) :
    « Oups… » dit *je me suis trompé*, pas *tu t'es trompé*. Ce test n'interdit pas d'enrichir
    le catalogue : il interdit de le faire sans relire cette phrase.
    """
    assert [e.code for e in regles.CATALOGUE] == [
        "bonjour",
        "bonne_partie",
        "bonne_chance",
        "bien_joue",
        "belle_carte",
        "merci",
        "oups",
        "je_reflechis",
        "un_instant",
        "ton_tour",
    ]
    assert regles.CODES == frozenset(e.code for e in regles.CATALOGUE)


def test_defauts_purs_accordes_avec_le_modele() -> None:
    """Le défaut du code et le ``server_default`` de la table doivent dire la même chose.

    Deux jeux de défauts qui divergent, c'est un réglage qui change de sens selon qu'une ligne
    existe ou non — le joueur ne pourrait pas savoir ce qui s'applique à lui.
    """
    colonne = JeuEmoteReglages.__table__.c.recevoir_emotes
    assert regles.ReglagesEmotes().recevoir_emotes is True
    assert "true" in str(colonne.server_default.arg).lower()


# --- Le limiteur, en mémoire --------------------------------------------------


def test_limiteur_compte_par_joueur_et_par_partie() -> None:
    """Le débit d'un joueur ne consomme pas celui de l'autre, ni celui d'une autre partie."""
    limiteur = LimiteurEmotes()
    g1, g2 = uuid.uuid4(), uuid.uuid4()
    a, b = uuid.uuid4(), uuid.uuid4()
    assert limiteur.autoriser(g1, a, 100.0)[0] is True
    assert limiteur.autoriser(g1, a, 100.1)[0] is False  # trop collé
    assert limiteur.autoriser(g1, b, 100.1)[0] is True  # l'autre joueur n'est pas pénalisé
    assert limiteur.autoriser(g2, a, 100.1)[0] is True  # ni la même personne dans une autre partie


def test_limiteur_nenregistre_pas_un_refus() -> None:
    """Spammer ne repousse pas sa propre autorisation : un refus ne compte pas comme un envoi."""
    limiteur = LimiteurEmotes()
    g, u = uuid.uuid4(), uuid.uuid4()
    limiteur.autoriser(g, u, 100.0)
    for i in range(10):
        limiteur.autoriser(g, u, 100.0 + i * 0.01)  # dix tentatives refusées
    assert limiteur.autoriser(g, u, 100.0 + regles.INTERVALLE_MIN_SECONDES)[0] is True


def test_limiteur_oublie_la_partie() -> None:
    """« Rien au-delà de la partie » : ``oublier`` efface tout ce que le limiteur en savait."""
    limiteur = LimiteurEmotes()
    g, u = uuid.uuid4(), uuid.uuid4()
    limiteur.autoriser(g, u, 100.0)
    assert limiteur.connait(g) is True
    limiteur.oublier(g)
    assert limiteur.connait(g) is False
    # Et le budget repart de zéro : plus aucune trace de l'emote précédente.
    assert limiteur.autoriser(g, u, 100.1)[0] is True


# --- Le réglage, en base ------------------------------------------------------


async def test_reglage_defaut_sans_ligne(db_session) -> None:
    """Un compte qui n'a jamais touché au réglage échange des emotes (défaut DJ10)."""
    user = await _make_user(db_session)
    assert (await charger_reglages(db_session, user.id)).recevoir_emotes is True
    assert await db_session.get(JeuEmoteReglages, user.id) is None  # aucune ligne inutile écrite


async def test_reglage_memorise(db_session) -> None:
    """Couper écrit une ligne : le choix vaut pour les parties suivantes, pas pour cet onglet."""
    user = await _make_user(db_session)
    await enregistrer_reglages(db_session, user.id, recevoir_emotes=False)
    assert (await charger_reglages(db_session, user.id)).recevoir_emotes is False
    await enregistrer_reglages(db_session, user.id, recevoir_emotes=True)
    assert (await charger_reglages(db_session, user.id)).recevoir_emotes is True


async def test_reglage_patch_partiel_ne_touche_rien(db_session) -> None:
    """``None`` laisse le réglage en place : deux onglets ne s'écrasent pas l'un l'autre."""
    user = await _make_user(db_session)
    await enregistrer_reglages(db_session, user.id, recevoir_emotes=False)
    assert (
        await enregistrer_reglages(db_session, user.id, recevoir_emotes=None)
    ).recevoir_emotes is False


async def test_comptes_ayant_coupe_ne_retient_que_les_coupes(db_session) -> None:
    a = await _make_user(db_session)
    b = await _make_user(db_session)
    await enregistrer_reglages(db_session, b.id, recevoir_emotes=False)
    assert await comptes_ayant_coupe(db_session, [a.id, b.id]) == frozenset({b.id})
    assert await comptes_ayant_coupe(db_session, []) == frozenset()


# --- La diffusion -------------------------------------------------------------


class BusDeTest:
    """Bus minimal satisfaisant :class:`~pbm_api.games.emotes_service.BusEmotes`."""

    def __init__(self, abonnes: list[uuid.UUID]) -> None:
        self._abonnes = abonnes
        self.recus: list[tuple[uuid.UUID, dict]] = []

    def user_ids(self, game_id: uuid.UUID) -> frozenset[uuid.UUID]:
        return frozenset(self._abonnes)

    def publier_emote(self, game_id, *, code, de_user_id, coupes) -> int:
        servis = 0
        for user_id in self._abonnes:
            if user_id in coupes:
                continue
            self.recus.append(
                (user_id, {"code": code, "de": "moi" if user_id == de_user_id else "adversaire"})
            )
            servis += 1
        return servis


async def test_diffusion_sert_les_deux_joueurs_avec_le_bon_cote(db_session) -> None:
    """Chacun reçoit l'emote, l'émetteur en « moi » (confirmation), l'autre en « adversaire »."""
    a = await _make_user(db_session)
    b = await _make_user(db_session)
    bus = BusDeTest([a.id, b.id])
    game_id = uuid.uuid4()

    refus = await diffuser_emote(
        bus,
        db_session,
        game_id=game_id,
        de_user_id=a.id,
        code="bien_joue",
        maintenant=100.0,
        limiteur=LimiteurEmotes(),
    )

    assert refus is None
    assert dict(bus.recus)[a.id]["de"] == "moi"
    assert dict(bus.recus)[b.id]["de"] == "adversaire"


async def test_code_hors_catalogue_refuse(db_session) -> None:
    """Un code inconnu est **refusé**, jamais replié sur une emote par défaut.

    Replier reviendrait à faire dire à un joueur une phrase que personne n'a choisie : le contraire
    exact de DJ10.
    """
    a = await _make_user(db_session)
    bus = BusDeTest([a.id])
    refus = await diffuser_emote(
        bus,
        db_session,
        game_id=uuid.uuid4(),
        de_user_id=a.id,
        code="tu_joues_mal",
        maintenant=100.0,
        limiteur=LimiteurEmotes(),
    )
    assert refus is not None and refus["code"] == regles.ERREUR_INCONNUE
    assert bus.recus == []


async def test_aucun_texte_ne_traverse(db_session) -> None:
    """Le seul champ lu est ``code``, et il doit être une chaîne du catalogue.

    C'est la garantie « aucune saisie de texte libre » côté serveur : il n'existe pas de chemin par
    lequel une phrase saisie par un joueur atteindrait l'autre. Un client bricolé qui envoie du
    texte est refusé comme un code inconnu.
    """
    a = await _make_user(db_session)
    bus = BusDeTest([a.id])
    for charge in ("Coucou, tu as quel âge ?", "", 12, None, ["bien_joue"], {"code": "bien_joue"}):
        refus = await diffuser_emote(
            bus,
            db_session,
            game_id=uuid.uuid4(),
            de_user_id=a.id,
            code=charge,
            maintenant=100.0,
            limiteur=LimiteurEmotes(),
        )
        assert refus is not None and refus["code"] == regles.ERREUR_INCONNUE, charge
    assert bus.recus == []


async def test_emetteur_ayant_coupe_ne_peut_pas_envoyer(db_session) -> None:
    """Un seul interrupteur, les deux sens : coupé, on ne reçoit plus **et** on n'envoie plus.

    Le serveur fait autorité : l'écran masque la palette, mais c'est ce refus-ci qui compte — un
    client bricolé ne contourne pas un réglage.
    """
    a = await _make_user(db_session)
    b = await _make_user(db_session)
    await enregistrer_reglages(db_session, a.id, recevoir_emotes=False)
    bus = BusDeTest([a.id, b.id])

    refus = await diffuser_emote(
        bus,
        db_session,
        game_id=uuid.uuid4(),
        de_user_id=a.id,
        code="bien_joue",
        maintenant=100.0,
        limiteur=LimiteurEmotes(),
    )
    assert refus is not None and refus["code"] == regles.ERREUR_COUPEES
    assert bus.recus == []


async def test_coupure_immediate_sans_reconnexion(db_session) -> None:
    """Critère : couper est **immédiat**. La diffusion relit le réglage à chaque emote.

    On diffuse une première emote (reçue par les deux), puis le destinataire coupe — sans fermer ni
    rouvrir quoi que ce soit — et la seconde emote ne l'atteint plus. C'est bien la relecture par
    emote qui le prouve : un réglage lu une fois à l'abonnement ne prendrait effet qu'après un F5.
    """
    a = await _make_user(db_session)
    b = await _make_user(db_session)
    bus = BusDeTest([a.id, b.id])
    limiteur = LimiteurEmotes()
    game_id = uuid.uuid4()

    await diffuser_emote(
        bus,
        db_session,
        game_id=game_id,
        de_user_id=a.id,
        code="bonjour",
        maintenant=100.0,
        limiteur=limiteur,
    )
    assert b.id in dict(bus.recus)

    bus.recus.clear()
    await enregistrer_reglages(db_session, b.id, recevoir_emotes=False)

    await diffuser_emote(
        bus,
        db_session,
        game_id=game_id,
        de_user_id=a.id,
        code="bien_joue",
        maintenant=102.0,
        limiteur=limiteur,
    )
    # L'émetteur garde son écho ; le destinataire qui a coupé ne reçoit rien.
    assert [u for u, _ in bus.recus] == [a.id]


async def test_debit_depasse_refuse_avec_le_delai(db_session) -> None:
    """Critère : le débit est limité **et testé** de bout en bout, délai annoncé compris."""
    a = await _make_user(db_session)
    bus = BusDeTest([a.id])
    limiteur = LimiteurEmotes()
    game_id = uuid.uuid4()

    assert (
        await diffuser_emote(
            bus,
            db_session,
            game_id=game_id,
            de_user_id=a.id,
            code="bonjour",
            maintenant=100.0,
            limiteur=limiteur,
        )
        is None
    )
    refus = await diffuser_emote(
        bus,
        db_session,
        game_id=game_id,
        de_user_id=a.id,
        code="merci",
        maintenant=100.1,
        limiteur=limiteur,
    )
    assert refus is not None
    assert refus["code"] == regles.ERREUR_TROP_RAPIDE
    assert refus["attente"] > 0
    assert "attends" in refus["message"]


async def test_tous_destinataires_coupes_nest_pas_un_refus(db_session) -> None:
    """L'adversaire a coupé : l'emote part quand même, et on ne le dit pas à l'émetteur.

    Annoncer « l'adversaire t'a coupé » transformerait un réglage de confort en information
    sociale, donc en reproche. L'émetteur reçoit son écho, et c'est tout.
    """
    a = await _make_user(db_session)
    b = await _make_user(db_session)
    await enregistrer_reglages(db_session, b.id, recevoir_emotes=False)
    bus = BusDeTest([a.id, b.id])

    refus = await diffuser_emote(
        bus,
        db_session,
        game_id=uuid.uuid4(),
        de_user_id=a.id,
        code="merci",
        maintenant=100.0,
        limiteur=LimiteurEmotes(),
    )
    assert refus is None
    assert [u for u, _ in bus.recus] == [a.id]


# --- Le hub, et l'absence de trace dans le journal ---------------------------


def test_hub_publier_emote_respecte_les_coupes() -> None:
    """Le hub ne dépose rien chez un abonné qui a coupé, et compte ceux qu'il a servis."""
    hub = Hub()
    game_id = uuid.uuid4()
    a, b = uuid.uuid4(), uuid.uuid4()
    ab_a = hub.souscrire(game_id, a)
    ab_b = hub.souscrire(game_id, b)

    assert hub.user_ids(game_id) == frozenset({a, b})
    servis = hub.publier_emote(game_id, code="oups", de_user_id=a, coupes=frozenset({b}))

    assert servis == 1
    assert ab_a.file.get_nowait() == {"type": "emote", "code": "oups", "de": "moi"}
    assert ab_b.file.empty()


def test_hub_emote_ne_marque_pas_la_saturation() -> None:
    """File pleine : l'emote est perdue (journalisée), mais aucune resync n'est programmée.

    Une emote n'est pas rattrapable — elle n'a pas de numéro de séquence. Marquer l'abonné
    « saturé » déclencherait une resynchronisation complète de la partie pour un message que la
    resync ne contient même pas : du travail pour rien, à chaque emote d'un client lent.
    """
    hub = Hub()
    game_id = uuid.uuid4()
    a = uuid.uuid4()
    abonne = hub.souscrire(game_id, a)
    abonne.file = asyncio.Queue(1)
    abonne.file.put_nowait({"type": "evenement", "numero": 0})

    assert hub.publier_emote(game_id, code="oups", de_user_id=a, coupes=frozenset()) == 0
    assert abonne.sature is False


async def test_emote_nentre_pas_dans_le_journal(db_session) -> None:
    """Critère : rien n'est conservé au-delà de la partie — même pas une ligne de journal.

    On pilote un vrai canal, on lui envoie une emote comme le ferait le navigateur, et on vérifie
    que le numéro courant de la partie **n'a pas bougé** : l'emote n'est pas un coup, elle n'est
    donc ni journalisée, ni rejouable, ni visible dans un replay.
    """
    from pbm_api.games.service import appliquer_action, creer_partie
    from pbm_api.models import Card, Deck, DeckCard, Set

    async def _carte(nom: str) -> Card:
        set_row = Set(code=f"em-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
        db_session.add(set_row)
        await db_session.flush()
        carte = Card(
            set_id=set_row.id,
            number=str(uuid.uuid4().int % 1000),
            name=nom,
            supertype="Pokémon",
            energy_type="water",
            element_type="water",
            hp=60,
            stage="Base",
            retreat_cost=1,
            prize_marker="ordinaire",
        )
        db_session.add(carte)
        await db_session.flush()
        return carte

    async def _deck(user: User, carte: Card) -> Deck:
        deck = Deck(user_id=user.id, name="Deck test")
        db_session.add(deck)
        await db_session.flush()
        db_session.add(DeckCard(deck_id=deck.id, card_id=carte.id, quantity=10))
        await db_session.flush()
        return deck

    user_a = await _make_user(db_session)
    user_b = await _make_user(db_session)
    deck_a = await _deck(user_a, await _carte("Carpanaud"))
    deck_b = await _deck(user_b, await _carte("Magicarpe"))
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )
    await appliquer_action(
        db_session, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=0
    )
    numero_avant = game.current_numero

    @asynccontextmanager
    async def _fabrique():
        yield db_session

    class FauxCanal:
        def __init__(self) -> None:
            self.entrants: asyncio.Queue = asyncio.Queue()
            self.sortants: list[dict] = []

        async def recevoir(self) -> dict | None:
            return await self.entrants.get()

        async def envoyer(self, message: dict) -> None:
            self.sortants.append(message)

    hub = Hub()
    abonne = hub.souscrire(game.id, user_a.id)
    canal = FauxCanal()
    limiteur = LimiteurEmotes()
    tache = asyncio.ensure_future(
        piloter_canal(
            canal,
            abonne=abonne,
            fabrique_session=_fabrique,
            game_id=game.id,
            graine_hex=game.graine,
            depuis=0,
            intervalle_battement=5.0,
            bus_emotes=hub,
            limiteur_emotes=limiteur,
        )
    )
    try:
        await canal.entrants.put({"type": "emote", "code": "bien_joue"})
        # L'emote revient par la file de diffusion de l'abonné (écho « moi »).
        echo = await asyncio.wait_for(abonne.file.get(), timeout=2.0)
        assert echo == {"type": "emote", "code": "bien_joue", "de": "moi"}
    finally:
        await canal.entrants.put(None)
        await asyncio.wait_for(tache, timeout=2.0)

    await db_session.refresh(game)
    assert game.current_numero == numero_avant, (
        "Une emote a avancé le numéro de la partie : elle est donc entrée dans le journal, "
        "alors que le lot exige qu'elle ne survive pas à la partie."
    )


async def test_canal_refuse_une_emote_inconnue_en_le_disant(db_session) -> None:
    """Un code inconnu reçu sur le canal renvoie une erreur explicite à l'émetteur seul."""
    from pbm_api.games.temps_reel import _traiter_message_client

    user = await _make_user(db_session)
    game_id = uuid.uuid4()

    @asynccontextmanager
    async def _fabrique():
        yield db_session

    class Canal:
        def __init__(self) -> None:
            self.sortants: list[dict] = []

        async def envoyer(self, message: dict) -> None:
            self.sortants.append(message)

    canal = Canal()
    hub = Hub()
    hub.souscrire(game_id, user.id)
    transmis = await _traiter_message_client(
        canal,
        {"type": "emote", "code": "va_te_faire"},
        _fabrique,
        game_id,
        user.id,
        "00" * 16,
        7,
        bus_emotes=hub,
        limiteur_emotes=LimiteurEmotes(),
    )

    assert transmis == 7  # une emote ne touche pas le numéro de séquence
    assert canal.sortants[-1]["code"] == regles.ERREUR_INCONNUE
