"""Jeton signé pour `PUT /uploads/{id}/raw` — l'équivalent d'une URL présignée S3 quand le
backend est `local` (D7) : pas de service de stockage séparé à qui déléguer un vrai
présignage, donc l'API se présigne elle-même une URL vers sa propre route, à durée limitée,
sans dépendre du cookie de session (même contrat qu'un présignage S3 : quiconque détient
l'URL peut l'utiliser une fois, avant expiration).
"""

import hashlib
import hmac
import time
import uuid

from pbm_api.config import settings


def generate_upload_token(upload_id: uuid.UUID, expires_in: int = 900) -> str:
    expires_at = int(time.time()) + expires_in
    signature = _sign(upload_id, expires_at)
    return f"{expires_at}.{signature}"


def verify_upload_token(upload_id: uuid.UUID, token: str) -> bool:
    try:
        expires_at_raw, signature = token.split(".", 1)
        expires_at = int(expires_at_raw)
    except ValueError:
        return False
    if expires_at < int(time.time()):
        return False
    expected = _sign(upload_id, expires_at)
    return hmac.compare_digest(expected, signature)


def _sign(upload_id: uuid.UUID, expires_at: int) -> str:
    message = f"{upload_id}:{expires_at}".encode()
    return hmac.new(settings.secret_key.encode("utf-8"), message, hashlib.sha256).hexdigest()
