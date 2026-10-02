"""Hachage des mots de passe (argon2id) et politique minimale de robustesse."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError

MIN_PASSWORD_LENGTH = 10

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hache avec Argon2id (sel et paramètres intégrés au résultat) — seul ce hash est
    stocké en base, jamais le mot de passe en clair."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Vérifie le mot de passe contre son hash ; False sur mauvais mot de passe ou hash
    corrompu/d'un autre format — jamais de levée qui distinguerait les deux cas à l'appelant."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHash):
        return False


def is_password_long_enough(password: str) -> bool:
    """Politique minimale de robustesse : au moins `MIN_PASSWORD_LENGTH` caractères."""
    return len(password) >= MIN_PASSWORD_LENGTH
