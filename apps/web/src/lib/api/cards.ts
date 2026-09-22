import { apiGet } from "@/lib/api/client";
import { getApiBaseUrl } from "@/lib/config";

export type PriceVariant = "normal" | "holo" | "reverse_holo" | "first_edition";

export type CardSetOut = {
  id: string;
  name: string;
  code: string;
  series: string | null;
  release_date: string | null;
  total_cards: number | null;
  logo_url: string | null;
};

export type CardRankingOut = {
  rarity_rank: number | null;
  rarity_group_size: number | null;
  value_percentile: number | null;
};

export type OwnedCollectionRankOut = {
  position: number | null;
  total_priced: number;
};

export type CardDetail = {
  id: string;
  name: string;
  number: string;
  rarity: string | null;
  supertype: string | null;
  element_type: string | null;
  hp: number | null;
  has_image: boolean;
  illustrator: string | null;
  set: CardSetOut;
  prices_eur: Partial<Record<PriceVariant, string | null>>;
  ranking: CardRankingOut;
  owned_count: number;
  collection_rank: OwnedCollectionRankOut | null;
};

export function getCardDetail(cardId: string): Promise<CardDetail> {
  return apiGet<CardDetail>(`/cards/${cardId}`);
}

export type PriceHistoryRange = "7" | "30" | "365" | "all";

export type PriceHistoryPoint = {
  day: string;
  price_eur: string;
};

export type PriceHistoryResponse = {
  card_id: string;
  variant: PriceVariant;
  points: PriceHistoryPoint[];
};

export function getCardPriceHistory(
  cardId: string,
  variant: PriceVariant,
  range: PriceHistoryRange
): Promise<PriceHistoryResponse> {
  const params = new URLSearchParams({ variant, range });
  return apiGet<PriceHistoryResponse>(`/cards/${cardId}/price-history?${params.toString()}`);
}

/** Forme écrite par `pbm_api.state.service` (lot `v3-etat`) — `MyCardItemOut.condition_detail`
 * est un `dict` non typé côté API (`{[key: string]: unknown}` dans le schéma OpenAPI généré). */
export type ConditionAxis = {
  near_px: number;
  far_px: number;
  ratio: string;
  grade: string;
} | null;

export type ConditionDetail = {
  centering: {
    horizontal: ConditionAxis;
    vertical: ConditionAxis;
    grade: string | null;
  } | null;
  corners: { grade: string | null; confidence: number | null; note: string | null } | null;
  edges: { grade: string | null; confidence: number | null; note: string | null } | null;
  surface: { grade: string | null; confidence: number | null; note: string | null } | null;
  overall_grade: string | null;
  overall_grade_label: string | null;
  score_10: number | null;
  counterfeit_suspected: boolean;
  counterfeit_reasons: string[];
  disclaimer: string;
};

export type MyCardItem = {
  id: string;
  language: string;
  variant: PriceVariant;
  condition_grade: string | null;
  counterfeit_suspected: boolean;
  purchase_price: string | null;
  purchase_currency: string | null;
  purchase_price_eur: string | null;
  acquired_at: string | null;
  value_eur: string | null;
  has_photo: boolean;
  condition_detail: ConditionDetail | null;
};

export function getCardMyItems(cardId: string): Promise<MyCardItem[]> {
  return apiGet<MyCardItem[]>(`/cards/${cardId}/my-items`);
}

export function collectionItemPhotoUrl(itemId: string): string {
  return `${getApiBaseUrl()}/me/collection/${itemId}/photo`;
}

export type Anecdote = {
  text: string;
  source_url: string;
};

export type CardInsights = {
  card_id: string;
  status: "ready" | "no_context" | "no_ai_key";
  anecdotes: Anecdote[];
  generated_at: string | null;
};

export function getCardInsights(cardId: string): Promise<CardInsights> {
  return apiGet<CardInsights>(`/cards/${cardId}/insights`);
}

export type Legalities = {
  standard: boolean | null;
  expanded: boolean | null;
};

export type PrizeRule = {
  applies: boolean;
  prizes_taken: number | null;
  label: string;
};

export type TournamentDeck = {
  deck_name: string;
  tournament_name: string;
  tournament_url: string | null;
  placement: string;
};

export type TournamentPresence = {
  status: "checked" | "unavailable";
  source_url: string | null;
  checked_at: string | null;
  decks: TournamentDeck[];
};

export type Study = {
  status: "ready" | "no_ai_key";
  text: string | null;
  generated_at: string | null;
};

export type Attack = { name: string; damage?: number | string; cost?: string[]; effect?: string };

export type InGameStudy = {
  card_id: string;
  legalities: Legalities;
  prize_rule: PrizeRule;
  attacks: Attack[] | null;
  abilities: { name: string; effect?: string }[] | null;
  tournament_presence: TournamentPresence;
  study: Study;
};

export function getInGameStudy(cardId: string): Promise<InGameStudy> {
  return apiGet<InGameStudy>(`/cards/${cardId}/in-game-study`);
}
