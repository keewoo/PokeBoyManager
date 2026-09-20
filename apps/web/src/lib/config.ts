// Sans `NEXT_PUBLIC_API_URL` (absente à la construction), jamais une valeur en dur : le navigateur
// résout `/api` contre l'origine courante, que Caddy achemine déjà vers l'API en PROD
// (`docs/infra/SERVEUR-POKEBOY.md`) — et en dev, `.env` (copié depuis `.env.example`) définit la
// variable explicitement plutôt que de dépendre d'un repli ici (mission `pbm-front-accueil` :
// "localhost" ne doit plus apparaître dans le JavaScript servi en production).
const RELATIVE_API_FALLBACK = "/api";

export function getApiBaseUrl(): string {
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (!url) {
    return RELATIVE_API_FALLBACK;
  }
  return url.replace(/\/+$/, "");
}

// Réservé aux Server Components / appels côté serveur (ex: accueil visiteur, mission
// `pbm-front-accueil` point 1) : contrairement au navigateur, `fetch()` exécuté côté Node n'a
// pas d'origine implicite pour résoudre une URL relative comme `/api` — il faut une URL absolue.
// `null` sans `NEXT_PUBLIC_API_URL` (jamais une origine devinée) : l'appelant doit alors renoncer
// à l'appel plutôt que de risquer une requête vers une origine inventée.
export function getServerApiBaseUrl(): string | null {
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (!url) return null;
  return url.replace(/\/+$/, "");
}

// Doit rester alignée avec `SESSION_COOKIE_NAME` côté `apps/api` (`pbm_api.config.Settings`).
export function getSessionCookieName(): string {
  return process.env.NEXT_PUBLIC_SESSION_COOKIE_NAME || "pbm_session";
}

// Doit rester alignée avec `CSRF_COOKIE_NAME` côté `apps/api`. Ce cookie n'est pas HttpOnly :
// le front le relit pour le renvoyer dans l'en-tête `X-CSRF-Token` sur toute requête qui écrit
// (`pbm_api.security.csrf`).
export function getCsrfCookieName(): string {
  return process.env.NEXT_PUBLIC_CSRF_COOKIE_NAME || "pbm_csrf";
}

// Origine du dépôt présigné (lot `v3-upload`, `STORAGE_BACKEND=s3` — MinIO en dev/CI) que le
// navigateur appelle en direct par `PUT` (`pbm_api.storage.ObjectStorage.presign_put`), sans
// passer par l'API : nécessaire à la CSP `connect-src` (`src/middleware.ts`, lot `v5-securite`),
// sinon le navigateur bloque l'envoi. `null` avec `STORAGE_BACKEND=local` (UAT/PROD) : l'envoi
// passe alors par l'API elle-même, déjà couverte par `getApiBaseUrl()`.
export function getUploadOrigin(): string | null {
  const url = process.env.NEXT_PUBLIC_UPLOAD_ORIGIN;
  return url ? new URL(url).origin : null;
}
