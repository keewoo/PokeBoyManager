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
