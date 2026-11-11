import { NextResponse, type NextRequest } from "next/server";

import { getApiBaseUrl, getSessionCookieName, getUploadOrigin } from "@/lib/config";

// Élargi (mission `v5-securite` point 2) : les en-têtes de sécurité ci-dessous doivent
// s'appliquer à toute page, pas seulement aux routes protégées par session — seuls les
// assets déjà immuables/statiques de Next.js en sont exclus (rien à protéger, coût inutile).
/**
 * Portée du middleware : toutes les routes sauf les assets statiques/immuables de Next
 * (`_next/static`, `_next/image`, `favicon.ico`) — ceux-ci n'ont rien à protéger.
 */
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
  // Avec `STORAGE_BACKEND=s3` (SeaweedFS en dev/CI), le navigateur dépose la photo brute par un
  // `PUT` direct vers l'origine du stockage objet, présignée par l'API (`pbm_api.uploads`,
  // `pbm_api.s3.ObjectStorage.presign_put`) — jamais via l'API elle-même. Sans cette origine en
  // `connect-src`, ce `PUT` est bloqué par la CSP et tout envoi de photo échoue
  // (constaté par le lot `v5-e2e`, premier à exercer un vrai envoi depuis le navigateur).
  // `null` avec `STORAGE_BACKEND=local` (UAT/PROD) : l'envoi passe alors par l'API elle-même,
  // déjà couverte par `apiOrigin`.
  const uploadOrigin = getUploadOrigin();
  // Origine **WebSocket** du canal temps réel du jeu (`pbm_api.routers.games_ws`, lot
  // `j-temps-reel`). Elle doit être nommée séparément : une source `http://hôte` de `connect-src`
  // ne couvre PAS `ws://hôte` dans Chromium, et le navigateur refuse alors d'ouvrir le socket
  // (« violates the following Content Security Policy directive: connect-src … »).
  //
  // Trouvé par le lot `j-e2e-deux-navigateurs`, le premier à ouvrir une vraie partie dans un vrai
  // navigateur : le canal échouait trois fois puis repliait en interrogation périodique, sans que
  // rien n'échoue — la partie « marchait », en mode dégradé, en permanence.
  //
  // Ne concerne que les déploiements où l'API a sa **propre origine** (dev, CI, e2e : page sur
  // :3100, API sur :8100). En UAT/PROD l'API partage l'origine du site (`https://pokeboy.lol/api`)
  // et `'self'` couvre déjà `wss:` — d'où un défaut resté invisible en ligne.
  const wsOrigin = apiOrigin ? apiOrigin.replace(/^http/, "ws") : null;
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
    `connect-src 'self'${apiOrigin ? ` ${apiOrigin}` : ""}${wsOrigin ? ` ${wsOrigin}` : ""}${uploadOrigin ? ` ${uploadOrigin}` : ""}`,
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

// Un hôte tel qu'un navigateur l'écrit : nom (ou IPv4) et port facultatif, ou IPv6 entre crochets.
// Tout le reste (virgule d'une liste `X-Forwarded-Host`, espace, barre oblique, `@`) est refusé.
const HOST_PATTERN = /^(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:.]+\])(?::\d{1,5})?$/;

/**
 * Origine publique de la requête — celle que le visiteur a tapée — pour construire une redirection.
 *
 * `request.url` ne la donne pas derrière Caddy : le serveur Next autonome compose l'URL de la
 * requête avec **son propre nom d'écoute** (`initURL` de `next-server.js` :
 * `${protocole}://${hostname}:${port}${chemin}`), si bien qu'une redirection calculée depuis
 * `request.url` envoyait le visiteur de `pokeboy.lol` vers `https://localhost:3100/connexion`
 * (constaté en PROD le 11/11/2026, sur `/jeu` et `/collection`). Une redirection relative n'est pas
 * possible non plus : l'adaptateur du middleware relit `Location` par `new NextURL(…)` sans base.
 *
 * 1. **`NEXT_PUBLIC_SITE_URL`, quand la construction la pose** (le build de PROD :
 *    `https://pokeboy.lol`) : l'origine est alors fixée, et aucun en-tête de la requête ne la
 *    choisit. Rien ne dépend ainsi de la configuration du proxy : un cache partagé, un CDN ou un
 *    `trusted_proxies` posé un jour devant Next ne pourrait pas faire rediriger vers un autre hôte.
 * 2. Sinon (dev, CI, e2e), l'hôte vient de la requête : `X-Forwarded-Host` (que Caddy réécrit avec
 *    l'hôte reçu, sans croire celui d'un client), puis `Host` (en dev, `localhost:3100`, ce qui est
 *    juste). Un candidat est écarté s'il n'a pas la forme d'un hôte **ou** si l'analyseur d'URL le
 *    refuse (`1.2.3.999`, port `99999`, `[1.2.3.4]`) : sans ce second contrôle, `new URL` levait et
 *    la requête finissait en erreur 500 au lieu de passer au candidat suivant. En dernier recours,
 *    l'origine de `request.url`. Le protocole reste celui de `request.nextUrl`, que Next tire déjà
 *    de `X-Forwarded-Proto`.
 *
 * Une valeur de `NEXT_PUBLIC_SITE_URL` illisible ou hors http(s) est ignorée (cas 2) : la
 * redirection reste celle, sûre, du dev. C'est la même variable que `metadataBase` (`layout.tsx`).
 */
function publicOrigin(request: NextRequest): string {
  const configured = configuredSiteOrigin();
  if (configured) return configured;
  const candidates = [request.headers.get("x-forwarded-host"), request.headers.get("host")];
  for (const value of candidates) {
    const host = value?.split(",")[0]?.trim() ?? "";
    if (!HOST_PATTERN.test(host)) continue;
    try {
      return new URL(`${request.nextUrl.protocol}//${host}`).origin;
    } catch {
      // Forme d'hôte admise par le motif mais refusée par l'analyseur d'URL : candidat suivant.
    }
  }
  return request.nextUrl.origin;
}

/** Origine de `NEXT_PUBLIC_SITE_URL` (lue à chaque appel : inlinée par `next build`), ou `null`. */
function configuredSiteOrigin(): string | null {
  const raw = process.env.NEXT_PUBLIC_SITE_URL;
  if (!raw) return null;
  try {
    const url = new URL(raw);
    return url.protocol === "https:" || url.protocol === "http:" ? url.origin : null;
  } catch {
    return null;
  }
}

/**
 * Middleware Next exécuté à chaque requête : pose les en-têtes de sécurité (CSP à nonce par requête,
 * HSTS, anti-framing, nosniff…) sur toute réponse, et redirige vers `/connexion?next=…` l'accès à une
 * route protégée (`PROTECTED_PATH_PREFIXES`) sans cookie de session — l'API 401 restant l'autorité.
 * Le nonce est transmis au rendu serveur via l'en-tête de requête `x-nonce` (relu par `layout.tsx`).
 */
export function middleware(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");

  const isProtected = PROTECTED_PATH_PREFIXES.some((prefix) =>
    request.nextUrl.pathname.startsWith(prefix)
  );
  if (isProtected && !request.cookies.has(getSessionCookieName())) {
    // Présence du cookie seulement : une session expirée ou révoquée est encore rejetée par
    // l'API (401), qui reste la seule source de vérité. Cette garde évite juste d'afficher
    // une page privée vide à un visiteur qui n'a manifestement pas de session.
    const loginUrl = new URL("/connexion", publicOrigin(request));
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
