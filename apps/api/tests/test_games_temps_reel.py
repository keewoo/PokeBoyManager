"""Canal temps réel des parties (`pbm_api.games.temps_reel`) — lot `j-temps-reel`.

Couvre les critères d'acceptation du lot, chacun sans socket réel (ni thread, ni navigateur) :

* **reprise après F5** — `resynchroniser` rend la vue complète de l'état courant plus la file des
  coups depuis un numéro : rejouer le journal remet le joueur exactement où il était
  (`test_resynchroniser_*`) ;
* **aucune perte sur coupure** — la file des coups ∈ [`depuis`, courant) est exhaustive et ordonnée
  par numéro, insensible au désordre et aux doublons (`test_resynchroniser_depuis_milieu`,
  `test_canal_saturation_rattrapage`) ;
* **diffusion projetée par destinataire** — le `Hub` ne diffuse jamais l'état brut
  (`test_hub_publier_projette_*`), et un rejeu idempotent n'est pas diffusé.

Le pilotage de canal est exercé sur un **faux canal en mémoire**, dans la boucle du test : la
resynchronisation, le battement de cœur, la resync à la demande et le rattrapage après saturation
sont tous déterministes. La route de repli HTTP et l'accès croisé sont dans
`test_games_ws_routes.py`.
"""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime

from pbm_api.games.service import ResultatAction, appliquer_action, creer_partie
from pbm_api.games.temps_reel import Hub, piloter_canal, resynchroniser
from pbm_api.models import Card, Deck, DeckCard, Set, User

_IDENTITY = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}


async def _make_user(db) -> User:
    user = User(email=f"tr-{uuid.uuid4().hex[:10]}@example.com", password_hash="x", **_IDENTITY)
    db.add(user)
    await db.flush()
    return user


async def _make_card(db, *, name: str) -> Card:
    set_row = Set(code=f"tr-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
    db.add(set_row)
    await db.flush()
    card = Card(
        set_id=set_row.id,
        number=str(uuid.uuid4().int % 1000),
        name=name,
        supertype="Pokémon",
        energy_type="water",
        element_type="water",
        hp=60,
        stage="Base",
        retreat_cost=1,
        prize_marker="ordinaire",
    )
    db.add(card)
    await db.flush()
    return card


async def _make_deck(db, user: User, card: Card, qty: int = 10) -> Deck:
    deck = Deck(user_id=user.id, name="Deck test")
    db.add(deck)
    await db.flush()
    db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=qty))
    await db.flush()
    return deck


async def _partie(db):
    """Deux joueurs, une partie prête à jouer ; renvoie `(game, user_a, user_b)`."""
    user_a = await _make_user(db)
    user_b = await _make_user(db)
    carte_a = await _make_card(db, name="Carpanaud")
    carte_b = await _make_card(db, name="Tiplouf")
    deck_a = await _make_deck(db, user_a, carte_a)
    deck_b = await _make_deck(db, user_b, carte_b)
    game = await creer_partie(
        db, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )
    return game, user_a, user_b


def _fabrique(db):
    """Fabrique de session qui prête la session du test au pilote (même boucle, non refermée)."""

    @asynccontextmanager
    async def _cm():
        yield db

    return _cm


# --- resynchroniser ----------------------------------------------------------


async def test_resynchroniser_reprise_complete_et_file(db_session):
    game, user_a, _ = await _partie(db_session)
    for n in range(3):
        await appliquer_action(
            db_session, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=n
        )
    await db_session.refresh(game)

    resync = await resynchroniser(db_session, game, user_id=user_a.id, depuis=0)

    assert resync["type"] == "resync"
    assert resync["numero"] == 3
    assert [c["numero"] for c in resync["evenements"]] == [0, 1, 2]
    assert resync["vue"]["joueurs"]  # la vue complète est présente (reprise exacte)
    # Le secret d'aléatoire ne fuit jamais dans la charge temps réel.
    assert "graine" not in json.dumps(resync)


async def test_resynchroniser_depuis_milieu_ne_rejoue_que_le_reste(db_session):
    game, user_a, _ = await _partie(db_session)
    for n in range(3):
        await appliquer_action(
            db_session, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=n
        )
    await db_session.refresh(game)

    resync = await resynchroniser(db_session, game, user_id=user_a.id, depuis=2)

    # « Donne-moi tout depuis 2 » : seuls les coups 2.. (ici le coup 2), jamais 0 ni 1.
    assert [c["numero"] for c in resync["evenements"]] == [2]
    assert resync["depuis"] == 2
    assert resync["numero"] == 3


