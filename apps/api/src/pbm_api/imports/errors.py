class ImportFileEmptyError(Exception):
    """Le fichier envoyé n'a aucune ligne de données (en-tête seul ou fichier vide)."""


class ImportFileTooLargeError(Exception):
    """Dépasse `settings.import_csv_max_size_bytes`."""


class ImportTooManyRowsError(Exception):
    """Dépasse `settings.import_csv_max_rows` — un CSV de cette taille est probablement un
    mauvais export (pas la collection d'un particulier), jamais rapproché en partie en silence."""


class ImportFileUndecodableError(Exception):
    """Ni UTF-8 (avec ou sans BOM) ni Latin-1/CP1252 — les deux encodages observés sur les
    exports courants (Excel FR notamment) — n'ont pu décoder le fichier."""
