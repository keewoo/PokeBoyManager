import { apiGet, apiJson } from "@/lib/api/client";
import { getApiBaseUrl, getCsrfCookieName } from "@/lib/config";

// Contrats miroir de `apps/api/src/pbm_api/decks/schemas.py` — une seule légalité, côté serveur,
// jamais recopiée côté écran (risque du lot « la même règle des deux côtés ») : l'écran affiche
// ce que l'API calcule, il ne le recalcule pas.

export type DeckFormat = "standard" | "expanded" | "unlimited";

export const DECK_FORMATS: { value: DeckFormat; label: string }[] = [
  { value: "standard", label: "Standard" },
  { value: "expanded", label: "Étendu" },
  { value: "unlimited", label: "Illimité" },
];

// Sévérités renvoyées par `pbm_api.decks.legality` (constantes stables réutilisées par l'écran).
export const SEVERITY_BLOCKING = "bloquant";
export const SEVERITY_WARNING = "avertissement";

export type LegalityIssue = {
  code: string;
  message: string;
  severity: string;
  card_id: string | null;
  card_name: string | null;
  detail: Record<string, unknown> | null;
};

export type DeckLegality = {
  legal: boolean;
  card_count: number;
  size_ok: boolean;
  format: DeckFormat;
  format_label: string;
  issues: LegalityIssue[];
};

export type DeckCard = {
  card_id: string;
  card_name: string;
  card_number: string;
  set_id: string;
  set_name: string;
  set_code: string;
  image_url: string | null;
  supertype: string | null;
  rarity: string | null;
  quantity: number;
  is_basic_energy: boolean;
  is_special_energy: boolean;
  is_basic_pokemon: boolean;
  owned: number;
  missing: number;
  in_collection: boolean;
  in_format: boolean;
  counterfeit_excluded: number;
};

export type DeckDetail = {
  id: string;
  name: string;
  format: DeckFormat;
  created_at: string;
  updated_at: string;
  cards: DeckCard[];
  legality: DeckLegality;
};

export type DeckSummary = {
  id: string;
  name: string;
  format: DeckFormat;
  card_count: number;
  legal: boolean;
  created_at: string;
  updated_at: string;
};

export type DeckCardSearchItem = {
  card_id: string;
  set_id: string;
  number: string;
  name: string;
  set_name: string;
  set_code: string;
  series: string | null;
  rarity: string | null;
  supertype: string | null;
  hp: number | null;
  image_url: string | null;
  energy_type: string | null;
  is_basic_energy: boolean;
  is_special_energy: boolean;
  value_eur: string | null;
  owned_count: number;
  in_deck_count: number;
  is_duplicate: boolean;
};

export type DeckCardSearchResponse = {
  items: DeckCardSearchItem[];
  next_cursor: string | null;
};

export type DeckCardFacetSet = { set_id: string; name: string; code: string };

export type DeckCardFacets = {
  sets: DeckCardFacetSet[];
  rarities: string[];
  card_types: string[];
  hp_min: number | null;
  hp_max: number | null;
  owned_card_count: number;
  duplicate_card_count: number;
};

export type DeckCardSearchParams = {
  q?: string;
  setId?: string;
  rarity?: string;
  cardType?: string;
  owned?: boolean;
  duplicates?: boolean;
  deckId?: string;
  cursor?: string;
  limit?: number;
};

export function listDecks(): Promise<{ decks: DeckSummary[] }> {
  return apiGet<{ decks: DeckSummary[] }>("/me/decks");
}

export function getDeck(deckId: string): Promise<DeckDetail> {
  return apiGet<DeckDetail>(`/me/decks/${deckId}`);
}

export function createDeck(payload: {
  name: string;
  format?: DeckFormat;
}): Promise<DeckDetail> {
  return apiJson<DeckDetail>("POST", "/me/decks", payload);
}

export function updateDeck(
  deckId: string,
  payload: { name?: string; format?: DeckFormat }
): Promise<DeckDetail> {
  return apiJson<DeckDetail>("PATCH", `/me/decks/${deckId}`, payload);
}

export function deleteDeck(deckId: string): Promise<void> {
  return apiJson<void>("DELETE", `/me/decks/${deckId}`);
}

export function duplicateDeck(deckId: string): Promise<DeckDetail> {
  return apiJson<DeckDetail>("POST", `/me/decks/${deckId}/duplicate`);
}

export function setDeckCard(
  deckId: string,
  cardId: string,
  quantity: number
): Promise<DeckDetail> {
  return apiJson<DeckDetail>("PUT", `/me/decks/${deckId}/cards/${cardId}`, { quantity });
}

export function removeDeckCard(deckId: string, cardId: string): Promise<DeckDetail> {
  return apiJson<DeckDetail>("DELETE", `/me/decks/${deckId}/cards/${cardId}`);
}

export function getDeckCardFacets(): Promise<DeckCardFacets> {
  return apiGet<DeckCardFacets>("/me/decks/cards/facets");
}

// ---- alertes, remplacements et historique (mission `v7-decks-collection-sync`) ----
// Miroir de `apps/api/src/pbm_api/decks/schemas.py`. Une carte quittée la collection ne modifie
// jamais un deck en silence : l'API inscrit une alerte, l'écran la montre et propose — c'est le
// joueur qui tranche.

