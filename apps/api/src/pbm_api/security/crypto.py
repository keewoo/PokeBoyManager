"""Chiffrement enveloppe des clés IA — AES-256-GCM, `user_id` en données associées.

La clé maître ne vit jamais en base : `settings.ai_key_encryption_key`, à fournir par
variable d'environnement en dehors du dépôt pour tout déploiement (la valeur par défaut est
un secret de développement, sans portée hors de cette machine). Rotation : déchiffrer chaque
`ai_credentials` avec l'ancienne clé maître puis rechiffrer avec la nouvelle — aucune clé en
clair journalisée pendant l'opération.

`user_id` comme données associées (AAD) lie le chiffré au compte : une ligne copiée dans un
autre compte (ou une tentative de déchiffrement avec un mauvais `user_id`) échoue avec
`cryptography.exceptions.InvalidTag`, jamais un déchiffrement silencieux incorrect.
"""

import base64
import os
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from pbm_api.config import settings

_NONCE_SIZE_BYTES = 12
_MASK_SEPARATOR = "…"


def _master_key() -> bytes:
    return base64.b64decode(settings.ai_key_encryption_key)


def _associated_data(user_id: uuid.UUID) -> bytes:
    return str(user_id).encode("utf-8")


def encrypt_api_key(plaintext: str, user_id: uuid.UUID) -> tuple[bytes, bytes]:
    """Renvoie `(chiffré, nonce)`. Le nonce est aléatoire à chaque appel — jamais réutilisé
    avec la même clé maître, condition de sécurité d'AES-GCM."""
    aesgcm = AESGCM(_master_key())
    nonce = os.urandom(_NONCE_SIZE_BYTES)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), _associated_data(user_id))
    return ciphertext, nonce


def decrypt_api_key(ciphertext: bytes, nonce: bytes, user_id: uuid.UUID) -> str:
    """Lève `cryptography.exceptions.InvalidTag` si `user_id` ne correspond pas au chiffré
    d'origine, ou si la clé maître a changé sans rotation préalable."""
    aesgcm = AESGCM(_master_key())
    plaintext = aesgcm.decrypt(nonce, ciphertext, _associated_data(user_id))
    return plaintext.decode("utf-8")


def mask_api_key(raw: str) -> str:
    """Masque présentable côté API (ex: `sk-ant-a…4f2a`) — jamais la clé en clair."""
    if len(raw) <= 8:
        return f"{_MASK_SEPARATOR}{raw[-2:]}"
    return f"{raw[:8]}{_MASK_SEPARATOR}{raw[-4:]}"
