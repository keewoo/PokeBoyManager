"""Erreurs du module fiche carte, capturées par `pbm_api.routers.cards` pour rendre un 404."""


class CardNotFoundError(Exception):
    """Aucune carte avec cet id au catalogue."""
