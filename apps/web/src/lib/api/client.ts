import { getApiBaseUrl, getCsrfCookieName } from "@/lib/config";

/**
 * Erreur d'un appel API portant le code HTTP (`status`) et le message serveur destiné à
 * l'utilisateur. Levée par `handle` dès que la réponse n'est pas 2xx ; les écrans s'en servent
 * pour distinguer 401/404/422 et afficher la raison (`detail`) telle que l'API l'a rédigée.
 */
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

// Le cookie CSRF n'est posé qu'après connexion ; absent, l'en-tête est simplement omis (les
// routes non authentifiées — inscription, connexion — n'en exigent pas).
function csrfHeaders(): HeadersInit {
  const token = readCookie(getCsrfCookieName());
  return token ? { "X-CSRF-Token": token } : {};
}

async function errorMessage(response: Response): Promise<string> {
  const payload = await response.json().catch(() => null);
  if (payload && typeof payload === "object" && "detail" in payload && typeof payload.detail === "string") {
    return payload.detail;
  }
  return "Une erreur est survenue. Réessaie dans un instant.";
}

async function handle<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/**
 * GET sur l'API avec le cookie de session (`credentials: "include"`). Résout vers le corps JSON
 * typé, ou lève `ApiError` sur une réponse non-2xx. Point d'entrée en lecture de tous les clients.
 */
export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, { credentials: "include" });
  return handle<T>(response);
}

/**
 * Appel JSON mutant (POST/PUT/PATCH/DELETE) : joint le cookie de session, l'en-tête CSRF quand il
 * existe, et sérialise `body` si fourni. Un 204 résout vers `undefined` ; tout non-2xx lève
 * `ApiError`. C'est le serveur qui décide — l'interface ne fait que transmettre la demande.
 */
export async function apiJson<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...csrfHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return handle<T>(response);
}

/**
 * POST multipart d'un fichier unique (champ `file`), avec session et en-tête CSRF. Le
 * `Content-Type` est laissé au navigateur (frontière multipart). Même gestion d'erreur que les
 * autres helpers. Sert aux envois de photos, avatar et imports CSV.
 */
export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { ...csrfHeaders() },
    body: formData,
  });
  return handle<T>(response);
}
