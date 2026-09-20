"""Filtre anti-fuite de clé IA dans les journaux (mission #3 du lot `v1-byok`).

Avant ce lot, `pbm_api.security.log_filter` n'existait pas : ces tests échouent à l'import
et passent une fois le module posé. Un test échoue explicitement si une clé apparaît dans
un enregistrement de log une fois le filtre installé.
"""

import logging

from pbm_api.security.log_filter import (
    install_api_key_redaction,
    install_secret_url_redaction,
    redact,
    redact_secret_urls,
)

ANTHROPIC_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"
OPENAI_KEY = "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789"
GEMINI_KEY = "AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz012345"
EXPORT_DOWNLOAD_TOKEN = "AbC123-xyz_9DeF0" * 3  # forme `secrets.token_urlsafe`
UPLOAD_RAW_TOKEN = "1758360000.4f0a1c9b2e8d7f6a5c3b1e0d9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a"


def test_redact_masks_anthropic_key() -> None:
    text = f"appel avec la clé {ANTHROPIC_KEY} refusé"
    assert ANTHROPIC_KEY not in redact(text)


def test_redact_masks_openai_key() -> None:
    text = f"clé {OPENAI_KEY} invalide"
    assert OPENAI_KEY not in redact(text)


def test_redact_masks_gemini_key() -> None:
    text = f"clé {GEMINI_KEY} invalide"
    assert GEMINI_KEY not in redact(text)


def test_redact_leaves_unrelated_text_untouched() -> None:
    text = "connexion à la base réussie"
    assert redact(text) == text


def test_installed_filter_masks_a_key_logged_via_a_named_logger(caplog) -> None:
    """Un logger nommé (pas seulement `root`) doit aussi être couvert : `setLogRecordFactory`
    agit à la création de l'enregistrement, avant toute question de propagation."""
    install_api_key_redaction()
    logger = logging.getLogger("pbm_api.ai.providers")

    with caplog.at_level(logging.ERROR):
        logger.error("échec de l'appel avec la clé %s", ANTHROPIC_KEY)

    assert ANTHROPIC_KEY not in caplog.text
    assert "***CLE_IA_MASQUEE***" in caplog.text


def test_redact_secret_urls_masks_export_download_token() -> None:
    text = f'"GET /export/download?token={EXPORT_DOWNLOAD_TOKEN} HTTP/1.1" 200'
    assert EXPORT_DOWNLOAD_TOKEN not in redact_secret_urls(text)


def test_redact_secret_urls_masks_local_upload_raw_token() -> None:
    text = f'"PUT /uploads/2f6e.../raw?token={UPLOAD_RAW_TOKEN} HTTP/1.1" 204'
    assert UPLOAD_RAW_TOKEN not in redact_secret_urls(text)


def test_redact_secret_urls_leaves_unrelated_text_untouched() -> None:
    text = '"GET /me/collection?sort=value_desc HTTP/1.1" 200'
    assert redact_secret_urls(text) == text


def test_installed_url_filter_masks_a_token_logged_via_uvicorn_access(caplog) -> None:
    """Reproduit la forme réelle du format d'accès d'uvicorn : la ligne de requête complète
    (chemin + query string) part comme un seul argument `%s`, jamais le jeton isolé — c'est
    cette ligne entière que `redact_secret_urls` doit nettoyer."""
    install_secret_url_redaction()
    logger = logging.getLogger("uvicorn.access")
    request_line = f"GET /export/download?token={EXPORT_DOWNLOAD_TOKEN} HTTP/1.1"

    with caplog.at_level(logging.INFO):
        logger.info('%s - "%s" %d', "127.0.0.1:12345", request_line, 200)

    assert EXPORT_DOWNLOAD_TOKEN not in caplog.text
    assert "***JETON_MASQUE***" in caplog.text
