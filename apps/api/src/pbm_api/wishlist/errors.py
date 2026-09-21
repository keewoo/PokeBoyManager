class WishlistItemNotFoundError(Exception):
    """Aucun vœu avec cet id pour cet utilisateur (jamais un 403 : pas de fuite d'existence,
    même règle que `pbm_api.collection.errors.CollectionItemNotFoundError`)."""


class WishlistItemAlreadyExistsError(Exception):
    """La carte figure déjà dans les vœux de l'utilisateur (`uq_wishlist_items_user_card`) —
    un second ajout ne crée jamais de doublon, `PATCH` sert à corriger le prix cible."""
