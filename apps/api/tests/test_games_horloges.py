"""Horloges d'une partie, côté service (lot `j-timer`).

Le décompte, les bascules et la détection d'expiration sont prouvés purs dans le job `game`
(`pbm_game.horloges`). Ici on couvre l'**intégration** API :

* une partie neuve porte ses horloges (colonne `games.horloges`), figées sur la config DJ4 ;
* un coup met à jour les horloges dans la même transaction (donc reprises après un F5) ;
* une **expiration** produit toujours un coup journalisé, jamais un blocage (défaite au temps) ;
* la **pause de déconnexion** gèle, la reconnexion reprend.

Les durées viennent de la configuration (`settings`) : un changement d'environnement ne demande pas
de redéployer le moteur. On tourne contre la vraie base de test (la CI fait foi).
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from pbm_game.horloges.modele import CompteurActif, ConfigHorloges, EtatHorloges
from sqlalchemy import select

from pbm_api.config import settings
from pbm_api.games import horloges as adapt
from pbm_api.games.service import (
    appliquer_action,
    creer_partie,
    expirer_horloge,
    marquer_deconnexion,
    marquer_reconnexion,
    reprendre_partie,
)
from pbm_api.models import Card, Deck, DeckCard, Game, GameEvent, Set, User

_IDENTITY = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}


async def _make_user(db) -> User:
    user = User(email=f"h-{uuid.uuid4().hex[:10]}@example.com", password_hash="x", **_IDENTITY)
    db.add(user)
    await db.flush()
    return user


async def _make_card(db, *, name: str) -> Card:
    set_row = Set(code=f"h-{uuid.uuid4().hex[:8]}", name="Set horloge", series="Série test")
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


async def _make_deck(db, user: User, card: Card, qty: int) -> Deck:
    deck = Deck(user_id=user.id, name="Deck horloge")
    db.add(deck)
    await db.flush()
    db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=qty))
    await db.flush()
    return deck


async def _partie(db) -> tuple[Game, User, User]:
    user_a = await _make_user(db)
    user_b = await _make_user(db)
    deck_a = await _make_deck(db, user_a, await _make_card(db, name="Carpanaud"), 10)
    deck_b = await _make_deck(db, user_b, await _make_card(db, name="Tiplouf"), 10)
    game = await creer_partie(
        db, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )
    return game, user_a, user_b


# --- Configuration : les durées viennent des réglages -----------------------


def test_config_horloges_vient_des_reglages():
    c = adapt.config_horloges(settings)
    assert c.par_tour_s == settings.horloge_par_tour_s
    assert c.par_joueur_s == settings.horloge_par_joueur_s
    assert c.par_decision_s == settings.horloge_par_decision_s
    assert c.tolerance_reseau_s == settings.horloge_tolerance_reseau_s
    assert c.pause_deconnexion_s == settings.horloge_pause_deconnexion_s


# --- Création : la partie porte ses horloges --------------------------------


async def test_creer_partie_pose_les_horloges(db_session):
    game, _, _ = await _partie(db_session)
    assert game.horloges is not None
    h = EtatHorloges.depuis_json(game.horloges)
    etat, _ = await reprendre_partie(db_session, game)
    # Plein budget pour chacun ; le tour du premier joueur court.
    assert set(h.budgets_s.values()) == {settings.horloge_par_joueur_s}
    assert h.actif is not None and h.actif.joueur == etat.tour.joueur_actif
    assert h.actif.genre == "tour"


async def test_un_coup_met_a_jour_les_horloges_dans_la_transaction(db_session):
    game, user_a, _ = await _partie(db_session)
    etat, _ = await reprendre_partie(db_session, game)
    actif_avant = etat.tour.joueur_actif

    res = await appliquer_action(
        db_session, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=0
    )

    # Le coup renvoie le temps restant affichable (vérité serveur) ...
    assert res.horloges is not None
    assert res.horloges["joueurs"][actif_avant]["genre"] == "tour"
    # ... et les horloges persistées suivent le même joueur (le tour n'a pas changé).
    await db_session.refresh(game)
    h = EtatHorloges.depuis_json(game.horloges)
    assert h.actif is not None and h.actif.joueur == actif_avant


# --- Expiration : toujours un coup journalisé, jamais un blocage ------------


async def _forcer_budget_epuise(db, game, now: datetime) -> str:
    """Place les horloges de ``game`` dans un état où le budget du joueur actif est quasi épuisé.

    Renvoie l'identifiant du joueur actif (le futur perdant au temps). Le compteur a démarré loin
    dans le passé : à ``now``, l'écoulé dépasse largement le petit budget restant.
    """
    etat, _ = await reprendre_partie(db, game)
    actif = etat.tour.joueur_actif
    autre = next(j.id for j in etat.joueurs if j.id != actif)
    cfg = adapt.config_horloges(settings)
    passe_lointain = now.timestamp() - 1000.0
    h = EtatHorloges(
        config=cfg,
        budgets_s={actif: 5.0, autre: cfg.par_joueur_s},
        actif=CompteurActif(joueur=actif, genre="tour", depuis=passe_lointain),
    )
    game.horloges = h.en_json()
    await db.commit()
    return actif


async def test_expiration_budget_journalise_une_defaite_au_temps(db_session):
    game, _, _ = await _partie(db_session)
    now = datetime.now(UTC)
    perdant = await _forcer_budget_epuise(db_session, game, now)

    res = await expirer_horloge(db_session, game.id, maintenant=now)

    assert res is not None and res.terminee  # un coup a bien été produit (pas de blocage)
    assert res.raison_fin == "temps_ecoule"
    await db_session.refresh(game)
    assert game.status == "terminee"
    assert game.raison_fin == "temps_ecoule"
    assert game.vainqueur_user_id is not None and str(game.vainqueur_user_id) != perdant
    # Le coup système est **journalisé** (jamais un abandon muet).
    events = (
        await db_session.execute(select(GameEvent).where(GameEvent.game_id == game.id))
    ).scalars().all()
    assert any(e.action["type"] == "defaite_temps" and e.auteur == "systeme" for e in events)


async def test_expiration_sans_echeance_ne_fait_rien(db_session):
    game, _, _ = await _partie(db_session)
    # Horloges fraîches (démarrées à la création) : rien n'a expiré juste après.
    res = await expirer_horloge(db_session, game.id, maintenant=datetime.now(UTC))
    assert res is None
    await db_session.refresh(game)
    assert game.status == "en_cours"


# --- Pause de déconnexion ----------------------------------------------------


async def test_pause_puis_reprise_de_deconnexion(db_session):
    game, user_a, _ = await _partie(db_session)
    now = datetime.now(UTC)

    await marquer_deconnexion(db_session, game.id, user_a.id, maintenant=now)
    await db_session.refresh(game)
    h = EtatHorloges.depuis_json(game.horloges)
    assert h.en_pause and h.pause_joueur is not None

    await marquer_reconnexion(db_session, game.id, maintenant=now + timedelta(seconds=30))
    await db_session.refresh(game)
    h2 = EtatHorloges.depuis_json(game.horloges)
    assert not h2.en_pause


async def test_pause_dont_la_grace_est_depassee_est_reprise_par_l_expiration(db_session):
    """Une pause qui dépasse sa grâce est reprise par le balayage d'expiration (sans coup)."""
    game, user_a, _ = await _partie(db_session)
    now = datetime.now(UTC)
    await marquer_deconnexion(db_session, game.id, user_a.id, maintenant=now)

    res = await expirer_horloge(
        db_session, game.id, maintenant=now + timedelta(seconds=200)
    )
    assert res is None  # grâce dépassée → on reprend les horloges, aucun coup n'est joué
    await db_session.refresh(game)
    assert not EtatHorloges.depuis_json(game.horloges).en_pause
    assert game.status == "en_cours"


