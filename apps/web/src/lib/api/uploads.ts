import { getApiBaseUrl, getCsrfCookieName } from "@/lib/config";

export const CSRF_HEADER_NAME = "X-CSRF-Token";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export type UploadFileMeta = {
  filename: string;
  content_type: string;
  size_bytes: number;
};

export type UploadTarget = {
  upload_id: string;
  method: string;
  url: string;
  headers: Record<string, string>;
};

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

export async function hasAnyAiKey(): Promise<boolean> {
  const response = await fetch(`${getApiBaseUrl()}/me/ai-keys`, { credentials: "include" });
  if (!response.ok) {
    return false;
  }
  const keys = await response.json().catch(() => []);
  return Array.isArray(keys) && keys.length > 0;
}
