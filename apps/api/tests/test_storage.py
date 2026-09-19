"""`pbm_api.storage` (lot `v3-upload`) : le lot `v1-profil` y ajoute `delete` (suppression de
l'avatar remplacé ou du compte) sur les deux implémentations — sans test dédié jusqu'ici, la
méthode n'était exercée qu'indirectement via `tests/test_uploads.py` pour `put`/`get`.
"""

import pytest

from pbm_api.s3 import ObjectStorage
from pbm_api.storage.local import LocalObjectStorage


async def test_local_storage_delete_removes_the_file(tmp_path) -> None:
    storage = LocalObjectStorage(root=str(tmp_path))
    await storage.put("avatars/u1.jpg", b"hello-local", "image/jpeg")
    assert await storage.get("avatars/u1.jpg") == b"hello-local"

    await storage.delete("avatars/u1.jpg")
    assert await storage.get("avatars/u1.jpg") is None


async def test_local_storage_delete_of_a_missing_key_does_not_raise(tmp_path) -> None:
    storage = LocalObjectStorage(root=str(tmp_path))
    await storage.delete("avatars/never-existed.jpg")


async def test_local_storage_rejects_path_traversal(tmp_path) -> None:
    storage = LocalObjectStorage(root=str(tmp_path))
    with pytest.raises(ValueError):
        await storage.put("../escape.jpg", b"x", "image/jpeg")


async def test_s3_storage_delete_removes_the_object() -> None:
    storage = ObjectStorage()
    await storage.ensure_bucket()
    await storage.put("avatars/s3-delete.jpg", b"hello-s3", "image/jpeg")
    assert await storage.get("avatars/s3-delete.jpg") == b"hello-s3"

    await storage.delete("avatars/s3-delete.jpg")
    assert await storage.get("avatars/s3-delete.jpg") is None
