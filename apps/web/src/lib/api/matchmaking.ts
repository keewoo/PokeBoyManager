import { apiGet, apiJson } from "@/lib/api/client";

// Contrats miroir de `apps/api/src/pbm_api/routers/matchmaking.py`. Le serveur fait autorité : le
// client propose un `deck_id`, le serveur vérifie et refuse en nommant ce qui manque. L'écran
// n'applique aucune règle — il affiche l'état réel de la file et la jouabilité calculée là-bas.

// Statuts de la file, miroir de `FileOut.status`.
/** Statut de file : le joueur est apparié, une partie est créée (miroir de `FileOut.status`). */
export const FILE_APPARIE = "apparie";
/** Statut de file : le joueur attend un adversaire. */
export const FILE_EN_ATTENTE = "en_attente";
/** Statut de file : le joueur n'est pas dans la file. */
export const FILE_ABSENT = "absent";

/** État de la recherche d'adversaire : statut, partie éventuelle, rang et temps d'attente. */
export type FileState = {
  status: string;
  game_id: string | null;
  adversaire_user_id: string | null;
  position: number | null;
  joueurs_en_file: number | null;
  attente_secondes: number | null;
};

/** Présence des joueurs (en ligne, en partie, en file) et chemins de repli quand personne n'est disponible. */
export type Presence = {
  en_ligne: number;
  en_partie: number;
  en_file: number;
  autres_disponibles: number;
  // Chemins de repli quand personne n'est disponible : "invitation", "entrainement_bot".
  options: string[];
};

/** Une carte qui empêche un deck d'entrer en file, avec la raison du refus (le serveur nomme ce qui manque). */
export type RefusDeck = { carte: string; raison: string };

/** Verdict de jouabilité d'un deck pour le matchmaking : jouable ou non, et la liste des refus. */
export type DeckJouabilite = {
  deck_id: string;
  jouable: boolean;
  refus: RefusDeck[];
};

/** L'état réel de la recherche : apparié (partie créée), en attente (rang, temps), ou absent. */
export function getQueue(): Promise<FileState> {
  return apiGet<FileState>("/matchmaking/queue");
}

/** Entre dans la file avec un deck et tente un appariement immédiat (apparié ou en attente). */
export function enterQueue(deckId: string): Promise<FileState> {
  return apiJson<FileState>("POST", "/matchmaking/queue", { deck_id: deckId });
}

/** Annule la recherche : retire le joueur de la file. Idempotent. */
export function leaveQueue(): Promise<FileState> {
  return apiJson<FileState>("DELETE", "/matchmaking/queue");
}

/** La présence des comptes invités, et les options de repli s'il n'y a personne à affronter. */
export function getPresence(): Promise<Presence> {
  return apiGet<Presence>("/matchmaking/presence");
}

/**
 * La jouabilité d'un deck **avant** d'entrer en file (le serveur rejoue le contrôle d'entrée).
 * `jouable` faux → `refus` nomme chaque carte en cause ; un deck d'autrui répond 404 (ApiError).
 */
export function checkDeckPlayable(deckId: string): Promise<DeckJouabilite> {
  return apiGet<DeckJouabilite>(`/matchmaking/decks/${deckId}/jouabilite`);
}
