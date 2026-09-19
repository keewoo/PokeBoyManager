"""Contrôle d'un mot de passe contre les fuites connues, par k-anonymat (HIBP).

Seuls les 5 premiers caractères du hash SHA-1 du mot de passe quittent le serveur — jamais
le mot de passe, jamais son hash complet. Voir https://haveibeenpwned.com/API/v3#PwnedPasswords.
"""

import hashlib
import logging

import httpx

logger = logging.getLogger(__name__)

HIBP_RANGE_URL = "https://api.pwnedpasswords.com/range/{prefix}"


class CompromisedPasswordChecker:
    """Interrogeable en tant que dépendance FastAPI ; substituable dans les tests."""

    def __init__(self, timeout: float = 3.0) -> None:
        self._timeout = timeout

    async def is_compromised(self, password: str) -> bool:
        digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()  # noqa: S324 — HIBP impose SHA-1
        prefix, suffix = digest[:5], digest[5:]

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(HIBP_RANGE_URL.format(prefix=prefix))
                response.raise_for_status()
        except httpx.HTTPError:
            # Service tiers indisponible : on ne bloque pas l'inscription/réinitialisation
            # sur une panne externe, mais ce n'est pas un repli silencieux — c'est journalisé.
            logger.warning("hibp_unreachable", exc_info=True)
            return False

        for line in response.text.splitlines():
            found_suffix, _, _count = line.partition(":")
            if found_suffix.strip() == suffix:
                return True
        return False


_default_checker = CompromisedPasswordChecker()


def get_compromised_checker() -> CompromisedPasswordChecker:
    return _default_checker
