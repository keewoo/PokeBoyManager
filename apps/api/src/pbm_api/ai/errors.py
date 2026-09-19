class ProviderKeyNotFoundError(Exception):
    """Aucune clé enregistrée pour ce fournisseur, pour cet utilisateur."""


class DefaultProviderWithoutKeyError(Exception):
    """Le fournisseur par défaut choisi n'a pas de clé enregistrée."""
