import { apiGet, apiJson } from "@/lib/api/client";
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


/** Un coup soumis par le joueur : son type, ses paramètres, et le numéro d'action qu'il croit prochain. */
export type CoupSoumis = {
  type: string;
  params: Record<string, unknown>;
  numero_attendu: number;
};

/**
 * Joue un coup — **le serveur fait autorité** : il le rejoue, le valide, et renvoie la vue projetée
 * du joueur après coup (`{ vue, evenements, numero }`). Un coup illégal lève `ApiError` de statut
 * 422 dont le `message` porte la **raison du moteur** (règle `R-x.y` en clair) ; un conflit de
 * numéro ou une partie close, 409. `numero_attendu` assure l'**idempotence** : renvoyer deux fois le
 * même coup au même numéro (double clic, renvoi réseau) ne le joue qu'une fois.
 *
 * L'auteur du coup n'est jamais dans le corps : le serveur l'impose depuis la session — un client ne
 * peut pas agir sous une autre identité. Abandonner passe par ce même chemin (c'est une action
 * légale, irréversible), pas par une route à part.
 */
export function playAction(gameId: string, coup: CoupSoumis): Promise<EtatPartieReponse> {
  return apiJson<EtatPartieReponse>("POST", `/games/${gameId}/actions`, coup);
}
