"""Filtres de journalisation qui masquent les secrets avant qu'ils n'atteignent un journal.

Installés au démarrage (`main.py`) via `logging.setLogRecordFactory` : la redaction s'applique
à la création de chaque `LogRecord`, quel que soit le logger d'origine (`uvicorn.access`,
`uvicorn.error`, bibliothèques tierces...). Un simple `logger.addFilter(...)` sur le logger
racine n'aurait couvert que les messages émis directement sur ce logger — pas ceux d'un logger
nommé qui se contente de propager vers root, cas le plus courant en pratique. Les deux
installateurs chaînent leur fabrique à celle déjà en place (`logging.getLogRecordFactory()` au
moment de l'appel) : appeler les deux au démarrage applique les deux redactions, dans l'ordre
d'installation.
"""

import logging
import re
from collections.abc import Callable

# --- Clés IA (Anthropic, OpenAI, Google) — lot v1-byok ------------------------------------

_KEY_PATTERNS = (
    # Anthropic d'abord : générique `sk-...` matcherait sinon une partie de `sk-ant-...` et
    # laisserait un reliquat masqué mais reconnaissable.
    re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AIza[A-Za-z0-9_-]{20,}"),
)
_KEY_MASK = "***CLE_IA_MASQUEE***"


def redact(text: str) -> str:
    for pattern in _KEY_PATTERNS:
        text = pattern.sub(_KEY_MASK, text)
    return text


def install_api_key_redaction() -> None:
    _install_redaction(redact)


# --- Jetons portés par l'URL elle-même — lot v5-securite -----------------------------------
#
# Le lien de téléchargement d'export (`GET /export/download?token=...`, `pbm_api.export`) et
# le jeton d'envoi du backend de stockage local (`PUT /uploads/{id}/raw?token=...`,
# `pbm_api.security.upload_tokens`) portent leur secret dans la query string plutôt que dans un
# cookie. `uvicorn.access` journalise la ligne de requête complète (chemin + query string) :
# sans cette redaction, ces jetons finiraient en clair dans les journaux malgré leur portée
# volontairement limitée (une seule ressource, durée bornée). Les deux formes
# (`secrets.token_urlsafe`, et `epoch.hexsig` d'`upload_tokens.py`) tiennent dans un seul motif
# générique sur la valeur du paramètre `token`.

_TOKEN_QUERY_PATTERN = re.compile(r"(?<=[?&]token=)[A-Za-z0-9_.\-]{8,}")
_TOKEN_MASK = "***JETON_MASQUE***"


def redact_secret_urls(text: str) -> str:
    return _TOKEN_QUERY_PATTERN.sub(_TOKEN_MASK, text)


def install_secret_url_redaction() -> None:
    _install_redaction(redact_secret_urls)


def _install_redaction(redact_fn: Callable[[str], str]) -> None:
    original_factory = logging.getLogRecordFactory()

    def factory(*args, **kwargs) -> logging.LogRecord:
        record = original_factory(*args, **kwargs)
        if isinstance(record.msg, str):
            record.msg = redact_fn(record.msg)
        if isinstance(record.args, dict):
            record.args = {
                key: redact_fn(value) if isinstance(value, str) else value
                for key, value in record.args.items()
            }
        elif isinstance(record.args, tuple):
            record.args = tuple(
                redact_fn(arg) if isinstance(arg, str) else arg for arg in record.args
            )
        return record

    logging.setLogRecordFactory(factory)
