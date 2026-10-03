"""Une **partie complète jouée par l'API** jusqu'à la victoire par les récompenses, puis rejouée.

Preuve du jalon J1 au niveau du **service** (lot ``j-coups-joueur``), au-delà du moteur pur : deux
decks (Pokémon attaquant + Énergies de base, cibles à récompenses) s'affrontent via
:func:`appliquer_action` — qui **valide** chaque coup contre la liste légale (anti-triche) et
**orchestre** les coups système entre les tours — de la mise en place jusqu'à la sixième récompense
prise (R-14.1). Puis :func:`reprendre_partie` reconstruit l'état depuis le journal et **vérifie
l'empreinte** : tout est rejouable. La CI fait foi.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pbm_game.actions import actions_legales
from pbm_game.actions.familles_jeu import familles_jeu
from pbm_game.journal import RAISON_DERNIERE_RECOMPENSE

from pbm_api.games.catalogue_jeu import construire_catalogue_jeu
from pbm_api.games.construction import joueur_id_de
from pbm_api.games.service import (
    appliquer_action,
    creer_partie,
    demarrer_partie,
    reprendre_partie,
)
from pbm_api.models import Card, Deck, DeckCard, Game, Set, User

_IDENTITY = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}
_GRAINE = (b"pbm-partie-complete-api-seed----").hex()  # 31→ complété ; ≥16 octets


async def _user(db) -> User:
    u = User(email=f"pc-{uuid.uuid4().hex[:10]}@example.com", password_hash="x", **_IDENTITY)
    db.add(u)
    await db.flush()
    return u


async def _set(db) -> Set:
    s = Set(code=f"pc-{uuid.uuid4().hex[:8]}", name="Set partie complète", series="Série test")
    db.add(s)
    await db.flush()
    return s


async def _pikachu(db, set_row) -> Card:
    """Attaquant : « Charge » coûte 1 énergie électrique, inflige 60 (K.O. une cible de 60 PV)."""
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


async def _cible(db, set_row) -> Card:
    """Défenseur : 3 récompenses (``tag_team``), 60 PV, aucune attaque (il ne riposte pas)."""
    c = Card(
        set_id=set_row.id, number=str(uuid.uuid4().int % 100000), name="Duo Tag",
        supertype="Pokémon", energy_type="incolore", element_type="incolore", hp=60,
        stage="Base", retreat_cost=0, prize_marker="tag_team", attacks=[],
    )
    db.add(c)
    await db.flush()
    return c


async def _deck(db, user, cartes: list[tuple[Card, int]]) -> Deck:
    deck = Deck(user_id=user.id, name="Deck partie complète")
    db.add(deck)
    await db.flush()
    for card, qty in cartes:
        db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=qty))
    await db.flush()
    return deck


def _identite_actif(joueur) -> str | None:
    return joueur.actif.cartes[0].instance_id if joueur.actif is not None else None


def _choisir(etat, jid, catalogue):
    """Stratégie minimale : promouvoir, placer, attaquer, charger l'Actif, sinon passer."""
    legales = actions_legales(etat, jid, familles=familles_jeu(catalogue))
    par_type: dict[str, list] = {}
    for coup in legales:
        par_type.setdefault(coup.action.type, []).append(coup)
    if "promouvoir" in par_type:
        return par_type["promouvoir"][0].action
    if "placer_mise_en_place" in par_type:
        return par_type["placer_mise_en_place"][0].action
    if "declarer_attaque" in par_type:
        return par_type["declarer_attaque"][0].action
    joueur = next(j for j in etat.joueurs if j.id == jid)
    if "attacher_energie" in par_type and joueur.actif is not None and not joueur.actif.energies:
        actif_id = _identite_actif(joueur)
        attaches = par_type["attacher_energie"]
        sur_actif = [c for c in attaches if c.action.params.get("cible") == actif_id]
        if sur_actif:
            return sur_actif[0].action
    if "avancer_phase" in par_type:
        return par_type["avancer_phase"][0].action
    return legales[0].action if legales else None


async def test_partie_complete_par_lapi_victoire_recompenses_et_rejeu(db_session):
    ua = await _user(db_session)
    ub = await _user(db_session)
    s = await _set(db_session)
    pika = await _pikachu(db_session, s)
    energie = await _energie(db_session, s)
    cible = await _cible(db_session, s)
    deck_a = await _deck(db_session, ua, [(pika, 6), (energie, 14)])
    deck_b = await _deck(db_session, ub, [(cible, 20)])

    game = await creer_partie(
        db_session, joueur_a=(ua.id, deck_a.id), joueur_b=(ub.id, deck_b.id), graine_hex=_GRAINE
    )
    await demarrer_partie(db_session, game)

    user_par_jid = {joueur_id_de(ua.id): ua.id, joueur_id_de(ub.id): ub.id}

    for _ in range(600):
        game = await db_session.get(Game, game.id)
        if game.status != "en_cours":
            break
        etat, _rng = await reprendre_partie(db_session, game)
        catalogue = await construire_catalogue_jeu(db_session, etat)
        if etat.mise_en_place is not None:
            idx = next(i for i, p in enumerate(etat.mise_en_place.placements) if p is None)
            acteur = etat.joueurs[idx].id
        else:
            acteur = etat.tour.joueur_actif
        action = _choisir(etat, acteur, catalogue)
        assert action is not None, f"aucun coup pour {acteur} (phase {etat.tour.phase})"
        await appliquer_action(
            db_session,
            game_id=game.id,
            user_id=user_par_jid[acteur],
            type=action.type,
            params=action.params,
            numero_attendu=game.current_numero,
        )

    game = await db_session.get(Game, game.id)
    assert game.status == "terminee", f"statut : {game.status}"
    assert game.vainqueur_user_id == ua.id, f"vainqueur : {game.vainqueur_user_id}"
    assert game.raison_fin == RAISON_DERNIERE_RECOMPENSE, f"raison : {game.raison_fin}"

    # Tout est rejouable : la reprise reconstruit l'état depuis le journal et vérifie l'empreinte.
    etat_final, _ = await reprendre_partie(db_session, game)
    assert etat_final.terminee and etat_final.vainqueur == joueur_id_de(ua.id)
