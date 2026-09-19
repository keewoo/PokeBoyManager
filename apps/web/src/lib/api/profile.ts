import type { components } from "@pbm/api-client";

import { apiGet, apiJson, apiUpload } from "@/lib/api/client";
import { getApiBaseUrl } from "@/lib/config";

export type ProfileResponse = components["schemas"]["ProfileResponse"];
export type SessionResponse = components["schemas"]["SessionResponse"];
export type MessageResponse = components["schemas"]["MessageResponse"];

export function getProfile(): Promise<ProfileResponse> {
  return apiGet<ProfileResponse>("/me");
}

export type UpdateIdentityPayload = {
  pseudo: string;
  firstName?: string;
  lastName: string;
  birthDate: string;
};

export function updateIdentity(payload: UpdateIdentityPayload): Promise<ProfileResponse> {
  return apiJson<ProfileResponse>("PATCH", "/me", {
    pseudo: payload.pseudo,
    first_name: payload.firstName || null,
    last_name: payload.lastName,
    birth_date: payload.birthDate,
  });
}

export function uploadAvatar(file: File): Promise<ProfileResponse> {
  return apiUpload<ProfileResponse>("/me/avatar", file);
}

// Le navigateur envoie le cookie de session lui-même (`<img>` en `crossOrigin="use-credentials"`) :
// pas de jeton dans l'URL. `bust` force le rechargement après un nouvel envoi (le chemin ne
// change jamais sinon, le navigateur garderait l'ancienne image en cache).
export function avatarUrl(bust?: number): string {
  const suffix = bust ? `?v=${bust}` : "";
  return `${getApiBaseUrl()}/me/avatar${suffix}`;
}

export function requestEmailChange(email: string): Promise<MessageResponse> {
  return apiJson<MessageResponse>("POST", "/me/email", { email });
}

export function confirmEmailChange(token: string): Promise<MessageResponse> {
  return apiJson<MessageResponse>("POST", "/me/email/confirm", { token });
}

export function changePassword(
  currentPassword: string,
  newPassword: string
): Promise<MessageResponse> {
  return apiJson<MessageResponse>("POST", "/me/password", {
    current_password: currentPassword,
    new_password: newPassword,
  });
}

export function listSessions(): Promise<SessionResponse[]> {
  return apiGet<SessionResponse[]>("/me/sessions");
}

export function revokeSession(sessionId: string): Promise<void> {
  return apiJson<void>("DELETE", `/me/sessions/${sessionId}`);
}

export function deleteAccount(password: string): Promise<void> {
  return apiJson<void>("DELETE", "/me", { password });
}
