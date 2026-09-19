class PseudoAlreadyTakenError(Exception):
    """Un autre compte utilise déjà ce pseudo (contrainte `users.pseudo` unique)."""


class AvatarTooLargeError(Exception):
    """Photo au-delà de `pbm_api.profile.avatar.MAX_UPLOAD_BYTES`."""


class AvatarNotFoundError(Exception):
    """L'utilisateur n'a pas (ou plus) d'avatar enregistré."""


class SessionNotFoundError(Exception):
    """Aucune session avec cet identifiant pour l'utilisateur courant (accès croisé inclus)."""
