import pytest

from pbm_api.config import Settings

_ENV = ("DATABASE_URL", "TEST_DATABASE_URL", "REDIS_URL", "S3_ENDPOINT_URL", "SMTP_PORT")


def test_defaults_match_shared_dev_infra(monkeypatch: pytest.MonkeyPatch) -> None:
    """Les valeurs par défaut doivent pointer l'infra partagée `pbm-shared` sans .env.

    La CI (et chaque lot) surcharge ces variables : on les retire
    pour lire les vraies valeurs par défaut.
    """
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert ":55432/" in settings.database_url
    assert settings.redis_url == "redis://localhost:56379/0"
    assert settings.s3_endpoint_url == "http://localhost:59000"
    assert settings.smtp_port == 51025
