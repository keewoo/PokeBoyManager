"""Stockage disque local (D7 : `STORAGE_BACKEND=local`, cible UAT/PROD sans Docker).

Même surface async que `pbm_api.s3.ObjectStorage` (`get`/`put`/`ensure_bucket`) pour que le
reste de l'application ignore quel backend est actif. Pas de notion de bucket sur un disque :
`ensure_bucket` crée simplement le répertoire racine.
"""

import asyncio
from pathlib import Path

from pbm_api.config import settings


class LocalObjectStorage:
    def __init__(self, root: str | None = None) -> None:
        self._root = Path(root or settings.photos_storage_path)

    def _path_for(self, key: str) -> Path:
        # `key` est toujours construit côté serveur (jamais depuis une entrée utilisateur brute
        # au-delà d'un UUID) — pas de composant ".." possible, mais on le refuse quand même.
        if ".." in Path(key).parts:
            raise ValueError(f"clé de stockage invalide : {key!r}")
        return self._root / key

    def _ensure_bucket_sync(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    async def ensure_bucket(self) -> None:
        await asyncio.to_thread(self._ensure_bucket_sync)

    def _get_sync(self, key: str) -> bytes | None:
        path = self._path_for(key)
        if not path.is_file():
            return None
        return path.read_bytes()

    async def get(self, key: str) -> bytes | None:
        return await asyncio.to_thread(self._get_sync, key)

    def _put_sync(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(self._put_sync, key, data, content_type)

    def _delete_sync(self, key: str) -> None:
        self._path_for(key).unlink(missing_ok=True)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._delete_sync, key)
