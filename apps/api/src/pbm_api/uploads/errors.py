class TooManyFilesError(Exception):
    """Plus de `upload_max_files_per_batch` fichiers dans un même envoi (mission point 2)."""


class InvalidFileError(Exception):
    """Type déclaré non accepté ou taille annoncée au-delà de `upload_max_size_bytes`."""

    def __init__(self, filename: str, reason: str) -> None:
        self.filename = filename
        self.reason = reason
        super().__init__(f"{filename}: {reason}")


class UploadNotFoundError(Exception):
    """Aucun envoi avec cet id pour cet utilisateur (jamais un 403 : pas de fuite d'existence)."""


class UploadAlreadyProcessedError(Exception):
    """`complete` appelé une seconde fois sur le même envoi."""


class UploadRawMissingError(Exception):
    """`complete` appelé avant que les octets bruts n'aient été reçus par le stockage."""