# --- Mapping des causes d'expiration vers l'action par défaut (adaptateur) ---


def test_action_par_defaut_mappe_chaque_cause():
    cfg = ConfigHorloges(
        par_tour_s=90, par_joueur_s=1500, par_decision_s=30,
        tolerance_reseau_s=10, pause_deconnexion_s=120,
    )
    t0 = 1_000_000.0
    # Tour expiré → fin_tour.
    tour = EtatHorloges(
        config=cfg, budgets_s={"a": 1500.0, "b": 1500.0},
        actif=CompteurActif("a", "tour", t0),
    )
    assert adapt.action_par_defaut(tour.en_json(), t0 + 200) == ("fin_tour", {})
    # Décision expirée → expirer_demande.
    deci = EtatHorloges(
        config=cfg, budgets_s={"a": 1500.0, "b": 1500.0},
        actif=CompteurActif("b", "decision", t0),
    )
    assert adapt.action_par_defaut(deci.en_json(), t0 + 200) == ("expirer_demande", {})
    # Budget épuisé → defaite_temps (le perdant est nommé).
    budg = EtatHorloges(
        config=cfg, budgets_s={"a": 5.0, "b": 1500.0},
        actif=CompteurActif("a", "tour", t0),
    )
    assert adapt.action_par_defaut(budg.en_json(), t0 + 200) == ("defaite_temps", {"joueur": "a"})
    # Rien expiré → None.
    assert adapt.action_par_defaut(tour.en_json(), t0 + 5) is None
