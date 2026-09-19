"""Chiffrement enveloppe des clés IA (AES-256-GCM, `user_id` en données associées).

Avant ce lot, `pbm_api.security.crypto` n'existait pas : ces tests échouent à l'import et
passent une fois le module posé.
"""

import uuid

import pytest
from cryptography.exceptions import InvalidTag

from pbm_api.security.crypto import decrypt_api_key, encrypt_api_key, mask_api_key

RAW_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"


def test_encrypt_then_decrypt_roundtrips_for_the_same_user() -> None:
    user_id = uuid.uuid4()
    ciphertext, nonce = encrypt_api_key(RAW_KEY, user_id)

    assert ciphertext != RAW_KEY.encode("utf-8")
    assert RAW_KEY.encode("utf-8") not in ciphertext

    assert decrypt_api_key(ciphertext, nonce, user_id) == RAW_KEY


def test_decrypt_fails_when_user_id_does_not_match_the_one_used_to_encrypt() -> None:
    """Une clé copiée dans un autre compte (ou une ligne mal filtrée) ne se déchiffre pas :
    `user_id` fait partie des données associées, l'étiquette d'authentification GCM ne
    correspond plus."""
    owner_id, other_user_id = uuid.uuid4(), uuid.uuid4()
    ciphertext, nonce = encrypt_api_key(RAW_KEY, owner_id)

    with pytest.raises(InvalidTag):
        decrypt_api_key(ciphertext, nonce, other_user_id)


def test_encrypt_uses_a_fresh_nonce_each_time() -> None:
    user_id = uuid.uuid4()
    ciphertext_1, nonce_1 = encrypt_api_key(RAW_KEY, user_id)
    ciphertext_2, nonce_2 = encrypt_api_key(RAW_KEY, user_id)

    assert nonce_1 != nonce_2
    assert ciphertext_1 != ciphertext_2


def test_mask_api_key_never_exposes_the_middle_of_the_key() -> None:
    mask = mask_api_key(RAW_KEY)

    assert mask.startswith("sk-ant-a")
    assert mask.endswith("6789")
    assert RAW_KEY[10:-4] not in mask


def test_mask_api_key_handles_very_short_input_without_raising() -> None:
    mask = mask_api_key("short")
    assert "short" not in mask
