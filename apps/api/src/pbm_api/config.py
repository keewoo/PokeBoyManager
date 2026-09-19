from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration lue depuis l'environnement — un lot pointe sa propre base/bucket."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_auth"
    redis_url: str = "redis://localhost:56379/0"
    redis_prefix: str = "pbm:v1-auth:"

    s3_endpoint_url: str = "http://localhost:59000"
    s3_access_key: str = "pbm"
    s3_secret_key: str = "pbmpbmpbm"
    s3_bucket: str = "pbm-v1-auth"
    s3_region: str = "us-east-1"

    smtp_host: str = "localhost"
    smtp_port: int = 51025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@pokeboymanager.local"

    # --- Comptes (lot v1-auth) ---
    # Valeur de dev uniquement : aucun secret réel, à surcharger par variable d'environnement
    # en UAT/PROD (signe les jetons CSRF, dérivés du cookie de session).
    secret_key: str = "dev-only-change-me-in-production"
    app_public_url: str = "http://localhost:3000"

    session_cookie_name: str = "pbm_session"
    csrf_cookie_name: str = "pbm_csrf"
    session_ttl_days: int = 30
    email_token_ttl_minutes: int = 60

    login_rate_limit_max_attempts: int = 5
    login_rate_limit_window_seconds: int = 900


settings = Settings()
