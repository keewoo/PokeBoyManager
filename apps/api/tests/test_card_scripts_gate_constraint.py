"""La **contrainte en base** de la porte DJ8/D9 sur `card_scripts` (critère d'acceptation n°1).

« Aucun script n'entre en jeu sans tests verts ET validation » doit être tenu par une contrainte,
pas par une consigne : même un INSERT direct qui contournerait `enregistrer_script` doit être refusé
par la base si la ligne `scripte` n'a pas de programme, de date de validation ET `review_tests_ok`.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from pbm_api.jeu.scripts.depot import enregistrer_script, script_par_empreinte
from pbm_api.models.card_scripts import (
    SCRIPT_STATUT_NON_SUPPORTE,
    SCRIPT_STATUT_SCRIPTE,
    CardScript,
)

_PROG = {"version": 1, "effets": [{"op": "piocher", "nombre": 1}]}


@pytest.mark.asyncio
async def test_scripte_sans_preuve_est_refuse_par_la_base(db_session):
    """Un INSERT direct d'un `scripte` sans validation ni tests verts viole la contrainte CHECK."""
    ligne = CardScript(
        text_fingerprint="f" * 64,
        source_text="Piochez 1 carte.",
        dsl_version=1,
        script=_PROG,
        statut=SCRIPT_STATUT_SCRIPTE,
        # validated_at NULL, review_tests_ok NULL → la porte n'est pas franchie.
    )
    db_session.add(ligne)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_enregistrer_scripte_remplit_la_preuve_et_passe(db_session):
    """Par `enregistrer_script`, un `scripte` reçoit programme + validation + tests verts : OK."""
    texte = f"Piochez 1 carte — {uuid.uuid4().hex[:6]}."
    ligne = await enregistrer_script(
        db_session,
        source_text=texte,
        statut=SCRIPT_STATUT_SCRIPTE,
        dsl_version=1,
        script=_PROG,
        tests=[{"nom": "t"}],
    )
    relu = await script_par_empreinte(db_session, ligne.text_fingerprint)
    assert relu.statut == SCRIPT_STATUT_SCRIPTE
    assert relu.review_tests_ok is True  # vouché par défaut (validation/import)
    assert relu.validated_at is not None


@pytest.mark.asyncio
async def test_non_supporte_sans_preuve_est_accepte(db_session):
    """La contrainte ne vise QUE `scripte` : un `non_supporte` sans preuve reste permis (D9)."""
    texte = f"Effet hors langage — {uuid.uuid4().hex[:6]}."
    ligne = await enregistrer_script(
        db_session,
        source_text=texte,
        statut=SCRIPT_STATUT_NON_SUPPORTE,
        dsl_version=1,
        script=None,
        notes="tournure manquante",
    )
    assert ligne.statut == SCRIPT_STATUT_NON_SUPPORTE
    assert ligne.validated_at is None
