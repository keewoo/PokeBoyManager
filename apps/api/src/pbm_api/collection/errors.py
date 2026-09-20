class CollectionItemNotFoundError(Exception):
    """Aucun exemplaire avec cet id pour cet utilisateur (jamais un 403 : pas de fuite
    d'existence, même règle que `pbm_api.validation.errors.DetectionNotFoundError`)."""


class CollectionItemPhotoMissingError(Exception):
    """L'exemplaire existe mais n'a pas de photo (ajout manuel) ou son objet a disparu du
    stockage — même distinction que `pbm_api.uploads.errors.DetectionCropMissingError`."""
