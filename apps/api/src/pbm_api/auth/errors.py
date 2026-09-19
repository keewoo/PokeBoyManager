"""Erreurs du domaine authentification — traduites en réponses HTTP par le routeur."""


class PasswordTooShortError(Exception):
    pass


class PasswordCompromisedError(Exception):
    pass


class InvalidCredentialsError(Exception):
    """E-mail inconnu ou mot de passe erroné — toujours le même message, sans distinction."""


class RateLimitedError(Exception):
    pass


class InvalidTokenError(Exception):
    pass


class TokenExpiredError(Exception):
    pass


class TokenAlreadyUsedError(Exception):
    pass


class TermsNotAcceptedError(Exception):
    """Case « J'accepte les conditions » non cochée."""


class InvalidBirthDateError(Exception):
    """Date de naissance absente ou dans le futur."""


class UnderageWithoutParentalConsentError(Exception):
    """Moins de 15 ans sur l'inscription libre — RGPD art. 8 : seul un compte créé par
    l'administrateur (consentement du parent porté par JF) peut couvrir ce cas."""
