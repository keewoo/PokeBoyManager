import { apiGet, apiJson } from "@/lib/api/client";
import type { EtatPartieReponse } from "@/lib/game/plateau";

// Contrats miroir de `apps/api/src/pbm_api/games/schemas.py` (`GameSummaryOut`). La liste des
// parties sert au salon (lot `j-salon-partie`) : reprise d'une partie en cours, rappel du dernier
// résultat. Toujours bornée au participant côté serveur — une partie d'autrui n'apparaît jamais.

// Statuts possibles d'une partie, miroir de `pbm_api.models.games` (`GAME_STATUS_*`).
/** Statut d'une partie en cours (miroir de `GAME_STATUS_*` côté serveur). */
export const GAME_EN_COURS = "en_cours";
/** Statut d'une partie achevée normalement. */
export const GAME_TERMINEE = "terminee";
/** Statut d'une partie abandonnée faute d'activité (expirée). */
export const GAME_EXPIREE = "expiree";

/** Résumé d'une partie pour le salon : statut, numéro d'action courant, vainqueur et raison de fin. */
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


// --- Replay d'une partie finie (lot `j-replay`) ------------------------------
// Contrats miroir de `apps/api/src/pbm_api/games/replay.py`. Le serveur n'ouvre le replay qu'une
// fois la partie finie : une partie en cours répond 409, et l'écran n'a aucun repli à inventer.

/** Les vues de replay reconnues par le serveur (`pbm_api.games.replay.VUES`). */
export const REPLAY_VUE_MOI = "moi";
/** Vue complète : les deux vues de joueur, servies ensemble (partie finie seulement). */
export const REPLAY_VUE_COMPLETE = "complete";

/** Le coup qui a mené à un rang : qui, quoi, quand, et l'empreinte de l'état obtenu. */
export type ReplayCoup = {
  numero: number;
  auteur: string;
  type: string;
  horodatage: string;
  empreinte: string;
};

/**
 * Un **rang** du replay : l'état de la partie à ce point, projeté pour chaque destinataire servi.
 *
 * `vues` et `evenements` sont indexés par identifiant de joueur du moteur : une seule entrée en
 * `vue=moi`, les deux en `vue=complete`. `coup` est `null` au rang 0 (aucun coup ne mène à l'état
 * initial).
 */
export type ReplayEtape = {
  rang: number;
  coup: ReplayCoup | null;
  vues: Record<string, unknown>;
  evenements: Record<string, unknown[]>;
};

/** Un siège de la partie rejouée : son joueur, son pseudo, et le niveau du bot s'il en tient un. */
export type ReplayJoueur = {
  seat: number;
  user_id: string;
  joueur_id: string;
  pseudo: string | null;
  bot_niveau: string | null;
};

/**
 * Une **page** de replay. `total` est le nombre de coups de la partie (donc `total + 1` rangs) et
 * `complet` dit si la page va jusqu'au bout : un client enchaîne les pages tant que `complet` est
 * faux. Le serveur ne tronque jamais en silence — c'est ce qui permet à l'écran de dire ce qu'il
 * n'a pas encore chargé plutôt que de laisser croire que la partie s'arrête là.
 */
export type ReplayPage = {
  game_id: string;
  statut: string;
  raison_fin: string | null;
  vainqueur_user_id: string | null;
  engagement: string;
  /** La graine révélée (volet « reveal » du commit-reveal), nulle si la partie n'est pas allée au bout. */
  graine: string | null;
  vue: string;
  joueurs: ReplayJoueur[];
  total: number;
  depuis: number;
  limite: number;
  complet: boolean;
  etapes: ReplayEtape[];
};

/**
 * Une page du replay d'une partie **finie**.
 *
 * Lève `ApiError` 404 si le compte n'a pas le droit de regarder (participant ou partage ouvert),
 * 409 si la partie est encore en cours, 422 sur une vue impossible (`vue=moi` demandée par un
 * spectateur) ou une page hors bornes.
 */
export function getReplay(
  gameId: string,
  options: { vue?: string; depuis?: number; limite?: number } = {},
): Promise<ReplayPage> {
  const params = new URLSearchParams();
  params.set("vue", options.vue ?? REPLAY_VUE_MOI);
  if (options.depuis !== undefined) params.set("depuis", String(options.depuis));
  if (options.limite !== undefined) params.set("limite", String(options.limite));
  return apiGet<ReplayPage>(`/games/${gameId}/replay?${params.toString()}`);
}

/** Un compte à qui le replay est ouvert : qui, par quel joueur, et depuis quand. */
export type PartageReplay = {
  user_id: string;
  pseudo: string | null;
  partage_par_user_id: string;
  created_at: string;
};

/** Les comptes à qui ce replay est ouvert (réservé aux deux joueurs : 404 sinon). */
export function listReplayPartages(gameId: string): Promise<PartageReplay[]> {
  return apiGet<PartageReplay[]>(`/games/${gameId}/replay/partages`);
}

/**
 * Ouvre le replay à un compte invité, par son **pseudo**. Idempotent côté serveur.
 *
 * Lève `ApiError` 404 si aucun compte invité ne porte ce pseudo (on ne révèle pas l'existence d'un
 * compte ordinaire), 422 si la cible joue déjà cette partie.
 */
export function ouvrirPartageReplay(gameId: string, pseudo: string): Promise<PartageReplay> {
  return apiJson<PartageReplay>("POST", `/games/${gameId}/replay/partages`, { pseudo });
}

/** Retire à un compte le droit de regarder ce replay (404 s'il n'y avait rien à retirer). */
export function fermerPartageReplay(gameId: string, userId: string): Promise<void> {
  return apiJson<void>("DELETE", `/games/${gameId}/replay/partages/${userId}`);
}
