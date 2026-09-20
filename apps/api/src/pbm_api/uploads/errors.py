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


class UploadTooLargeError(Exception):
    """L'objet déposé dans le stockage dépasse `upload_max_size_bytes` — détecté par
    `storage.head()` avant `get()` (mission `v5-securite` point 2) : le backend S3 n'a aucun
    moyen d'empêcher ce dépôt au moment du présignage, contrairement au backend local."""


class DetectionNotFoundError(Exception):
    """Aucune détection avec cet id pour cet envoi de cet utilisateur."""


class DetectionCropMissingError(Exception):
    """Le recadrage n'est plus dans le stockage (objet supprimé entre-temps)."""
