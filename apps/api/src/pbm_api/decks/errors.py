class DeckNotFoundError(Exception):
    """Aucun deck avec cet id pour cet utilisateur (jamais un 403 : pas de fuite d'existence,
    même règle que `pbm_api.collection.errors.CollectionItemNotFoundError`)."""


class DeckCardNotFoundError(Exception):
    """La carte visée n'est pas (ou plus) dans ce deck."""
