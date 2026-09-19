import type { components } from "@pbm/api-client";

import { apiJson } from "@/lib/api/client";

export type ExportResponse = components["schemas"]["ExportResponse"];

export function requestExport(): Promise<ExportResponse> {
  return apiJson<ExportResponse>("POST", "/me/export");
}
