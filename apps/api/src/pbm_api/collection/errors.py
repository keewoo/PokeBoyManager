"""Erreurs du domaine collection : signalées pour que l'API réponde 404 sans jamais révéler si
l'exemplaire existe pour un autre utilisateur ou n'existe pas du tout."""


class CollectionItemNotFoundError(Exception):
    """Aucun exemplaire avec cet id pour cet utilisateur (jamais un 403 : pas de fuite
    d'existence, même règle que `pbm_api.validation.errors.DetectionNotFoundError`)."""


class CollectionItemPhotoMissingError(Exception):
    """L'exemplaire existe mais n'a pas de photo (ajout manuel) ou son objet a disparu du
    stockage — même distinction que `pbm_api.uploads.errors.DetectionCropMissingError`."""
