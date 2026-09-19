"""Stockage des photos (D7) : deux implémentations, choisies par `STORAGE_BACKEND`.

- `s3` (défaut, MinIO en dev/CI, Object Storage en ligne) : `pbm_api.s3.ObjectStorage`, déjà
  utilisé par le proxy d'images du catalogue.
- `local` (UAT/PROD, disque du serveur) : `pbm_api.storage.local.LocalObjectStorage`.

Aucune fonctionnalité ne doit supposer l'une ou l'autre : le code applicatif (routeurs
`uploads`, `profile`) ne connaît que le protocole `get`/`put`/`delete`/`ensure_bucket` commun
aux deux.
"""

from pbm_api.config import settings
from pbm_api.s3 import ObjectStorage
from pbm_api.storage.local import LocalObjectStorage

StorageBackend = ObjectStorage | LocalObjectStorage


def build_storage() -> StorageBackend:
    if settings.storage_backend == "local":
        return LocalObjectStorage()
    return ObjectStorage()


__all__ = ["StorageBackend", "build_storage", "LocalObjectStorage", "ObjectStorage"]
