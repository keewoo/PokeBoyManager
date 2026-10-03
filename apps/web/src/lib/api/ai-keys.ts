import type { components } from "@pbm/api-client";

import { apiGet, apiJson } from "@/lib/api/client";

/** Fournisseur d'IA pris en charge (Claude, Gemini, OpenAI), tel que défini par le schéma serveur. */
export type AiProvider = components["schemas"]["AiProvider"];
/** État d'une clé IA pour un fournisseur — jamais la valeur de la clé, seulement sa présence/métadonnées. */
export type AiKeyResponse = components["schemas"]["AiKeyResponse"];
/** Résultat d'un test de clé (le serveur appelle réellement le fournisseur et renvoie le verdict). */
export type AiKeyTestResponse = components["schemas"]["AiKeyTestResponse"];
/** Réglages IA de l'utilisateur, dont le fournisseur par défaut. */
export type AiSettingsResponse = components["schemas"]["AiSettingsResponse"];
/** Une ligne de consommation IA (coût/jetons d'un appel), pour l'historique d'usage. */
export type AiUsageEntry = components["schemas"]["AiUsageEntry"];

/** Liste les clés IA déposées par l'utilisateur (`GET /me/ai-keys`) — présence seule, jamais la valeur. */
export function listAiKeys(): Promise<AiKeyResponse[]> {
  return apiGet<AiKeyResponse[]>("/me/ai-keys");
}

/** Dépose ou remplace la clé d'un fournisseur (`PUT /me/ai-keys/{provider}`) ; chiffrée côté serveur, jamais relue. */
export function upsertAiKey(provider: AiProvider, apiKey: string): Promise<AiKeyResponse> {
  return apiJson<AiKeyResponse>("PUT", `/me/ai-keys/${provider}`, { api_key: apiKey });
}

/** Supprime la clé d'un fournisseur (`DELETE /me/ai-keys/{provider}`). */
export function deleteAiKey(provider: AiProvider): Promise<void> {
  return apiJson<void>("DELETE", `/me/ai-keys/${provider}`);
}

/** Teste la clé d'un fournisseur (`POST /me/ai-keys/{provider}/test`) : c'est le serveur qui appelle le fournisseur et tranche. */
export function testAiKey(provider: AiProvider): Promise<AiKeyTestResponse> {
  return apiJson<AiKeyTestResponse>("POST", `/me/ai-keys/${provider}/test`, {});
}

/** Lit les réglages IA de l'utilisateur (`GET /me/ai-settings`). */
export function getAiSettings(): Promise<AiSettingsResponse> {
  return apiGet<AiSettingsResponse>("/me/ai-settings");
}

/** Change le fournisseur IA par défaut (`PATCH /me/ai-settings`). */
export function setDefaultProvider(provider: AiProvider): Promise<AiSettingsResponse> {
  return apiJson<AiSettingsResponse>("PATCH", "/me/ai-settings", { default_provider: provider });
}

/** Historique de consommation IA de l'utilisateur (`GET /me/ai-usage`). */
export function getAiUsage(): Promise<AiUsageEntry[]> {
  return apiGet<AiUsageEntry[]>("/me/ai-usage");
}
