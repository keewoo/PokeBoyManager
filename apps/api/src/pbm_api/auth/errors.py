"""Erreurs du domaine authentification — traduites en réponses HTTP par le routeur."""


class PasswordTooShortError(Exception):
    """Mot de passe plus court que la politique en vigueur — traduite en 400."""

    pass


class PasswordCompromisedError(Exception):
    """Mot de passe trouvé dans une fuite connue (HIBP) — traduite en 400."""

    pass


class InvalidCredentialsError(Exception):
    """E-mail inconnu ou mot de passe erroné — toujours le même message, sans distinction."""


class RateLimitedError(Exception):
    """Débit dépassé — réservée à cet usage, le limiteur en place renvoie un booléen que
    le routeur traduit lui-même en 429 sans passer par cette exception."""

    pass


class InvalidTokenError(Exception):
    """Jeton d'e-mail (vérification ou réinitialisation) inconnu — traduite en 400."""

    pass


class TokenExpiredError(Exception):
    """Jeton d'e-mail trouvé mais au-delà de sa durée de vie — traduite en 400."""

    pass


class TokenAlreadyUsedError(Exception):
    """Jeton d'e-mail déjà consommé — un jeton ne sert qu'une fois ; traduite en 400."""

    pass


class TermsNotAcceptedError(Exception):
    """Case « J'accepte les conditions » non cochée."""


class InvalidBirthDateError(Exception):
    """Date de naissance absente ou dans le futur."""


class UnderageWithoutParentalConsentError(Exception):
    """Moins de 15 ans sur l'inscription libre — RGPD art. 8 : seul un compte créé par
    l'administrateur (consentement du parent porté par JF) peut couvrir ce cas."""
