class CollectionItemNotFoundError(Exception):
    """Aucun exemplaire avec cet id pour cet utilisateur (jamais un 403 : pas de fuite
    d'existence, même règle que `pbm_api.validation.errors.DetectionNotFoundError`)."""
