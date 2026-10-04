"""Le passage d'assistance de bout en bout (`pbm_api.jeu.scripts.assistance.runner`) — sur base.

Tests **sur base** (la CI fait foi) avec un fournisseur **factice** déterministe (aucune clé, aucun
réseau, aucune dépense réelle) : on prouve la mécanique DJ8 — un script qui passe tests ET
contradiction devient `scripte`, un effet déclaré hors langage devient `non_supporte`, le budget
s'arrête net au plafond, et une reprise ne retraite rien.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest

from pbm_api.jeu.scripts.assistance import runner
from pbm_api.jeu.scripts.assistance.fournisseur import FournisseurFactice, Usage
from pbm_api.jeu.scripts.depot import script_par_empreinte
from pbm_api.jeu.scripts.empreinte import empreinte_texte
from pbm_api.models import Card, CollectionItem, Set, User
from pbm_api.models.card_scripts import SCRIPT_STATUT_NON_SUPPORTE, SCRIPT_STATUT_SCRIPTE

_IDENTITY = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}

_PIOCHE_1 = "Piochez 1 carte."
_PIOCHE_2 = "Piochez 2 cartes."
_IMPOSSIBLE = "Un effet impossible à exprimer dans le langage."
#: Un effet dont le script proposé échoue à ses tests → statut « à revoir » (reste candidat, donc
#: c'est le grand livre — pas le registre — qui le saute à la reprise).
_BANCAL = "Un effet dont le script sera bancal."


def _script_pioche(n: int) -> dict:
    return {"version": 1, "effets": [{"op": "piocher", "nombre": n}]}


def _essai_pioche(n: int) -> dict:
    return {
        "nom": f"pioche {n}",
        "etat": {"alice": {"pioche": 5, "main": 0}, "bob": {}},
        "attendu": {"etat": {"alice": {"pioche": 5 - n, "main": n}}},
    }


def _proposition(n: int) -> str:
    import json

    return json.dumps(
        {
            "non_supporte": False,
            "confiance": "haute",
            "script": _script_pioche(n),
            "essais": [_essai_pioche(n)],
        }
    )


_NON_SUPPORTE = (
    '{"non_supporte": true, "raison": "tournure hors langage", "confiance": "basse",'
    ' "script": null, "essais": []}'
)
_APPROUVE = '{"verdict": "approuve", "raison": "conforme"}'


#: Une proposition dont l'essai est FAUX (pioche 1 mais en attend 2) → tests rouges → « à revoir ».
_BANCALE = (
    '{"non_supporte": false, "confiance": "moyenne",'
    ' "script": {"version": 1, "effets": [{"op": "piocher", "nombre": 1}]},'
    ' "essais": [{"nom": "faux", "etat": {"alice": {"pioche": 5, "main": 0}, "bob": {}},'
    ' "attendu": {"etat": {"alice": {"main": 2}}}}]}'
)


def _handler(prompt: str) -> str:
    """Répond en fonction du prompt : contradicteur → approuve ; proposeur → selon le texte."""
    if "avocat du diable" in prompt:
        return _APPROUVE
    if _BANCAL in prompt:
        return _BANCALE
    if _PIOCHE_2 in prompt:
        return _proposition(2)
    if _PIOCHE_1 in prompt:
        return _proposition(1)
    return _NON_SUPPORTE


async def _user_joueur(db) -> User:
    user = User(
        email=f"ia-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="x",
        game_access=True,
        **_IDENTITY,
    )
    db.add(user)
    await db.flush()
    return user


async def _carte_possedee(db, user: User, *, effet: str) -> Card:
    set_row = Set(code=f"ia-{uuid.uuid4().hex[:8]}", name="Set IA", series="Série test")
    db.add(set_row)
    await db.flush()
    card = Card(
        set_id=set_row.id,
        number=str(uuid.uuid4().int % 100000),
        name="Pokémon IA",
        supertype="Pokémon",
        energy_type="water",
        element_type="water",
        hp=60,
        stage="Base",
        retreat_cost=1,
        prize_marker="ordinaire",
        attacks=[{"name": "Att", "cost": ["water"], "damage": "10", "effect": effet}],
    )
    db.add(card)
    await db.flush()
    db.add(CollectionItem(user_id=user.id, card_id=card.id))
    await db.flush()
    return card


@pytest.mark.asyncio
async def test_passage_script_et_non_supporte(db_session, tmp_path):
    """Un effet exprimable devient `scripte` (tests + contradicteur), un autre `non_supporte`."""
    user = await _user_joueur(db_session)
    await _carte_possedee(db_session, user, effet=_PIOCHE_1)
    await _carte_possedee(db_session, user, effet=_IMPOSSIBLE)

    factice = FournisseurFactice(_handler, usage=Usage(0, 0))
    rapport = await runner.run(
        db_session,
        generateur=factice,
        plafond_eur=Decimal("50"),
        rate_usd_eur=Decimal("0.9"),
        model="claude-haiku-4-5",
        ledger_path=tmp_path / "ledger.json",
        limite=100,
    )
    assert rapport.scriptes == 1
    assert rapport.non_supportes == 1

    ligne_ok = await script_par_empreinte(db_session, empreinte_texte(_PIOCHE_1))
    assert ligne_ok.statut == SCRIPT_STATUT_SCRIPTE
    assert ligne_ok.review_tests_ok is True
    assert ligne_ok.review_contradicteur == "approuve"
    assert ligne_ok.famille == "pioche"
    assert ligne_ok.validated_at is not None

    ligne_ko = await script_par_empreinte(db_session, empreinte_texte(_IMPOSSIBLE))
    assert ligne_ko.statut == SCRIPT_STATUT_NON_SUPPORTE
    assert ligne_ko.script is None

    # Mesures de rendement présentes (mission point 5).
    assert rapport.mesures["acceptees_sans_retouche_pct"] == "100.00"


@pytest.mark.asyncio
async def test_reprise_scripte_nest_plus_candidat(db_session, tmp_path):
    """Un effet devenu `scripte` n'est plus sélectionné (décidé par le registre)."""
    user = await _user_joueur(db_session)
    await _carte_possedee(db_session, user, effet=_PIOCHE_1)
    ledger = tmp_path / "ledger.json"
    factice = FournisseurFactice(_handler, usage=Usage(0, 0))

    premier = await runner.run(
        db_session, generateur=factice, plafond_eur=Decimal("50"), rate_usd_eur=Decimal("0.9"),
        model="claude-haiku-4-5", ledger_path=ledger, limite=100,
    )
    assert premier.scriptes == 1

    second = await runner.run(
        db_session, generateur=factice, plafond_eur=Decimal("50"), rate_usd_eur=Decimal("0.9"),
        model="claude-haiku-4-5", ledger_path=ledger, limite=100,
    )
    assert second.status == "aucun_effet"
    assert second.effets_examines == 0  # rien n'a été retraité


