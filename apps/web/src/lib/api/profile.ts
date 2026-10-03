import type { components } from "@pbm/api-client";

import { apiGet, apiJson, apiUpload } from "@/lib/api/client";
import { getApiBaseUrl } from "@/lib/config";

/** Profil complet de l'utilisateur (identité, e-mail, réglages), schéma serveur. */
export type ProfileResponse = components["schemas"]["ProfileResponse"];
/** Une session active de l'utilisateur (appareil/navigateur), pour la gestion des connexions. */
export type SessionResponse = components["schemas"]["SessionResponse"];
/** Réponse générique porteuse d'un message utilisateur (actions e-mail/mot de passe). */
export type MessageResponse = components["schemas"]["MessageResponse"];

/** Lit le profil de l'utilisateur courant (`GET /me`). */
export function getProfile(): Promise<ProfileResponse> {
  return apiGet<ProfileResponse>("/me");
}

/** Données de mise à jour de l'identité côté écran (camelCase), transposées en snake_case pour l'API. */
export type UpdateIdentityPayload = {
  pseudo: string;
  firstName?: string;
  lastName: string;
  birthDate: string;
};

/** Met à jour l'identité (pseudo, nom, date de naissance) via `PATCH /me` ; prénom vide → `null`. */
export function updateIdentity(payload: UpdateIdentityPayload): Promise<ProfileResponse> {
  return apiJson<ProfileResponse>("PATCH", "/me", {
    pseudo: payload.pseudo,
    first_name: payload.firstName || null,
    last_name: payload.lastName,
    birth_date: payload.birthDate,
  });
}

/** Envoie une nouvelle photo de profil (`POST /me/avatar`, multipart) et renvoie le profil à jour. */
export function uploadAvatar(file: File): Promise<ProfileResponse> {
  return apiUpload<ProfileResponse>("/me/avatar", file);
}

// Le navigateur envoie le cookie de session lui-même (`<img>` en `crossOrigin="use-credentials"`) :
// pas de jeton dans l'URL. `bust` force le rechargement après un nouvel envoi (le chemin ne
// change jamais sinon, le navigateur garderait l'ancienne image en cache).
/** URL de l'avatar (`/me/avatar`), à poser dans un `<img>` ; le paramètre `bust` force le rechargement après un nouvel envoi (le chemin ne change pas sinon). */
export function avatarUrl(bust?: number): string {
  const suffix = bust ? `?v=${bust}` : "";
  return `${getApiBaseUrl()}/me/avatar${suffix}`;
}

/** Demande un changement d'adresse e-mail (`POST /me/email`) ; le serveur envoie un lien de confirmation à la nouvelle adresse. */
export function requestEmailChange(email: string): Promise<MessageResponse> {
  return apiJson<MessageResponse>("POST", "/me/email", { email });
}

/** Confirme le changement d'e-mail à partir du jeton du lien (`POST /me/email/confirm`). */
export function confirmEmailChange(token: string): Promise<MessageResponse> {
  return apiJson<MessageResponse>("POST", "/me/email/confirm", { token });
}

/** Change le mot de passe (`POST /me/password`) ; le serveur vérifie l'ancien avant d'accepter le nouveau. */
export function changePassword(
  currentPassword: string,
  newPassword: string
): Promise<MessageResponse> {
  return apiJson<MessageResponse>("POST", "/me/password", {
    current_password: currentPassword,
    new_password: newPassword,
  });
}

/** Liste les sessions actives de l'utilisateur (`GET /me/sessions`), pour en révoquer à distance. */
export function listSessions(): Promise<SessionResponse[]> {
  return apiGet<SessionResponse[]>("/me/sessions");
}

/** Révoque une session donnée (`DELETE /me/sessions/{id}`), déconnectant l'appareil correspondant. */
export function revokeSession(sessionId: string): Promise<void> {
  return apiJson<void>("DELETE", `/me/sessions/${sessionId}`);
}

/** Supprime définitivement le compte (`DELETE /me`) ; le mot de passe est redemandé pour confirmer. */
export function deleteAccount(password: string): Promise<void> {
  return apiJson<void>("DELETE", "/me", { password });
}
