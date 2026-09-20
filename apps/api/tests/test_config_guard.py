"""Garde de démarrage (lot `pbm-deploy`) : en production, les secrets de développement présents
en clair dans le dépôt doivent faire ÉCHOUER la construction de `Settings` — la mission l'exige
(« l'application doit refuser de démarrer avec une clé secrète de développement »). Hors
production, ces défauts restent tolérés (dev/CI/e2e les utilisent délibérément)."""

import pytest
from pydantic import ValidationError

from pbm_api.config import Settings

_REAL_SECRET = "x" * 40
_REAL_AI_KEY = "y" * 44


def test_production_refuses_dev_secret_key():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            secret_key="dev-only-change-me-in-production",
            ai_key_encryption_key=_REAL_AI_KEY,
        )


def test_production_refuses_dev_ai_key_encryption_key():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            secret_key=_REAL_SECRET,
            ai_key_encryption_key="bo8a8UxneCy51yL6Mhan73p0Yxh+tKGlj4cIAbrfRvo=",
        )


def test_production_refuses_simulated_provider():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            secret_key=_REAL_SECRET,
            ai_key_encryption_key=_REAL_AI_KEY,
            ai_simulated_provider=True,
        )


def test_production_accepts_real_secrets():
    settings = Settings(
        _env_file=None,
        app_env="production",
        secret_key=_REAL_SECRET,
        ai_key_encryption_key=_REAL_AI_KEY,
        ai_simulated_provider=False,
    )
    assert settings.app_env == "production"


def test_development_allows_dev_defaults():
    settings = Settings(_env_file=None, app_env="development")
    assert settings.secret_key == "dev-only-change-me-in-production"
