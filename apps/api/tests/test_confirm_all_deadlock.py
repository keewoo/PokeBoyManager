"""Régression : interblocage Postgres entre « Tout ajouter » et le passage d'état concurrent.

Observé pendant le build e2e du 01/10/2026 (`asyncpg.exceptions.DeadlockDetectedError`, route
`POST /uploads/{id}/confirm-all`). Les deux transactions écrivent les MÊMES lignes `detections` :

- `run_state_estimation_for_upload` (worker) verrouille les détections UNE PAR UNE, dans l'ordre
  de son `SELECT`, au fil des `db.get(Card)` qui déclenchent un autoflush (chaque détection d'une
  vraie photo pointe une carte DIFFÉRENTE, donc chaque `get` fait une requête -> un flush -> un
  verrou `NO KEY UPDATE` de plus) ;
- `confirm_all` verrouille toutes ses détections d'un bloc à son unique `commit`.

Sans ORDER BY commun, le passage d'état verrouille dans l'ordre du tas et `confirm_all` dans
l'ordre des clés — deux ordres différents -> cycle. Le correctif impose l'ordre d'id ascendant à
TOUTES les transactions qui écrivent ces lignes (`ORDER BY detections.id`), ce qui sérialise sans
cycle possible.

Reproduction DÉTERMINISTE avec le vrai passage d'état : deux détections, chacune liée à une carte
distincte (pour que l'autoflush verrouille bien incrémentalement), semées pour que le `SELECT` non
ordonné les parcoure en id DESCENDANT. Un verrou (`monkeypatch`) suspend le passage d'état juste
après qu'il a pris son premier verrou, le temps que `confirm_all` prenne le verrou opposé.
Vérifié sur Postgres : sans `ORDER BY` sur le passage d'état -> interblocage ;
avec, ce test passe.
"""

import asyncio
import datetime
import os
import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import pbm_api.state.service as state_service
from pbm_api.models import Card, Set, User
from pbm_api.models.collection import Detection, DetectionStatus, Upload, UploadStatus
from pbm_api.state.service import run_state_estimation_for_upload
from pbm_api.validation.service import confirm_all

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v2_catalogue_complet_test",
)


def _is_deadlock(exc: BaseException) -> bool:
    return "deadlock" in (repr(exc) + str(exc)).lower()


@pytest.mark.asyncio
async def test_confirm_all_concurrent_with_state_pass_no_deadlock(monkeypatch):
    engine = create_async_engine(TEST_DATABASE_URL)
    d_lo_id, d_hi_id = sorted([uuid.uuid4(), uuid.uuid4()])
    user_id, upload_id, set_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    card_lo, card_hi = uuid.uuid4(), uuid.uuid4()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as s:
            s.add(
                User(
                    id=user_id,
                    email=f"dl-{user_id.hex}@ex.com",
                    password_hash="x",
                    last_name="T",
                    birth_date=datetime.date(2000, 1, 1),
                    terms_version="1",
                    terms_accepted_at=datetime.datetime(2020, 1, 1),
                )
            )
            s.add(Set(id=set_id, code=f"S{set_id.hex[:8]}", name="Set", total_cards=100))
            await s.flush()
            s.add(Card(id=card_lo, set_id=set_id, number="1", name="A"))
            s.add(Card(id=card_hi, set_id=set_id, number="2", name="B"))
            s.add(Upload(id=upload_id, user_id=user_id, s3_key="k", status=UploadStatus.processed))
            await s.flush()
            # d_hi inséré en PREMIER : un SELECT sans ORDER BY (passage d'état non corrigé) renvoie
            # d_hi d'abord -> verrouillage incrémental en id DESCENDANT, à rebours de `confirm_all`
            # (dont le flush verrouille en ordre de clé ascendant). Chaque détection pointe sa
            # PROPRE carte pour que `db.get(Card)` requête (et donc autoflush+verrouille) à chaque
            # tour.
            for det_id, card in ((d_hi_id, card_hi), (d_lo_id, card_lo)):
                s.add(
                    Detection(
                        id=det_id,
                        upload_id=upload_id,
                        bbox={},
                        crop_s3_key=None,
                        status=DetectionStatus.pending,
                        candidates=[{"card_id": str(card), "combined_score": 0.95}],
                    )
                )
            await s.commit()

        orig_matched = state_service._matched_card_signals
        gate = asyncio.Event()
        calls = {"n": 0}

        async def patched_matched(db, detection):
            # `orig` fait les `db.get(Card/Set)` : au 2e tour, l'autoflush y verrouille la détection
            # du 1er tour. On suspend alors le passage d'état, verrou en main, le temps que
            # `confirm_all` prenne le verrou opposé — c'est la fenêtre qui provoque le cycle.
            result = await orig_matched(db, detection)
            calls["n"] += 1
            if calls["n"] == 2:
                gate.set()
                await asyncio.sleep(2.0)
            return result

        monkeypatch.setattr(state_service, "_matched_card_signals", patched_matched)

        async def state_pass():
            async with AsyncSession(engine, expire_on_commit=False) as s2:
                upload = await s2.get(Upload, upload_id)
                await run_state_estimation_for_upload(s2, None, upload)

        async def confirm():
            await gate.wait()
            async with AsyncSession(engine, expire_on_commit=False) as s3:
                user = await s3.get(User, user_id)
                await confirm_all(s3, user, upload_id)

        results = await asyncio.wait_for(
            asyncio.gather(state_pass(), confirm(), return_exceptions=True), timeout=40
        )
        deadlocks = [r for r in results if isinstance(r, BaseException) and _is_deadlock(r)]
        others = [r for r in results if isinstance(r, BaseException) and not _is_deadlock(r)]
        assert not deadlocks, f"interblocage Postgres : {deadlocks!r}"
        assert not others, f"erreur inattendue : {others!r}"

        async with AsyncSession(engine, expire_on_commit=False) as s4:
            validated = (
                await s4.execute(
                    select(Detection).where(
                        Detection.upload_id == upload_id,
                        Detection.status == DetectionStatus.validated,
                    )
                )
            ).scalars().all()
            assert len(validated) == 2
    finally:
        async with AsyncSession(engine) as sc:
            await sc.execute(delete(User).where(User.id == user_id))
            await sc.execute(delete(Card).where(Card.id.in_([card_lo, card_hi])))
            await sc.execute(delete(Set).where(Set.id == set_id))
            await sc.commit()
        await engine.dispose()
