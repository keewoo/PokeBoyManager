import type { components } from "@pbm/api-client";

import { apiGet } from "@/lib/api/client";

export type DashboardResponse = components["schemas"]["DashboardResponse"];
export type DashboardValuePoint = components["schemas"]["DashboardValuePoint"];
export type DashboardMoverCard = components["schemas"]["DashboardMoverCard"];
export type DashboardRecentAddition = components["schemas"]["DashboardRecentAddition"];

export function getDashboard(): Promise<DashboardResponse> {
  return apiGet<DashboardResponse>("/me/dashboard");
}
