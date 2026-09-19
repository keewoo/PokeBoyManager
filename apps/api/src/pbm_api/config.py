from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration lue depuis l'environnement — un lot pointe sa propre base/bucket."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v0_schema"
    redis_url: str = "redis://localhost:56379/0"
    redis_prefix: str = "pbm:v0-schema:"

    s3_endpoint_url: str = "http://localhost:59000"
    s3_access_key: str = "pbm"
    s3_secret_key: str = "pbmpbmpbm"
    s3_bucket: str = "pbm-v0-schema"
    s3_region: str = "us-east-1"

    smtp_host: str = "localhost"
    smtp_port: int = 51025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@pokeboymanager.local"


settings = Settings()
