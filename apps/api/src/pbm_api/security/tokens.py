"""Jetons opaques : générés côté serveur, seul leur hash SHA-256 est stocké en base.

Vaut aussi bien pour les jetons de session (cookie) que pour les jetons d'e-mail
(vérification, réinitialisation) : le jeton en clair ne transite qu'une fois
(cookie ou lien d'e-mail), jamais journalisé, jamais relisible depuis la base.
"""

import hashlib
import secrets


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
