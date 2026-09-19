class DetectionSourceMissingError(Exception):
    """La photo source (`Upload.s3_key`) est introuvable dans le stockage — envoi non complété
    ou objet supprimé entre-temps."""