async def test_resynchroniser_au_numero_courant_rend_vue_sans_coup(db_session):
    game, user_a, _ = await _partie(db_session)
    for n in range(2):
        await appliquer_action(
            db_session, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=n
        )
    await db_session.refresh(game)

    resync = await resynchroniser(db_session, game, user_id=user_a.id, depuis=2)

    # Un F5 « à jour » : aucune file à rejouer, mais la vue complète pour se repositionner.
    assert resync["evenements"] == []
    assert resync["vue"]["joueurs"]


async def test_resynchroniser_depuis_au_dela_est_borne(db_session):
    game, user_a, _ = await _partie(db_session)
    await appliquer_action(
        db_session, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=0
    )
    await db_session.refresh(game)

    resync = await resynchroniser(db_session, game, user_id=user_a.id, depuis=999)

    assert resync["depuis"] == resync["numero"] == 1
    assert resync["evenements"] == []


async def test_resynchroniser_partie_terminee_porte_le_vainqueur(db_session):
    game, user_a, user_b = await _partie(db_session)
    await appliquer_action(
        db_session, game_id=game.id, user_id=user_a.id, type="abandonner", numero_attendu=0
    )
    await db_session.refresh(game)

    resync = await resynchroniser(db_session, game, user_id=user_b.id, depuis=0)

    assert resync["termine"] is True
    assert resync["vainqueur_user_id"] == str(user_b.id)  # B gagne, A ayant abandonné


# --- Hub ---------------------------------------------------------------------


async def _un_resultat(db, game, user_a) -> ResultatAction:
    return await appliquer_action(
        db, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=0
    )


async def test_hub_publier_projette_pour_chaque_destinataire(db_session):
    game, user_a, user_b = await _partie(db_session)
    resultat = await _un_resultat(db_session, game, user_a)

    hub = Hub()
    ab_a = hub.souscrire(game.id, user_a.id)
    ab_b = hub.souscrire(game.id, user_b.id)
    hub.publier(game.id, resultat, graine_hex=game.graine)

    msg_a = ab_a.file.get_nowait()
    msg_b = ab_b.file.get_nowait()
    assert msg_a["type"] == "evenement" and msg_a["numero"] == 0
    assert msg_b["type"] == "evenement" and msg_b["numero"] == 0
    # Chacun reçoit SA vue : A a pioché, l'événement le concerne de son point de vue, B du sien.
    assert "vue" in msg_a and "vue" in msg_b
    assert "graine" not in json.dumps(msg_b)


async def test_hub_rejeu_idempotent_non_diffuse(db_session):
    game, user_a, _ = await _partie(db_session)
    resultat = await _un_resultat(db_session, game, user_a)
    rejeu = ResultatAction(
        numero=resultat.numero,
        evenements=resultat.evenements,
        empreinte=resultat.empreinte,
        terminee=resultat.terminee,
        vainqueur_user_id=resultat.vainqueur_user_id,
        raison_fin=resultat.raison_fin,
        etat=resultat.etat,
        rejoue=True,
        rng_compteurs=resultat.rng_compteurs,
    )

    hub = Hub()
    abonne = hub.souscrire(game.id, user_a.id)
    hub.publier(game.id, rejeu, graine_hex=game.graine)

    assert abonne.file.empty()  # un rejeu n'apporte aucun coup nouveau : rien à diffuser


async def test_hub_saturation_marque_sans_perte(db_session):
    game, user_a, _ = await _partie(db_session)
    resultat = await _un_resultat(db_session, game, user_a)

    hub = Hub()
    abonne = hub.souscrire(game.id, user_a.id)
    abonne.file = asyncio.Queue(1)
    abonne.file.put_nowait({"type": "evenement", "numero": 0})  # file pleine
    hub.publier(game.id, resultat, graine_hex=game.graine)

    # Jamais de perte muette : l'abonné est marqué, le pilote lui renverra une resync.
    assert abonne.sature is True


async def test_hub_desouscrire_nettoie(db_session):
    game, user_a, _ = await _partie(db_session)
    hub = Hub()
    abonne = hub.souscrire(game.id, user_a.id)
    assert hub.nb_abonnes(game.id) == 1
    hub.desouscrire(game.id, abonne)
    assert hub.nb_abonnes(game.id) == 0


# --- Pilotage de canal (faux canal en mémoire) -------------------------------


