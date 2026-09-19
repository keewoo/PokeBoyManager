import type { components } from "@pbm/api-client";

import { apiGet, apiJson } from "@/lib/api/client";

export type AiProvider = components["schemas"]["AiProvider"];
export type AiKeyResponse = components["schemas"]["AiKeyResponse"];
export type AiKeyTestResponse = components["schemas"]["AiKeyTestResponse"];
export type AiSettingsResponse = components["schemas"]["AiSettingsResponse"];
export type AiUsageEntry = components["schemas"]["AiUsageEntry"];

export function listAiKeys(): Promise<AiKeyResponse[]> {
  return apiGet<AiKeyResponse[]>("/me/ai-keys");
}

export function upsertAiKey(provider: AiProvider, apiKey: string): Promise<AiKeyResponse> {
  return apiJson<AiKeyResponse>("PUT", `/me/ai-keys/${provider}`, { api_key: apiKey });
}

export function deleteAiKey(provider: AiProvider): Promise<void> {
  return apiJson<void>("DELETE", `/me/ai-keys/${provider}`);
}

export function testAiKey(provider: AiProvider): Promise<AiKeyTestResponse> {
  return apiJson<AiKeyTestResponse>("POST", `/me/ai-keys/${provider}/test`, {});
}

export function getAiSettings(): Promise<AiSettingsResponse> {
  return apiGet<AiSettingsResponse>("/me/ai-settings");
}

export function setDefaultProvider(provider: AiProvider): Promise<AiSettingsResponse> {
  return apiJson<AiSettingsResponse>("PATCH", "/me/ai-settings", { default_provider: provider });
}

export function getAiUsage(): Promise<AiUsageEntry[]> {
  return apiGet<AiUsageEntry[]>("/me/ai-usage");
}
