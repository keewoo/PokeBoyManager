import { NextResponse, type NextRequest } from "next/server";

import { getApiBaseUrl, getSessionCookieName, getUploadOrigin } from "@/lib/config";

// Élargi (mission `v5-securite` point 2) : les en-têtes de sécurité ci-dessous doivent
// s'appliquer à toute page, pas seulement aux routes protégées par session — seuls les
// assets déjà immuables/statiques de Next.js en sont exclus (rien à protéger, coût inutile).
export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};

const PROTECTED_PATH_PREFIXES = ["/collection", "/ajouter", "/carte", "/profil", "/souhaits", "/jeu"];

// `getApiBaseUrl()` renvoie soit une origine absolue (`NEXT_PUBLIC_API_URL` défini), soit le
// repli relatif `/api` (mission `pbm-front-accueil`, point 4). `new URL("/api")` lèverait
// `Invalid URL` (une URL relative n'a pas d'origine sans base) : dans ce cas il n'y a rien à
// ajouter à la CSP — une origine relative résout contre 'self', déjà présent.
function apiOriginForCsp(): string | null {
  const base = getApiBaseUrl();
  if (base.startsWith("/")) return null;
  return new URL(base).origin;
}

function buildCsp(nonce: string): string {
  const apiOrigin = apiOriginForCsp();
  // Avec `STORAGE_BACKEND=s3` (MinIO en dev/CI), le navigateur dépose la photo brute par un
  // `PUT` direct vers l'origine du stockage objet, présignée par l'API (`pbm_api.uploads`,
  // `pbm_api.s3.ObjectStorage.presign_put`) — jamais via l'API elle-même. Sans cette origine en
  // `connect-src`, ce `PUT` est bloqué par la CSP et tout envoi de photo échoue
  // (constaté par le lot `v5-e2e`, premier à exercer un vrai envoi depuis le navigateur).
  // `null` avec `STORAGE_BACKEND=local` (UAT/PROD) : l'envoi passe alors par l'API elle-même,
  // déjà couverte par `apiOrigin`.
  const uploadOrigin = getUploadOrigin();
  // `script-src` par nonce (généré à chaque requête, voir plus bas) plutôt que `'self'` seul :
  // le layout racine (`src/app/layout.tsx`) pose un petit script inline pour choisir le thème
  // avant le premier rendu (éviter un flash clair/sombre) — un nonce laisse ce seul script
  // s'exécuter sans ouvrir la porte à un script injecté ailleurs sur la page.
  // `style-src` garde `'unsafe-inline'` : quelques composants (`ai-tab.tsx`, `design/page.tsx`)
  // posent une couleur dynamique via l'attribut `style`, qui ne peut pas porter de nonce (seuls
  // les éléments `<style>` le peuvent) — une injection CSS est un risque nettement plus faible
  // qu'une injection JS, compromis courant même sous CSP stricte.
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}'`,
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' data:${apiOrigin ? ` ${apiOrigin}` : ""}`,
    `connect-src 'self'${apiOrigin ? ` ${apiOrigin}` : ""}${uploadOrigin ? ` ${uploadOrigin}` : ""}`,
    "font-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ].join("; ");
}

function withSecurityHeaders(response: NextResponse, nonce: string): NextResponse {
  response.headers.set("Content-Security-Policy", buildCsp(nonce));
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("X-Frame-Options", "DENY");
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  response.headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  // Sans effet si la réponse part en clair (les navigateurs l'ignorent hors HTTPS) : inoffensif
  // de le poser aussi en dev HTTP.
  response.headers.set("Strict-Transport-Security", "max-age=63072000; includeSubDomains");
  return response;
}

export function middleware(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");

  const isProtected = PROTECTED_PATH_PREFIXES.some((prefix) =>
    request.nextUrl.pathname.startsWith(prefix)
  );
  if (isProtected && !request.cookies.has(getSessionCookieName())) {
    // Présence du cookie seulement : une session expirée ou révoquée est encore rejetée par
    // l'API (401), qui reste la seule source de vérité. Cette garde évite juste d'afficher
    // une page privée vide à un visiteur qui n'a manifestement pas de session.
    const loginUrl = new URL("/connexion", request.url);
    loginUrl.searchParams.set("next", `${request.nextUrl.pathname}${request.nextUrl.search}`);
    return withSecurityHeaders(NextResponse.redirect(loginUrl), nonce);
  }

  // Le nonce part aussi en en-tête de requête : `layout.tsx` (Server Component) le relit via
  // `headers()` pour l'attacher au script inline — c'est le mécanisme documenté par Next.js
  // pour faire transiter une valeur générée en middleware jusqu'au rendu serveur.
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  return withSecurityHeaders(response, nonce);
}