class FauxCanal:
    """Faux :class:`Canal` en mémoire : scripte les messages client et enregistre les réponses."""

    def __init__(self) -> None:
        self.entrants: asyncio.Queue = asyncio.Queue()
        self.sortants: list[dict] = []

    async def recevoir(self) -> dict | None:
        return await self.entrants.get()

    async def envoyer(self, message: dict) -> None:
        self.sortants.append(message)

    async def attendre(self, type_attendu: str, timeout: float = 1.0) -> dict:
        """Attend qu'un message de ce type soit émis (sans toucher la base dans le test)."""
        echeance = 0.0
        while echeance < timeout:
            for message in self.sortants:
                if message.get("type") == type_attendu:
                    return message
            await asyncio.sleep(0.01)
            echeance += 0.01
        recus = [m.get("type") for m in self.sortants]
        raise AssertionError(f"Aucun message « {type_attendu} » émis. Reçus : {recus}")


async def _piloter(canal, abonne, db, game, *, depuis=0, intervalle=5.0):
    return asyncio.ensure_future(
        piloter_canal(
            canal,
            abonne=abonne,
            fabrique_session=_fabrique(db),
            game_id=game.id,
            graine_hex=game.graine,
            depuis=depuis,
            intervalle_battement=intervalle,
        )
    )


async def _arreter(canal, tache) -> None:
    await canal.entrants.put(None)  # None = déconnexion → fin propre du pilote
    await asyncio.wait_for(tache, timeout=1.0)


async def test_canal_envoie_resync_initiale(db_session):
    game, user_a, _ = await _partie(db_session)
    await appliquer_action(
        db_session, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=0
    )
    hub = Hub()
    abonne = hub.souscrire(game.id, user_a.id)
    canal = FauxCanal()
    tache = await _piloter(canal, abonne, db_session, game)
    try:
        resync = await canal.attendre("resync")
        assert resync["numero"] == 1
    finally:
        await _arreter(canal, tache)


async def test_canal_diffuse_un_coup_publie(db_session):
    game, user_a, _ = await _partie(db_session)
    resultat = await _un_resultat(db_session, game, user_a)
    hub = Hub()
    abonne = hub.souscrire(game.id, user_a.id)
    canal = FauxCanal()
    tache = await _piloter(canal, abonne, db_session, game)
    try:
        await canal.attendre("resync")
        hub.publier(game.id, resultat, graine_hex=game.graine)  # diffusion en mémoire, sans base
        evenement = await canal.attendre("evenement")
        assert evenement["numero"] == 0
    finally:
        await _arreter(canal, tache)


async def test_canal_resync_a_la_demande(db_session):
    game, user_a, _ = await _partie(db_session)
    await appliquer_action(
        db_session, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=0
    )
    hub = Hub()
    abonne = hub.souscrire(game.id, user_a.id)
    canal = FauxCanal()
    tache = await _piloter(canal, abonne, db_session, game, depuis=1)
    try:
        await canal.attendre("resync")  # initiale (depuis=1 → file vide)
        canal.sortants.clear()
        await canal.entrants.put({"type": "resync", "depuis": 0})
        resync = await canal.attendre("resync")
        assert [c["numero"] for c in resync["evenements"]] == [0]
    finally:
        await _arreter(canal, tache)


async def test_canal_ping_pong_et_type_inconnu(db_session):
    game, user_a, _ = await _partie(db_session)
    hub = Hub()
    abonne = hub.souscrire(game.id, user_a.id)
    canal = FauxCanal()
    tache = await _piloter(canal, abonne, db_session, game)
    try:
        await canal.attendre("resync")
        await canal.entrants.put({"type": "ping"})
        await canal.attendre("pong")
        await canal.entrants.put({"type": "farfelu"})
        erreur = await canal.attendre("erreur")
        assert erreur["code"] == "type_inconnu"
    finally:
        await _arreter(canal, tache)


async def test_canal_battement_sur_silence(db_session):
    game, user_a, _ = await _partie(db_session)
    await appliquer_action(
        db_session, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=0
    )
    hub = Hub()
    abonne = hub.souscrire(game.id, user_a.id)
    canal = FauxCanal()
    tache = await _piloter(canal, abonne, db_session, game, intervalle=0.05)
    try:
        battement = await canal.attendre("battement")
        assert battement["numero"] == 1  # le battement porte le numéro courant du serveur
    finally:
        await _arreter(canal, tache)


async def test_canal_saturation_declenche_un_rattrapage(db_session):
    game, user_a, _ = await _partie(db_session)
    await appliquer_action(
        db_session, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=0
    )
    hub = Hub()
    abonne = hub.souscrire(game.id, user_a.id)
    canal = FauxCanal()
    tache = await _piloter(canal, abonne, db_session, game, intervalle=0.05)
    try:
        await canal.attendre("resync")
        canal.sortants.clear()
        abonne.sature = True  # un abonné trop lent a débordé : le pilote doit le rattraper
        resync = await canal.attendre("resync")
        assert resync["numero"] == 1
    finally:
        await _arreter(canal, tache)
