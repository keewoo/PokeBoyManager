import { defineConfig, devices } from "@playwright/test";

const WEB_PORT = 3100;
const API_PORT = 8100;
const MAILPIT_UI_PORT = process.env.MAILPIT_UI_PORT || "58025";

export const WEB_BASE_URL = `http://localhost:${WEB_PORT}`;
export const API_BASE_URL = `http://localhost:${API_PORT}`;
export const MAILPIT_BASE_URL = `http://localhost:${MAILPIT_UI_PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  // Un seul worker : tous les fichiers de specs partagent une unique instance API/DB/Redis/S3
  // (les trois entrées `webServer` ci-dessous), y compris le catalogue de démonstration
  // (`pbm_api.seed.DEMO_CARDS`, lot `v5-e2e`) — Playwright lance par défaut plusieurs workers en
  // parallèle sur des fichiers différents, ce qui fait cohabiter deux transactions concurrentes
  // sur la même carte de catalogue. Constaté le 20/09/2026 (lot `v5-e2e`) : un
  // `DeadlockDetectedError` Postgres entre le `confirm-all` du parcours complet et la validation
  // seedée d'un autre fichier, plus des timeouts sur des actions UI ordinaires — tout disparaît
  // en série.
  workers: 1,
  // Chimera héberge plusieurs lots autonomes en parallèle (`~/dev/lots/pbm-scheduler.sh`) : sous
  // charge partagée, une action DOM ordinaire peut dépasser les 30 s par défaut sans qu'il y ait
  // de régression (déjà noté par `v4-fiche` sur `auth.spec.ts`, confirmé à nouveau le 20/09/2026
  // sur les sept specs à la fois, `card-detail`/`validation` compris). La CI GitHub Actions fait
  // foi (runner dédié, sans cette contention) ; ce délai réduit seulement le bruit local.
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["html", { open: "never" }]] : "list",
  use: {
    baseURL: WEB_BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "uv run uvicorn pbm_api.main:app --host 0.0.0.0 --port " + API_PORT,
      cwd: "../api",
      url: `${API_BASE_URL}/health`,
      reuseExistingServer: !process.env.CI,
      env: {
        DATABASE_URL:
          process.env.E2E_DATABASE_URL ||
          "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_pages_auth_e2e",
        REDIS_URL: process.env.REDIS_URL || "redis://localhost:56379/0",
        REDIS_PREFIX: "pbm:v1-pages-auth:e2e:",
        SMTP_HOST: process.env.SMTP_HOST || "localhost",
        SMTP_PORT: process.env.SMTP_PORT || "51025",
        APP_PUBLIC_URL: WEB_BASE_URL,
        // Lot `v5-securite` limite désormais `/auth/register` (et `/auth/login`/`/auth/forgot`)
        // à `LOGIN_RATE_LIMIT_MAX_ATTEMPTS` tentatives par IP sur `LOGIN_RATE_LIMIT_WINDOW_
        // SECONDS` (5/900 s par défaut, `pbm_api.security.rate_limit.get_login_rate_limiter`,
        // un seul compteur Redis partagé par les trois routes). Toutes les specs e2e tournent
        // depuis la même IP (127.0.0.1) contre la même instance API : `auth`+`validation`+
        // `card-detail`+`parcours-complet` totalisent déjà 5 inscriptions dans une CI qui
        // repart de zéro — pile à la limite, sans marge pour la moindre reprise (`retries: 1`
        // en CI). Relevé ici pour cette seule instance e2e, jamais en UAT/PROD.
        LOGIN_RATE_LIMIT_MAX_ATTEMPTS: "50",
        // Lot `v5-e2e` (parcours complet) : bascule `pbm_api.ai.factory.create_provider` sur un
        // fournisseur simulé (aucun appel réseau, réponses déterministes) — jamais activé hors
        // e2e, aucune clé IA réelle disponible sur chimera. Sans effet sur les autres specs, qui
        // n'appellent jamais `create_provider` (elles sèment leur résultat directement en base).
        AI_SIMULATED_PROVIDER: "1",
      },
    },
    {
      // `next start` (build de production) plutôt que `next dev` : la compilation à la
      // demande de `next dev` introduit des pauses variables en cours d'interaction que
      // Playwright interprète comme un élément instable, et fait échouer les tests au hasard.
      command: `pnpm exec next build && pnpm exec next start --port ${WEB_PORT}`,
      url: WEB_BASE_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
      env: {
        NEXT_PUBLIC_API_URL: API_BASE_URL,
        // CSP `connect-src` (lot `v5-securite`) : sans l'origine du stockage objet, le `PUT`
        // présigné direct du navigateur vers MinIO est bloqué et tout envoi de photo échoue
        // (constaté par le lot `v5-e2e`, voir `src/middleware.ts`/`src/lib/config.ts`). Doit
        // rester alignée avec `S3_ENDPOINT_URL` de l'entrée `webServer` API ci-dessus.
        NEXT_PUBLIC_UPLOAD_ORIGIN: process.env.S3_ENDPOINT_URL || "http://localhost:59000",
      },
    },
    {
      // Worker arq (lot `v5-e2e`) : jusqu'ici aucune spec e2e n'avait besoin du vrai pipeline de
      // reconnaissance (`pbm_api.worker.detect_cards_task`), seulement d'un résultat semé
      // directement en base (`seed_validation_e2e.py`, `seed_card_fiche_e2e.py`). Le parcours
      // complet, lui, envoie une vraie photo et attend une vraie détection + identification —
      // sans ce worker, le job resterait en file indéfiniment. Même base/redis que l'API
      // ci-dessus (obligatoire : la queue arq est nommée `f"{REDIS_PREFIX}queue"`), pas de `url`
      // (rien à sonder en HTTP) : le test attend la fin du job via le flux SSE de validation.
      command: "uv run arq pbm_api.worker.WorkerSettings",
      cwd: "../api",
      reuseExistingServer: !process.env.CI,
      env: {
        DATABASE_URL:
          process.env.E2E_DATABASE_URL ||
          "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_pages_auth_e2e",
        REDIS_URL: process.env.REDIS_URL || "redis://localhost:56379/0",
        REDIS_PREFIX: "pbm:v1-pages-auth:e2e:",
        AI_SIMULATED_PROVIDER: "1",
      },
    },
  ],
});
