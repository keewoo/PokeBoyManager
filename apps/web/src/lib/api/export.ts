import type { components } from "@pbm/api-client";

import { ApiError, apiJson } from "@/lib/api/client";
import { getApiBaseUrl } from "@/lib/config";

export type ExportResponse = components["schemas"]["ExportResponse"];

export function requestExport(): Promise<ExportResponse> {
  return apiJson<ExportResponse>("POST", "/me/export");
}

/** Export CSV synchrone de la collection (mission `v6-import-export` point 1) : pas de job, pas
 * d'e-mail — le fichier part directement dans le navigateur. Distinct de `requestExport`
 * ci-dessus (archive ZIP complète, asynchrone, lot `v5-rgpd`). */
export async function downloadCollectionCsv(): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}/me/export/collection.csv`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new ApiError(response.status, "Impossible de télécharger l'export CSV.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "collection.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
