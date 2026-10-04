import { apiGet, apiJson } from "@/lib/api/client";
import { getApiBaseUrl, getCsrfCookieName } from "@/lib/config";

// Contrats miroir de `apps/api/src/pbm_api/decks/schemas.py` — une seule légalité, côté serveur,
// jamais recopiée côté écran (risque du lot « la même règle des deux côtés ») : l'écran affiche
// ce que l'API calcule, il ne le recalcule pas.

/** Format de jeu d'un deck, qui détermine quelles cartes sont légales. */
export type DeckFormat = "standard" | "expanded" | "unlimited";

/** Les formats proposés à l'écran, avec leur libellé français (source des listes déroulantes). */
export const DECK_FORMATS: { value: DeckFormat; label: string }[] = [
  { value: "standard", label: "Standard" },
  { value: "expanded", label: "Étendu" },
  { value: "unlimited", label: "Illimité" },
];

// Sévérités renvoyées par `pbm_api.decks.legality` (constantes stables réutilisées par l'écran).
/** Sévérité d'un problème de légalité qui rend le deck injouable (constante miroir du serveur). */
export const SEVERITY_BLOCKING = "bloquant";
/** Sévérité d'un problème de légalité simplement signalé, non bloquant (constante miroir du serveur). */
export const SEVERITY_WARNING = "avertissement";

/** Un problème de légalité relevé par le serveur sur un deck (code, message, sévérité, carte en cause). */
export type LegalityIssue = {
  code: string;
  message: string;
  severity: string;
  /** `possession` | `legalite` | `script` — ce qui bloque la carte (lot `j-effets-couverture-outil`). */
  category: string;
  card_id: string | null;
  card_name: string | null;
  detail: Record<string, unknown> | null;
};

/** Verdict de légalité d'un deck, calculé par le serveur : jouable ou non, taille, et la liste des problèmes. */
export type DeckLegality = {
  legal: boolean;
  card_count: number;
  size_ok: boolean;
  format: DeckFormat;
  format_label: string;
  issues: LegalityIssue[];
};

/** Une carte dans un deck : identité, quantité, et son statut de possession (possédées / manquantes / exclues). */
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

/** Un deck complet : ses cartes et son verdict de légalité (forme renvoyée par la plupart des mutations). */
export type DeckDetail = {
  id: string;
  name: string;
  format: DeckFormat;
  created_at: string;
  updated_at: string;
  cards: DeckCard[];
  legality: DeckLegality;
};

/** Résumé d'un deck pour la liste (sans le détail des cartes). */
export type DeckSummary = {
  id: string;
  name: string;
  format: DeckFormat;
  card_count: number;
  legal: boolean;
  created_at: string;
  updated_at: string;
};

/** Un résultat de recherche de cartes à ajouter à un deck, enrichi du contexte de possession et de présence dans le deck. */
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

/** Réponse paginée de la recherche de cartes pour un deck. */
export type DeckCardSearchResponse = {
  items: DeckCardSearchItem[];
  next_cursor: string | null;
};

/** Un set proposé comme facette de la recherche de cartes de deck. */
export type DeckCardFacetSet = { set_id: string; name: string; code: string };

/** Valeurs de filtres disponibles pour la recherche de cartes de deck (sets, raretés, types, plage de PV). */
export type DeckCardFacets = {
  sets: DeckCardFacetSet[];
  rarities: string[];
  card_types: string[];
  hp_min: number | null;
  hp_max: number | null;
  owned_card_count: number;
  duplicate_card_count: number;
};

/** Critères de recherche de cartes à ajouter à un deck (requête, filtres, pagination). */
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

/** Liste les decks de l'utilisateur (`GET /me/decks`). */
export function listDecks(): Promise<{ decks: DeckSummary[] }> {
  return apiGet<{ decks: DeckSummary[] }>("/me/decks");
}

/** Détail d'un deck avec ses cartes et sa légalité (`GET /me/decks/{id}`) ; borné à l'utilisateur. */
export function getDeck(deckId: string): Promise<DeckDetail> {
  return apiGet<DeckDetail>(`/me/decks/${deckId}`);
}