@pytest.mark.asyncio
async def test_reprise_a_revoir_saute_par_le_grand_livre(db_session, tmp_path):
    """Un `a_revoir` reste candidat, mais le grand livre le saute à la reprise."""
    user = await _user_joueur(db_session)
    await _carte_possedee(db_session, user, effet=_BANCAL)
    ledger = tmp_path / "ledger.json"
    factice = FournisseurFactice(_handler, usage=Usage(0, 0))

    premier = await runner.run(
        db_session, generateur=factice, plafond_eur=Decimal("50"), rate_usd_eur=Decimal("0.9"),
        model="claude-haiku-4-5", ledger_path=ledger, limite=100,
    )
    assert premier.a_revoir == 1

    second = await runner.run(
        db_session, generateur=factice, plafond_eur=Decimal("50"), rate_usd_eur=Decimal("0.9"),
        model="claude-haiku-4-5", ledger_path=ledger, limite=100,
    )
    assert second.effets_examines == 0  # le candidat existe encore…
    assert second.deja_traites == 1  # …mais le grand livre le saute (reprise)


@pytest.mark.asyncio
async def test_plafond_arrete_le_passage(db_session, tmp_path):
    """Le passage s'arrête net au plafond, sans redemander (DJ8) : deux effets, budget pour un."""
    user = await _user_joueur(db_session)
    await _carte_possedee(db_session, user, effet=_PIOCHE_1)
    await _carte_possedee(db_session, user, effet=_PIOCHE_2)

    # Usage non nul → coût non nul par effet ; plafond minuscule → un seul effet passe.
    factice = FournisseurFactice(_handler, usage=Usage(1000, 1000))
    rapport = await runner.run(
        db_session,
        generateur=factice,
        plafond_eur=Decimal("0.005"),
        rate_usd_eur=Decimal("0.9"),
        model="claude-haiku-4-5",
        ledger_path=tmp_path / "ledger.json",
        limite=100,
    )
    assert rapport.status == "budget_epuise"
    assert rapport.effets_examines == 1  # le second n'a pas été traité
