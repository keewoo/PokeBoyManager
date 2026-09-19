"""Hachage des mots de passe (argon2id) et politique minimale de robustesse."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError

MIN_PASSWORD_LENGTH = 10

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHash):
        return False


def is_password_long_enough(password: str) -> bool:
    return len(password) >= MIN_PASSWORD_LENGTH
