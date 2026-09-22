class DeckNotFoundError(Exception):
    """Aucun deck avec cet id pour cet utilisateur (jamais un 403 : pas de fuite d'existence,
    même règle que `pbm_api.collection.errors.CollectionItemNotFoundError`)."""


class DeckCardNotFoundError(Exception):
    """La carte visée n'est pas (ou plus) dans ce deck."""


class NoAiKeyForDeckError(Exception):
    """L'utilisateur n'a aucun fournisseur IA par défaut avec une clé (D4) : l'assistant de
    construction de deck (mission `v7-deck-ia`) reste indisponible tant qu'il n'en choisit pas un
    dans son profil — jamais une clé plateforme."""


class EmptyCollectionError(Exception):
    """Aucune carte possédée (hors Énergies de base) et dans le format du deck : l'assistant IA
    ne peut composer un deck « pris dans sa collection » à partir de rien (mission `v7-deck-ia`)."""
