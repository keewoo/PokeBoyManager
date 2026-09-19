from pbm_api.config import Settings


def test_defaults_match_shared_dev_infra() -> None:
    """Les valeurs par défaut doivent pointer l'infra partagée `pbm-shared` sans .env."""
    settings = Settings(_env_file=None)
    assert ":55432/" in settings.database_url
    assert settings.redis_url == "redis://localhost:56379/0"
    assert settings.s3_endpoint_url == "http://localhost:59000"
    assert settings.smtp_port == 51025
