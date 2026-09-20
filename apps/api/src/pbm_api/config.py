from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valeurs de développement présentes en clair dans le dépôt (`config.py`, `.env.example`) :
# tolérées hors production, INTERDITES dès `APP_ENV=production` (voir `_refuse_dev_defaults`).
_DEV_SECRET_KEY = "dev-only-change-me-in-production"
_DEV_AI_KEY_ENCRYPTION_KEY = "bo8a8UxneCy51yL6Mhan73p0Yxh+tKGlj4cIAbrfRvo="


class Settings(BaseSettings):
    """Configuration lue depuis l'environnement — un lot pointe sa propre base/bucket."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Environnement de déploiement (lot `pbm-deploy`) : "development" (défaut, dev/CI/e2e) ou
    # "production". En production, les secrets de développement font REFUSER le démarrage
    # (`_refuse_dev_defaults`) — une plateforme servie avec la clé publique du dépôt aurait des
    # jetons CSRF forgeables et un coffre de clés IA déchiffrable par quiconque lit le dépôt.
    app_env: str = "development"

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
    # Origine de l'API elle-même (lot v5-rgpd) : le lien de téléchargement d'export envoyé par
    # e-mail pointe directement dessus (pas de session requise, juste le jeton signé dans l'URL)
    # — `app_public_url` désigne `apps/web`, une origine distincte.
    api_public_url: str = "http://localhost:8000"

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

    # --- Stockage des photos (lots v3-upload, v1-profil) ---
    # D7 : deux implémentations de stockage — "s3" (MinIO en dev/CI, Object Storage en ligne)
    # ou "local" (disque du serveur en UAT/PROD, `PHOTOS_STORAGE_PATH`). Voir `pbm_api.storage`.
    # Sert les photos de cartes (v3-upload) et l'avatar utilisateur (v1-profil).
    storage_backend: str = "s3"
    photos_storage_path: str = "./var/photos"
    upload_max_size_bytes: int = 20 * 1024 * 1024
    upload_max_files_per_batch: int = 30

    # --- Pré-génération par lots des anecdotes/étude en jeu (lot v4-insights-batch) ---
    # Clé PLATEFORME distincte de toute clé d'utilisateur (D4 révisée, 19/09) — jamais une clé
    # de `ai_credentials`. Vide par défaut : sans elle, `insights_batch.runner` refuse de
    # soumettre un lot réel (fermé par défaut, jamais un envoi silencieux à vide). À fournir par
    # JF hors dépôt (variable d'environnement) avant tout passage réel.
    platform_anthropic_api_key: str = ""
    # Plafond de dépense en euros pour l'ensemble des passages cumulés (suivi dans
    # `var/insights_batch/ledger.json`, voir `pbm_api.insights_batch.ledger`) — 0 = aucun
    # passage réel autorisé (valeur de dev). À fournir par JF (décision D4, "budget à
    # plafonner").
    insights_budget_eur: float = 0.0
    # Modèle Anthropic par défaut du lot : Haiku 4.5, le moins cher des deux tarifs vérifiés le
    # 20/09/2026 sur claude.com/pricing (0,50 $/2,50 $ le Mtok en entrée/sortie une fois la
    # remise Batch de 50 % appliquée, contre 1 $/5 $ pour Sonnet 5) — un texte d'anecdotes/étude
    # en jeu ne demande pas le modèle le plus capable, et le catalogue complet se compte en
    # dizaines de milliers de cartes.
    insights_batch_model: str = "claude-haiku-4-5"
    # Nombre de cartes par lot Anthropic soumis en une fois — très en-deçà de la limite réelle
    # (100 000 requêtes ou 256 Mo, vérifié le 20/09/2026 sur platform.claude.com/docs) : garde
    # chaque lot rapide à traiter et à reprendre, et fait coïncider la taille d'un lot avec la
    # mesure de coût sur 100 cartes exigée par la mission.
    insights_batch_chunk_size: int = 100
    # Intervalle et nombre max de sondages du statut d'un lot Anthropic (`processing_status`) —
    # la doc indique la plupart des lots terminés en moins d'une heure ; 90×20s = 30 min avant
    # d'abandonner et de laisser reprendre le lot au prochain lancement (`results_url` reste
    # valable, l'identifiant du lot est repris depuis le fichier de reprise).
    insights_batch_poll_interval_seconds: int = 20
    insights_batch_poll_max_attempts: int = 90

    # --- Parcours e2e complet (lot v5-e2e) ---
    # Faux par défaut, jamais à activer en UAT/PROD : bascule `pbm_api.ai.factory.create_provider`
    # sur `pbm_api.ai.simulated_provider.SimulatedProvider` (aucun appel réseau, réponses
    # déterministes) pour que l'e2e Playwright fasse tourner le vrai pipeline de reconnaissance
    # (détection + identification, `pbm_api.worker.detect_cards_task`) sans clé IA réelle — aucune
    # disponible sur chimera (voir CLAUDE.md).
    ai_simulated_provider: bool = False

    @model_validator(mode="after")
    def _refuse_dev_defaults(self) -> "Settings":
        """En production, aucune valeur de développement ne doit rester active (lot `pbm-deploy`,
        exigence de la mission : « l'application doit refuser de démarrer avec une clé secrète de
        développement »). Silencieux hors production pour ne pas gêner dev/CI/e2e, qui utilisent
        délibérément ces défauts."""
        if self.app_env.strip().lower() not in {"production", "prod"}:
            return self
        offenders: list[str] = []
        if self.secret_key == _DEV_SECRET_KEY:
            offenders.append("SECRET_KEY")
        if self.ai_key_encryption_key == _DEV_AI_KEY_ENCRYPTION_KEY:
            offenders.append("AI_KEY_ENCRYPTION_KEY")
        if self.ai_simulated_provider:
            offenders.append("AI_SIMULATED_PROVIDER (fournisseur IA simulé, jamais en production)")
        if offenders:
            raise ValueError(
                "APP_ENV=production interdit les valeurs de développement : "
                + ", ".join(offenders)
                + " — à définir par variable d'environnement hors dépôt."
            )
        return self


settings = Settings()
