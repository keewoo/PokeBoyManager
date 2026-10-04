/**
 * Client de la file de demandes « je voudrais jouer cette carte » (`/me/demandes-cartes`, lot
 * `j-effets-couverture-outil`). Miroir des schémas serveur (`pbm_api.jeu.scripts.schemas`).
 * Bornée au joueur courant par le cookie de session : jamais les demandes d'un autre.
 */

import { apiGet, apiJson } from "@/lib/api/client";

/** Une demande du joueur : la carte, le statut posé, et sa jouabilité recalculée à la lecture. */
export type PlayRequest = {
  id: string;
  card_id: string;
  card_name: string;
  statut: string; // "en_attente" | "scriptee" | "refusee"
  note: string | null;
  jouable_maintenant: boolean;
  created_at: string;
  updated_at: string;
};

/** Les demandes du joueur courant. */
export type PlayRequestsResponse = { requests: PlayRequest[] };

/** Les demandes du joueur courant (`GET /me/demandes-cartes`). */
export function listPlayRequests(): Promise<PlayRequestsResponse> {
  return apiGet<PlayRequestsResponse>("/me/demandes-cartes");
}

/**
 * Signale (ou ré-ouvre) une demande pour une carte (`POST /me/demandes-cartes`). Idempotent par
 * carte côté serveur : re-demander ne crée pas de doublon. Lève `ApiError` sur une carte inconnue.
 */
export function requestPlayCard(cardId: string, note?: string): Promise<PlayRequest> {
  return apiJson<PlayRequest>("POST", "/me/demandes-cartes", { card_id: cardId, note });
}
