import type { components } from "@pbm/api-client";

import { apiGet } from "@/lib/api/client";

/** Agrégat du tableau de bord : valeur dans le temps, plus fortes variations, derniers ajouts. */
export type DashboardResponse = components["schemas"]["DashboardResponse"];
/** Un point de la courbe de valeur totale de la collection. */
export type DashboardValuePoint = components["schemas"]["DashboardValuePoint"];
/** Une carte parmi les plus fortes hausses/baisses de valeur. */
export type DashboardMoverCard = components["schemas"]["DashboardMoverCard"];
/** Un exemplaire récemment ajouté à la collection. */
export type DashboardRecentAddition = components["schemas"]["DashboardRecentAddition"];

/** Tableau de bord de l'utilisateur (`GET /me/dashboard`) : tout est agrégé côté serveur. */
export function getDashboard(): Promise<DashboardResponse> {
  return apiGet<DashboardResponse>("/me/dashboard");
}
