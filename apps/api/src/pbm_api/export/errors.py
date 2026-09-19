class ExportNotFoundError(Exception):
    """Aucun export avec cet id pour l'utilisateur courant (accès croisé inclus)."""


class ExportTokenInvalidError(Exception):
    """Jeton de téléchargement inconnu, déjà consommé par une autre demande, ou expiré (24 h)."""


class ExportArchiveMissingError(Exception):
    """Export marqué `succeeded` en base mais l'archive a disparu du stockage."""
