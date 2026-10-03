import type { components } from "@pbm/api-client";

import { apiJson } from "@/lib/api/client";

export { ApiError } from "@/lib/api/client";

/** Réponse générique porteuse d'un message utilisateur (confirmation d'une action asynchrone). */
export type MessageResponse = components["schemas"]["MessageResponse"];
/** Identité de l'utilisateur renvoyée à la connexion. */
export type UserResponse = components["schemas"]["UserResponse"];

/** Données du formulaire d'inscription côté écran (nommage camelCase), transposées en snake_case pour l'API. */
export type RegisterAccountPayload = {
  email: string;
  password: string;
  firstName?: string;
  lastName: string;
  birthDate: string;
  acceptTerms: boolean;
};

/**
 * Crée un compte (`POST /auth/register`). Mappe les champs d'écran vers le contrat serveur
 * (prénom optionnel → `null`). Le serveur envoie l'e-mail de vérification ; aucune session n'est
 * ouverte ici — l'utilisateur doit d'abord vérifier son adresse.
 */
export function registerAccount(payload: RegisterAccountPayload): Promise<MessageResponse> {
  return apiJson<MessageResponse>("POST", "/auth/register", {
    email: payload.email,
    password: payload.password,
    first_name: payload.firstName || null,
    last_name: payload.lastName,
    birth_date: payload.birthDate,
    accept_terms: payload.acceptTerms,
  });
}

/** Valide l'adresse e-mail à partir du jeton du lien reçu (`POST /auth/verify-email`). */
export function verifyEmail(token: string): Promise<MessageResponse> {
  return apiJson<MessageResponse>("POST", "/auth/verify-email", { token });
}

/** Ouvre une session (`POST /auth/login`) : le serveur pose les cookies de session et CSRF, et renvoie l'identité. */
export function login(email: string, password: string): Promise<UserResponse> {
  return apiJson<UserResponse>("POST", "/auth/login", { email, password });
}

/** Ferme la session courante (`POST /auth/logout`) ; le serveur invalide la session et ses cookies. */
export function logout(): Promise<void> {
  return apiJson<void>("POST", "/auth/logout");
}

/** Demande un e-mail de réinitialisation de mot de passe (`POST /auth/forgot`). Réponse neutre pour ne pas révéler si l'adresse existe. */
export function forgotPassword(email: string): Promise<MessageResponse> {
  return apiJson<MessageResponse>("POST", "/auth/forgot", { email });
}

/** Fixe un nouveau mot de passe à partir du jeton du lien de réinitialisation (`POST /auth/reset`). */
export function resetPassword(token: string, password: string): Promise<MessageResponse> {
  return apiJson<MessageResponse>("POST", "/auth/reset", { token, password });
}
