import { apiGet } from "@/lib/api/client";
import type { EtatPartieReponse } from "@/lib/game/plateau";

// Contrats miroir de `apps/api/src/pbm_api/games/schemas.py` (`GameSummaryOut`). La liste des
// parties sert au salon (lot `j-salon-partie`) : reprise d'une partie en cours, rappel du dernier
// résultat. Toujours bornée au participant côté serveur — une partie d'autrui n'apparaît jamais.

// Statuts possibles d'une partie, miroir de `pbm_api.models.games` (`GAME_STATUS_*`).
export const GAME_EN_COURS = "en_cours";
export const GAME_TERMINEE = "terminee";
export const GAME_EXPIREE = "expiree";

export type GameSummary = {
  id: string;
  status: string;
  current_numero: number;
  vainqueur_user_id: string | null;
  raison_fin: string | null;
  created_at: string;
  updated_at: string;
};

/** Les parties du joueur courant, de la plus récente à la plus ancienne (le serveur ordonne). */
export function listGames(): Promise<GameSummary[]> {
  return apiGet<GameSummary[]>("/games");
}

/**
 * La **vue autoritaire** de la partie pour le joueur courant (lot `j-plateau-layout`).
 *
 * Renvoie l'enveloppe `{ vue, evenements }` que produit `GET /games/{id}/state` (côté serveur,
 * `pbm_api.games.projection.vue_autoritaire` → `pbm_game.sortie.projeter`) : jamais la main adverse,
 * ni l'ordre d'une pioche, ni l'identité d'une récompense. Une partie où le joueur ne figure pas
 * répond 404 (`ApiError` de statut 404) — le plateau la traite comme inexistante, sans fuite.
 */
export function getGameState(gameId: string): Promise<EtatPartieReponse> {
  return apiGet<EtatPartieReponse>(`/games/${gameId}/state`);
}
