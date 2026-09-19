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

    # --- Coffre de clés IA (lot v1-byok) ---
    # Clé maître AES-256 (32 octets, base64), jamais en base : chiffre/déchiffre les clés IA
    # des utilisateurs. Valeur de dev uniquement — à définir par variable d'environnement hors
    # dépôt pour tout déploiement. Rotation : déchiffrer chaque `ai_credentials` avec l'ancienne
    # clé puis rechiffrer avec la nouvelle (aucune clé en clair journalisée pendant l'opération).
    ai_key_encryption_key: str = "bo8a8UxneCy51yL6Mhan73p0Yxh+tKGlj4cIAbrfRvo="

    # --- Envoi de photos (lot v3-upload) ---
    # D7 : deux implémentations de stockage — "s3" (MinIO en dev/CI, Object Storage en ligne)
    # ou "local" (disque du serveur en UAT/PROD, `PHOTOS_STORAGE_PATH`). Voir `pbm_api.storage`.
    storage_backend: str = "s3"
    photos_storage_path: str = "./var/photos"
    upload_max_size_bytes: int = 20 * 1024 * 1024
    upload_max_files_per_batch: int = 30


settings = Settings()