/** Crée un deck (`POST /me/decks`) et renvoie son détail (y compris la légalité d'un deck vide). */
export function createDeck(payload: {
  name: string;
  format?: DeckFormat;
}): Promise<DeckDetail> {
  return apiJson<DeckDetail>("POST", "/me/decks", payload);
}

/** Renomme un deck ou change son format (`PATCH /me/decks/{id}`) ; la légalité est recalculée côté serveur. */
export function updateDeck(
  deckId: string,
  payload: { name?: string; format?: DeckFormat }
): Promise<DeckDetail> {
  return apiJson<DeckDetail>("PATCH", `/me/decks/${deckId}`, payload);
}

/** Supprime un deck (`DELETE /me/decks/{id}`). */
export function deleteDeck(deckId: string): Promise<void> {
  return apiJson<void>("DELETE", `/me/decks/${deckId}`);
}

/** Duplique un deck (`POST /me/decks/{id}/duplicate`) et renvoie la copie. */
export function duplicateDeck(deckId: string): Promise<DeckDetail> {
  return apiJson<DeckDetail>("POST", `/me/decks/${deckId}/duplicate`);
}

/** Fixe la quantité d'une carte dans un deck (`PUT /me/decks/{id}/cards/{cardId}`) ; renvoie le deck à jour. */
export function setDeckCard(
  deckId: string,
  cardId: string,
  quantity: number
): Promise<DeckDetail> {
  return apiJson<DeckDetail>("PUT", `/me/decks/${deckId}/cards/${cardId}`, { quantity });
}

/** Retire entièrement une carte d'un deck (`DELETE /me/decks/{id}/cards/{cardId}`). */
export function removeDeckCard(deckId: string, cardId: string): Promise<DeckDetail> {
  return apiJson<DeckDetail>("DELETE", `/me/decks/${deckId}/cards/${cardId}`);
}

/** Valeurs de filtres pour la recherche de cartes de deck (`GET /me/decks/cards/facets`). */
export function getDeckCardFacets(): Promise<DeckCardFacets> {
  return apiGet<DeckCardFacets>("/me/decks/cards/facets");
}

// ---- alertes, remplacements et historique (mission `v7-decks-collection-sync`) ----
// Miroir de `apps/api/src/pbm_api/decks/schemas.py`. Une carte quittée la collection ne modifie
// jamais un deck en silence : l'API inscrit une alerte, l'écran la montre et propose — c'est le
// joueur qui tranche.

/** Alerte inscrite par le serveur quand une carte quitte la collection et rend un deck incomplet (sert aussi d'événement d'historique). */
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

/** Les alertes de deck et le nombre non lues (pour la pastille de notification). */
export type DeckAlertsResponse = {
  alerts: DeckAlert[];
  unread_count: number;
};

/** Une carte proposée en remplacement d'une carte devenue indisponible dans un deck. */
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

/** Les remplacements suggérés pour une carte donnée d'un deck. */
export type DeckReplacementsResponse = {
  card_id: string;
  replacements: DeckReplacement[];
};

/** L'historique des événements (alertes) d'un deck. */
export type DeckHistoryResponse = {
  deck_id: string;
  events: DeckAlert[];
};

/** Récupère les alertes de deck (`GET /me/decks/alerts`), par défaut seulement les non lues. */
export function fetchDeckAlerts(unreadOnly = true): Promise<DeckAlertsResponse> {
  return apiGet<DeckAlertsResponse>(`/me/decks/alerts?unread_only=${unreadOnly ? "true" : "false"}`);
}

/** Marque des alertes comme lues (`POST /me/decks/alerts/read`) ; sans `eventIds`, toutes le sont. */
export function markDeckAlertsRead(eventIds?: string[]): Promise<DeckAlertsResponse> {
  return apiJson<DeckAlertsResponse>("POST", "/me/decks/alerts/read", {
    event_ids: eventIds ?? null,
  });
}

