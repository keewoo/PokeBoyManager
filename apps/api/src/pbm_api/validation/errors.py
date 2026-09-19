class DetectionNotFoundError(Exception):
    """Aucune détection avec cet id pour un envoi de cet utilisateur (jamais un 403 : pas de
    fuite d'existence)."""


class DetectionAlreadyProcessedError(Exception):
    """`confirm`/`reject` appelé sur une détection déjà validée ou rejetée."""


class CardNotFoundError(Exception):
    """`card_id` soumis à `confirm` introuvable au catalogue."""
