import { apiGet } from "@/lib/api/client";
import { getApiBaseUrl } from "@/lib/config";

/** Variante de tirage d'une carte, dimension de prix : normal, holo, reverse holo, première édition. */
export type PriceVariant = "normal" | "holo" | "reverse_holo" | "first_edition";

/** Le set (extension) auquel appartient une carte : identité, série, logo. */
export type CardSetOut = {
  id: string;
  name: string;
  code: string;
  series: string | null;
  release_date: string | null;
  total_cards: number | null;
  logo_url: string | null;
};

/** Classement d'une carte par rareté/valeur dans son groupe (calculé côté serveur). */
export type CardRankingOut = {
  rarity_rank: number | null;
  rarity_group_size: number | null;
  value_percentile: number | null;
};

/** Rang de cette carte au sein de la collection valorisée de l'utilisateur (position / total chiffré). */
export type OwnedCollectionRankOut = {
  position: number | null;
  total_priced: number;
};

/** Fiche complète d'une carte du catalogue : identité, prix par variante, classement, et ce que l'utilisateur en possède. */
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

/** Fiche d'une carte du catalogue (`GET /cards/{id}`), enrichie du contexte de collection de l'utilisateur. */
export function getCardDetail(cardId: string): Promise<CardDetail> {
  return apiGet<CardDetail>(`/cards/${cardId}`);
}

/** Fenêtre temporelle d'un historique de prix : 7, 30 ou 365 jours, ou tout l'historique. */
export type PriceHistoryRange = "7" | "30" | "365" | "all";

/** Un point de la courbe de prix : un jour, une valeur en euros. */
export type PriceHistoryPoint = {
  day: string;
  price_eur: string;
};

/** Série de prix d'une carte pour une variante donnée, sur la fenêtre demandée. */
export type PriceHistoryResponse = {
  card_id: string;
  variant: PriceVariant;
  points: PriceHistoryPoint[];
};

/** Historique de prix d'une carte pour une variante et une fenêtre (`GET /cards/{id}/price-history`). */
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

/** Détail de l'état estimé d'un exemplaire : centrage, coins, bords, surface, note globale et soupçon de contrefaçon. Estimation serveur, assortie d'un avertissement (`disclaimer`). */
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

/** Un exemplaire précis que l'utilisateur possède d'une carte donnée : langue, variante, état, prix d'achat, valeur estimée. */
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

/** Les exemplaires de cette carte que possède l'utilisateur (`GET /cards/{id}/my-items`), bornés à sa collection. */
export function getCardMyItems(cardId: string): Promise<MyCardItem[]> {
  return apiGet<MyCardItem[]>(`/cards/${cardId}/my-items`);
}

/** URL de la photo d'un exemplaire de collection (`/me/collection/{id}/photo`), à poser dans un `<img>` ; le cookie de session part avec la requête. */
export function collectionItemPhotoUrl(itemId: string): string {
  return `${getApiBaseUrl()}/me/collection/${itemId}/photo`;
}

/** Une anecdote sur une carte, toujours accompagnée de sa source (exigence de sourçage). */
export type Anecdote = {
  text: string;
  source_url: string;
};

/** Anecdotes générées par l'IA de l'utilisateur pour une carte ; `status` dit pourquoi la liste peut être vide (pas de contexte, pas de clé IA). */
export type CardInsights = {
  card_id: string;
  status: "ready" | "no_context" | "no_ai_key";
  anecdotes: Anecdote[];
  generated_at: string | null;
};

/** Anecdotes sourcées d'une carte (`GET /cards/{id}/insights`) ; le serveur décide si et comment elles sont générées. */
export function getCardInsights(cardId: string): Promise<CardInsights> {
  return apiGet<CardInsights>(`/cards/${cardId}/insights`);
}

/** Légalité d'une carte par format de jeu (standard, étendu) ; `null` = inconnu. */
export type Legalities = {
  standard: boolean | null;
  expanded: boolean | null;
};

/** Règle de récompenses attachée à une carte (ex. nombre de prix pris quand elle est mise K.O.). */
export type PrizeRule = {
  applies: boolean;
  prizes_taken: number | null;
  label: string;
};

/** Un deck de tournoi où la carte a été jouée, avec son classement et la source. */
export type TournamentDeck = {
  deck_name: string;
  tournament_name: string;
  tournament_url: string | null;
  placement: string;
};

/** Présence de la carte en tournoi : soit vérifiée (avec decks et source), soit indisponible. */
export type TournamentPresence = {
  status: "checked" | "unavailable";
  source_url: string | null;
  checked_at: string | null;
  decks: TournamentDeck[];
};

/** Étude en jeu rédigée par l'IA de l'utilisateur ; `no_ai_key` si aucune clé n'est déposée. */
export type Study = {
  status: "ready" | "no_ai_key";
  text: string | null;
  generated_at: string | null;
};

/** Une attaque d'une carte : nom, dégâts, coût en énergies, effet. */
export type Attack = { name: string; damage?: number | string; cost?: string[]; effect?: string };

/** Dossier « étude en jeu » d'une carte : légalités, règle de prix, attaques/talents, présence en tournoi et étude IA. */
export type InGameStudy = {
  card_id: string;
  legalities: Legalities;
  prize_rule: PrizeRule;
  attacks: Attack[] | null;
  abilities: { name: string; effect?: string }[] | null;
  tournament_presence: TournamentPresence;
  study: Study;
};

/** Étude en jeu d'une carte (`GET /cards/{id}/in-game-study`) : légalités, tournois et analyse IA, le tout décidé côté serveur. */
export function getInGameStudy(cardId: string): Promise<InGameStudy> {
  return apiGet<InGameStudy>(`/cards/${cardId}/in-game-study`);
}
