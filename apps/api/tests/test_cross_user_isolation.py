"""Isolation par utilisateur au niveau du schéma.

Ce lot ne crée aucune route HTTP (pas encore d'auth ni d'API de collection) : l'équivalent du
« test d'accès croisé » exigé par le processus se vérifie ici au niveau données — une requête
filtrée par `user_id` ne doit jamais laisser fuiter l'exemplaire d'un autre utilisateur. Le test
d'accès croisé HTTP (404 sur `/api/collection/{id}` pour l'utilisateur B) revient au lot qui
posera les routes de collection.
"""

import uuid

from sqlalchemy import select

from pbm_api.models import Card, Set, User
from pbm_api.models.collection import CollectionItem


async def test_collection_query_scoped_by_user_id_excludes_other_users(db_session):
    user_a = User(email=f"user-a-{uuid.uuid4()}@example.com", password_hash="x")
    user_b = User(email=f"user-b-{uuid.uuid4()}@example.com", password_hash="x")
    db_session.add_all([user_a, user_b])

    set_row = Set(code=f"iso-{uuid.uuid4().hex[:8]}", name="Set isolation")
    db_session.add(set_row)
    await db_session.flush()
    card = Card(set_id=set_row.id, number="1", name="Carte isolation")
    db_session.add(card)
    await db_session.flush()

    item_a = CollectionItem(user_id=user_a.id, card_id=card.id, language="fr")
    item_b = CollectionItem(user_id=user_b.id, card_id=card.id, language="fr")
    db_session.add_all([item_a, item_b])
    await db_session.flush()

    result = await db_session.execute(
        select(CollectionItem).where(CollectionItem.user_id == user_a.id)
    )
    items_for_a = result.scalars().all()

    assert {item.id for item in items_for_a} == {item_a.id}
    assert item_b.id not in {item.id for item in items_for_a}
