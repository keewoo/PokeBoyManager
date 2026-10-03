import { getApiBaseUrl, getCsrfCookieName } from "@/lib/config";

/** Nom de l'en-tête HTTP portant le jeton CSRF, attendu par l'API sur les requêtes mutantes. */
export const CSRF_HEADER_NAME = "X-CSRF-Token";

/**
 * Erreur d'un appel d'upload portant le code HTTP et le message serveur. Dupliquée ici (plutôt
 * qu'importée de `client.ts`) car ce module fait ses appels `fetch` à la main — flux multipart et
 * cibles d'envoi présignées — sans passer par les helpers génériques.
 */
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Métadonnées d'un fichier à envoyer, déclarées avant l'envoi pour que le serveur prépare la cible. */
export type UploadFileMeta = {
  filename: string;
  content_type: string;
  size_bytes: number;
};

/** Cible d'envoi retournée par le serveur : où et comment déposer les octets bruts (URL, méthode, en-têtes signés). */
export type UploadTarget = {
  upload_id: string;
  method: string;
  url: string;
  headers: Record<string, string>;
};

/** Résultat de la finalisation d'un envoi : statut, métadonnées retenues, et le job de reconnaissance s'il a été lancé. */
export type CompleteUploadResult = {
  upload_id: string;
  status: string;
  content_type: string;
  size_bytes: number;
  recognition_enabled: boolean;
  job_id: string | null;
};

function readCookie(name: string): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const escaped = name.replace(/[.$?*|{}()[\]\\/+^]/g, "\\$&");
  const match = document.cookie.match(new RegExp(`(?:^|; )${escaped}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

/** Lit le jeton CSRF déposé en cookie après connexion (ou `null` côté serveur / avant session). */
export function getCsrfToken(): string | null {
  return readCookie(getCsrfCookieName());
}

async function parseErrorMessage(response: Response): Promise<string> {
  const payload = await response.json().catch(() => null);
  if (payload && typeof payload === "object" && "detail" in payload && typeof payload.detail === "string") {
    return payload.detail;
  }
  return "Une erreur est survenue. Réessaie dans un instant.";
}

/** Étape 1 de l'envoi : déclare les fichiers (`POST /uploads`) et récupère une cible signée par fichier. Lève `ApiError` sur échec. */
export async function createUploads(files: UploadFileMeta[]): Promise<UploadTarget[]> {
  const csrf = getCsrfToken();
  const response = await fetch(`${getApiBaseUrl()}/uploads`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { [CSRF_HEADER_NAME]: csrf } : {}),
    },
    body: JSON.stringify({ files }),
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  const body = (await response.json()) as { uploads: UploadTarget[] };
  return body.uploads;
}

/**
 * Étape 2 : dépose les octets bruts du fichier vers la cible fournie. L'URL peut être absolue (S3
 * présigné) ou relative à notre API ; dans tous les cas `credentials: "omit"` — une signature S3
 * serait invalidée par un cookie, et la cible locale s'authentifie par le jeton dans l'URL.
 */
export async function putRawBytes(target: UploadTarget, file: Blob): Promise<void> {
  const isAbsolute = /^https?:\/\//i.test(target.url);
  const url = isAbsolute ? target.url : `${getApiBaseUrl()}${target.url}`;
  const response = await fetch(url, {
    method: target.method,
    headers: target.headers,
    body: file,
    // La cible du backend "local" (D7) est notre propre API, autorisée par jeton signé dans
    // l'URL (pas de cookie nécessaire) ; une cible S3 présignée refuse même les en-têtes
    // d'identification (signature invalidée).
    credentials: "omit",
  });
  if (!response.ok) {
    throw new ApiError(response.status, "L'envoi de cette photo a échoué.");
  }
}

/** Étape 3 : signale la fin de l'envoi (`POST /uploads/{id}/complete`) ; le serveur valide et lance la reconnaissance. Lève `ApiError` sur échec. */
export async function completeUpload(uploadId: string): Promise<CompleteUploadResult> {
  const csrf = getCsrfToken();
  const response = await fetch(`${getApiBaseUrl()}/uploads/${uploadId}/complete`, {
    method: "POST",
    credentials: "include",
    headers: csrf ? { [CSRF_HEADER_NAME]: csrf } : {},
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  return (await response.json()) as CompleteUploadResult;
}

/** Un envoi qui a encore des cartes à valider : point de reprise du parcours de validation. */
export type PendingUpload = {
  upload_id: string;
  created_at: string;
  pending_count: number;
  total_count: number;
};

/** Envois de l'utilisateur qui ont encore des cartes à valider (lot `pbm-parcours-validation`,
 * mission point 2) : point d'entrée de reprise depuis « Ajouter des photos ». Renvoie une liste
 * vide plutôt que de lever si la requête échoue — c'est une aide, pas le cœur de l'écran. */
export async function listPendingValidations(): Promise<PendingUpload[]> {
  try {
    const response = await fetch(`${getApiBaseUrl()}/uploads/pending-validation`, {
      credentials: "include",
    });
    if (!response.ok) return [];
    const body = await response.json().catch(() => null);
    return Array.isArray(body?.uploads) ? (body.uploads as PendingUpload[]) : [];
  } catch {
    // Aide à la reprise, pas le cœur de l'écran : une panne réseau ne casse pas « Ajouter ».
    return [];
  }
}

/** Indique si l'utilisateur a déposé au moins une clé IA (`GET /me/ai-keys`) ; renvoie `false` sur échec, pour aiguiller l'écran d'ajout. */
export async function hasAnyAiKey(): Promise<boolean> {
  const response = await fetch(`${getApiBaseUrl()}/me/ai-keys`, { credentials: "include" });
  if (!response.ok) {
    return false;
  }
  const keys = await response.json().catch(() => []);
  return Array.isArray(keys) && keys.length > 0;
}
