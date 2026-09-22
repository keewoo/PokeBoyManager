import { apiGet, apiJson } from "@/lib/api/client";

export type CollectionSort =
  | "value_desc"
  | "value_asc"
  | "value_change_30d_desc"
  | "value_change_30d_asc"
  | "acquired_at_desc"
  | "acquired_at_asc"
  | "number_asc"
  | "name_asc";

export type CollectionListItem = {
  id: string;
  card_id: string;
  set_id: string;
  card_name: string;
  card_number: string;
  set_name: string;
  set_code: string;
  series: string | null;
  rarity: string | null;
  card_type: string | null;
  element_type: string | null;
  hp: number | null;
  language: string;
  variant: string;
  condition_grade: string | null;
  counterfeit_suspected: boolean;
  purchase_price: string | null;
  purchase_currency: string | null;
  acquired_at: string | null;
  value_eur: string | null;
  value_change_30d_eur: string | null;
  value_change_30d_pct: string | null;
  is_duplicate: boolean;
};

export type CollectionAggregates = {
  items_total: number;
  items_priced: number;
  items_missing_price: number;
  total_value_eur: string;
  value_change_7d_eur: string;
  value_change_30d_eur: string;
};

export type CollectionListResponse = {
  items: CollectionListItem[];
  next_cursor: string | null;
  aggregates: CollectionAggregates;
};

export type CollectionFacets = {
  sets: { set_id: string; name: string; code: string }[];
  series: string[];
  rarities: string[];
  card_types: string[];
  languages: string[];
  variants: string[];
  condition_grades: string[];
};

export type CollectionFilters = {
  q?: string;
  set_id?: string[];
  series?: string[];
  rarity?: string[];
  card_type?: string[];
  language?: string[];
  variant?: string[];
  condition_grade?: string[];
  value_min?: string;
  value_max?: string;
  acquired_from?: string;
  acquired_to?: string;
  duplicates?: boolean;
  counterfeit?: boolean;
  sort?: CollectionSort;
  cursor?: string;
  limit?: number;
};

function buildQuery(filters: CollectionFilters): string {
  const params = new URLSearchParams();
  const multi: (keyof CollectionFilters)[] = [
    "set_id",
    "series",
    "rarity",
    "card_type",
    "language",
    "variant",
    "condition_grade",
  ];
  for (const key of multi) {
    const values = filters[key] as string[] | undefined;
    values?.forEach((value) => params.append(key, value));
  }
  if (filters.q) params.set("q", filters.q);
  if (filters.value_min) params.set("value_min", filters.value_min);
  if (filters.value_max) params.set("value_max", filters.value_max);
  if (filters.acquired_from) params.set("acquired_from", filters.acquired_from);
  if (filters.acquired_to) params.set("acquired_to", filters.acquired_to);
  if (filters.duplicates) params.set("duplicates", "true");
  if (filters.counterfeit) params.set("counterfeit", "true");
  if (filters.sort) params.set("sort", filters.sort);
  if (filters.cursor) params.set("cursor", filters.cursor);
  if (filters.limit) params.set("limit", String(filters.limit));
  return params.toString();
}

export function listCollection(filters: CollectionFilters): Promise<CollectionListResponse> {
  const query = buildQuery(filters);
  return apiGet<CollectionListResponse>(`/me/collection${query ? `?${query}` : ""}`);
}

export function getCollectionFacets(): Promise<CollectionFacets> {
  return apiGet<CollectionFacets>("/me/collection/facets");
}

export type CreateCollectionItemPayload = {
  card_id: string;
  language?: string;
  variant?: string;
  quantity?: number;
  condition_grade?: string | null;
  purchase_price?: string | null;
  purchase_currency?: string | null;
  acquired_at?: string | null;
};

export function createCollectionItem(
  payload: CreateCollectionItemPayload
): Promise<{ collection_item_ids: string[] }> {
  return apiJson<{ collection_item_ids: string[] }>("POST", "/me/collection", payload);
}

export function deleteCollectionItem(itemId: string): Promise<void> {
  return apiJson<void>("DELETE", `/me/collection/${itemId}`);
}