/** Propose des remplacements pour une carte d'un deck (`GET .../replacements`) ; le serveur choisit les candidats. */
export function fetchDeckReplacements(
  deckId: string,
  cardId: string,
  limit = 10
): Promise<DeckReplacementsResponse> {
  return apiGet<DeckReplacementsResponse>(
    `/me/decks/${deckId}/cards/${cardId}/replacements?limit=${limit}`
  );
}

/** Historique des événements d'un deck (`GET /me/decks/{id}/history`). */
export function fetchDeckHistory(deckId: string): Promise<DeckHistoryResponse> {
  return apiGet<DeckHistoryResponse>(`/me/decks/${deckId}/history`);
}

/** Recherche de cartes à ajouter à un deck (`GET /me/decks/cards`), filtrée et paginée côté serveur. */
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

/**
 * Télécharge l'export d'un deck (`GET /me/decks/{id}/export?fmt=`), en texte ou PDF. Passe par
 * `fetch` (et non un `<a href>` nu) pour emporter le cookie de session sur l'origine d'API ;
 * renvoie le blob et le nom de fichier extrait de `Content-Disposition`. Lève sur échec.
 */
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

/** Une tranche de statistique de deck : une clé, son libellé, et un décompte (sert aux histogrammes). */
export type DeckStatBucket = { key: string; label: string; count: number };

/** Valorisation d'un deck : total en euros et couverture (cartes/exemplaires chiffrés ou non). */
export type DeckValue = {
  total_eur: string | null;
  priced_cards: number;
  missing_price_cards: number;
  priced_copies: number;
  counted_copies: number;
};

/** Statistiques d'un deck calculées côté serveur : répartitions (types, rôles, PV, courbe de coût), doublons, valeur. */
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

/** Statistiques d'un deck (`GET /me/decks/{id}/stats`) ; tous les chiffres viennent du serveur. */
export function fetchDeckStats(deckId: string): Promise<DeckStats> {
  return apiGet<DeckStats>(`/me/decks/${deckId}/stats`);
}

// ---- assistant IA de construction (mission `v7-deck-ia`) ----
// Miroir de `ProposeDeckRequest` / `DeckProposalResponse`
// (apps/api/src/pbm_api/decks/schemas.py). La proposition est corrigée puis écrite côté serveur,
// et sa légalité recalculée là-bas : l'écran affiche `response.deck` tel quel, il ne le devine pas.

/** Préférence de type donnée à l'assistant IA, avec une part souhaitée optionnelle. */
export type DeckTypePreference = { type: string; share?: number | null };

/** Consignes passées à l'assistant IA de construction de deck (types, énergies, style, cartes imposées, taille). */
export type ProposeDeckRequest = {
  types?: DeckTypePreference[];
  energy_types?: string[];
  style?: string | null;
  must_include?: string[];
  size?: number;
};

/** Justification par l'IA d'une carte retenue dans la proposition (quantité et raison). */
export type DeckProposalExplanation = {
  card_id: string;
  card_name: string;
  quantity: number;
  reason: string;
};

/** Correction appliquée par le serveur à la proposition de l'IA (ex. carte illégale retirée). */
export type DeckProposalCorrection = {
  code: string;
  message: string;
};

/** Résultat de l'assistant IA : le deck écrit et re-légalisé côté serveur, ses explications, corrections et coût en jetons. */
export type DeckProposalResponse = {
  deck: DeckDetail;
  explanations: DeckProposalExplanation[];
  corrections: DeckProposalCorrection[];
  summary: string | null;
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
};

/** Demande à l'IA de l'utilisateur de composer un deck (`POST /me/decks/{id}/propose`) ; le serveur corrige, écrit et recalcule la légalité — l'écran affiche `response.deck` tel quel. */
export function proposeDeck(
  deckId: string,
  payload: ProposeDeckRequest
): Promise<DeckProposalResponse> {
  return apiJson<DeckProposalResponse>("POST", `/me/decks/${deckId}/propose`, payload);
}
