"""Filtre de journalisation qui masque tout motif de clé IA (Anthropic, OpenAI, Google).

Installé une fois au démarrage (`install_api_key_redaction()`, appelé par `main.py`) via
`logging.setLogRecordFactory` : la redaction s'applique à la création de chaque
`LogRecord`, quel que soit le logger d'origine (`uvicorn.access`, `uvicorn.error`,
bibliothèques tierces...). Un simple `logger.addFilter(...)` sur le logger racine n'aurait
couvert que les messages émis directement sur ce logger — pas ceux d'un logger nommé qui se
contente de propager vers root, cas le plus courant en pratique.

Aucune route ne doit journaliser une clé en clair : ce filet de sécurité couvre le cas non
prévu (traceback, message d'erreur d'une bibliothèque tierce qui inclurait la clé).
"""

import logging
import re

_KEY_PATTERNS = (
    # Anthropic d'abord : générique `sk-...` matcherait sinon une partie de `sk-ant-...` et
    # laisserait un reliquat masqué mais reconnaissable.
    re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AIza[A-Za-z0-9_-]{20,}"),
)

_MASK = "***CLE_IA_MASQUEE***"


def redact(text: str) -> str:
    for pattern in _KEY_PATTERNS:
        text = pattern.sub(_MASK, text)
    return text


def _redact_args(args):
    if isinstance(args, dict):
        return {
            key: redact(value) if isinstance(value, str) else value for key, value in args.items()
        }
    if isinstance(args, tuple):
        return tuple(redact(arg) if isinstance(arg, str) else arg for arg in args)
    return args


def install_api_key_redaction() -> None:
    original_factory = logging.getLogRecordFactory()

    def factory(*args, **kwargs) -> logging.LogRecord:
        record = original_factory(*args, **kwargs)
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = _redact_args(record.args)
        return record

    logging.setLogRecordFactory(factory)