export type DeckAlert = {
  id: string;
  deck_id: string;
  deck_name: string;
  event_type: string; // "card_incomplete"
  reason: string; // "removed" | "counterfeit"
  card_id: string | null;
  card_name: string;
  required: number;
  owned: number;
  missing: number;
  read: boolean;
  created_at: string;
};

export type DeckAlertsResponse = {
  alerts: DeckAlert[];
  unread_count: number;
};

export type DeckReplacement = {
  card_id: string;
  set_id: string | null;
  number: string;
  name: string;
  set_name: string;
  set_code: string;
  supertype: string | null;
  hp: number | null;
  image_url: string | null;
  owned_count: number;
  reason: string;
};

export type DeckReplacementsResponse = {
  card_id: string;
  replacements: DeckReplacement[];
};

export type DeckHistoryResponse = {
  deck_id: string;
  events: DeckAlert[];
};

export function fetchDeckAlerts(unreadOnly = true): Promise<DeckAlertsResponse> {
  return apiGet<DeckAlertsResponse>(`/me/decks/alerts?unread_only=${unreadOnly ? "true" : "false"}`);
}

export function markDeckAlertsRead(eventIds?: string[]): Promise<DeckAlertsResponse> {
  return apiJson<DeckAlertsResponse>("POST", "/me/decks/alerts/read", {
    event_ids: eventIds ?? null,
  });
}

export function fetchDeckReplacements(
  deckId: string,
  cardId: string,
  limit = 10
): Promise<DeckReplacementsResponse> {
  return apiGet<DeckReplacementsResponse>(
    `/me/decks/${deckId}/cards/${cardId}/replacements?limit=${limit}`
  );
}

export function fetchDeckHistory(deckId: string): Promise<DeckHistoryResponse> {
  return apiGet<DeckHistoryResponse>(`/me/decks/${deckId}/history`);
}

export function searchDeckCards(
  params: DeckCardSearchParams
): Promise<DeckCardSearchResponse> {
  const query = new URLSearchParams();
  if (params.q) query.set("q", params.q);
  if (params.setId) query.set("set_id", params.setId);
  if (params.rarity) query.set("rarity", params.rarity);
  if (params.cardType) query.set("card_type", params.cardType);
  if (params.owned) query.set("owned", "true");
  if (params.duplicates) query.set("duplicates", "true");
  if (params.deckId) query.set("deck_id", params.deckId);
  if (params.cursor) query.set("cursor", params.cursor);
  if (params.limit) query.set("limit", String(params.limit));
  const suffix = query.toString();
  return apiGet<DeckCardSearchResponse>(`/me/decks/cards${suffix ? `?${suffix}` : ""}`);
}

// Export : l'API renvoie une pièce jointe (texte ou PDF). On la télécharge par `fetch` (le
// cookie de session part avec `credentials: "include"`, comme tout le client) plutôt que par un
// `<a href>` nu, qui n'emporterait pas la session sur une origine d'API distincte. La CSP
// `connect-src` autorise déjà cette origine (`src/middleware.ts`).
function readCsrfCookie(): string | null {
  if (typeof document === "undefined") return null;
  const name = getCsrfCookieName();
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export async function fetchDeckExport(
  deckId: string,
  fmt: "text" | "pdf"
): Promise<{ blob: Blob; filename: string }> {
  const csrf = readCsrfCookie();
  const response = await fetch(`${getApiBaseUrl()}/me/decks/${deckId}/export?fmt=${fmt}`, {
    credentials: "include",
    headers: csrf ? { "X-CSRF-Token": csrf } : {},
  });
  if (!response.ok) {
    throw new Error("L'export a échoué.");
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match?.[1] ?? `deck.${fmt === "pdf" ? "pdf" : "txt"}`;
  return { blob: await response.blob(), filename };
}

// ---- statistiques de deck (mission `v7-decks-stats`) ----
// Miroir de `DeckStatsOut` (apps/api/src/pbm_api/decks/schemas.py). Tous les chiffres viennent du
// serveur (catalogue + valorisation), jamais recalculés côté écran.

export type DeckStatBucket = { key: string; label: string; count: number };

export type DeckValue = {
  total_eur: string | null;
  priced_cards: number;
  missing_price_cards: number;
  priced_copies: number;
  counted_copies: number;
};

export type DeckStats = {
  deck_id: string;
  card_count: number;
  distinct_cards: number;
  by_supertype: DeckStatBucket[];
  by_role: DeckStatBucket[];
  type_distribution: DeckStatBucket[];
  untyped_pokemon: number;
  attack_cost_curve: DeckStatBucket[];
  attacks_counted: number;
  average_hp: number | null;
  pokemon_with_hp: number;
  stage_distribution: DeckStatBucket[];
  has_basic_pokemon: boolean;
  evolution_copies_without_base: number;
  special_cards: number;
  duplicate_copies: number;
  duplicate_ratio: number;
  value: DeckValue;
};

export function fetchDeckStats(deckId: string): Promise<DeckStats> {
  return apiGet<DeckStats>(`/me/decks/${deckId}/stats`);
}
