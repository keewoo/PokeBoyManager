"""Filtre anti-fuite de clé IA dans les journaux (mission #3 du lot `v1-byok`).

Avant ce lot, `pbm_api.security.log_filter` n'existait pas : ces tests échouent à l'import
et passent une fois le module posé. Un test échoue explicitement si une clé apparaît dans
un enregistrement de log une fois le filtre installé.
"""

import logging

from pbm_api.security.log_filter import install_api_key_redaction, redact

ANTHROPIC_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"
OPENAI_KEY = "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789"
GEMINI_KEY = "AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz012345"


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
