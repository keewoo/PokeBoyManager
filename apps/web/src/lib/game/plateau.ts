/**
 * Types et aides **pures** du plateau de jeu (lot `j-plateau-layout`).
 *
 * La forme décrite ici est le **contrat de sortie du serveur**, jamais une structure inventée côté
 * écran : c'est la « vue » projetée que renvoient `GET /games/{id}/state` (champ `vue`) et le canal
 * temps réel (`resync.vue`), produite par `pbm_game.sortie.projeter` →
 * `pbm_game.state.projection.vue`. Le serveur fait autorité : le client n'apprend jamais la main
 * adverse ni l'ordre d'une pioche — les zones cachées sont déjà réduites à un **nombre** à la
 * source. Ces types ne font que refléter ce filtrage ; aucune règle n'est rejouée ici.
 *
 * Tout est pur (aucune E/S, aucun React) : testable sans navigateur.
 */

/**
 * Une carte, telle que le serveur la laisse voir : identité d'instance et référence. Les cartes
 * **en jeu** (énergies attachées, Outil) portent en plus leur `type` (code d'élément), enrichi par
 * le serveur pour une pastille typée (lot `j-plateau-etat-visuel`) — `null`/absent quand le type
 * est inconnu du catalogue (repère neutre côté écran, jamais une couleur inventée).
 */
export type VueCarte = { instance_id: string; ref: string; type?: string | null };

/**
 * Un Pokémon en jeu (actif ou banc), entièrement public (R-3.6).
 *
 * `energies`/`cartes`/`outil` sont les cartes attachées ; `compteurs_degats` le total de dégâts
 * marqués ; `etats_speciaux` les états (triés par le serveur) ; `orientation` l'orientation
 * physique de la carte, déjà dérivée par le moteur (le détail visuel des dégâts, énergies et états
 * est le lot aval `j-plateau-etat-visuel` — ici on ne fait que porter l'information).
 */
export type VuePokemon = {
  cartes: VueCarte[];
  energies: VueCarte[];
  outil: VueCarte | null;
  compteurs_degats: number;
  etats_speciaux: string[];
  orientation: string;
  /**
   * Indicateurs d'affichage enrichis par le serveur (lot `j-plateau-etat-visuel`), à dessiner
   * **sans recalcul** : `pv_max` est le seuil de K.O. (PV imprimés + PV d'un Outil, R-13.1),
   * `pv_restants` = `pv_max − compteurs_degats` (jamais « imprimés − dégâts » côté écran) ; `type`
   * est le code d'élément du Pokémon. Absents quand les PV sont inconnus du catalogue (D9).
   */
  pv_max?: number;
  pv_restants?: number;
  type?: string | null;
};

/**
 * La vue d'un joueur. `main` (identités) n'est présent que pour soi ; `main_nombre` que pour
 * l'adversaire — la frontière anti-triche est posée côté serveur, on ne la rejoue pas. De même,
 * `pioche_nombre` et `recompenses_nombre` sont des nombres (zones cachées), et `recompenses_jetons`
 * (jetons opaques pour désigner une récompense) n'existe que pour soi.
 */
export type VueJoueur = {
  id: string;
  actif: VuePokemon | null;
  banc: VuePokemon[];
  defausse: VueCarte[];
  zone_perdue: VueCarte[];
  pioche_nombre: number;
  recompenses_nombre: number;
  main?: VueCarte[];
  main_nombre?: number;
  recompenses_jetons?: string[];
};

/** L'état du tour courant (qui joue, quelle phase, ce qui a déjà été fait ce tour). */
export type VueTour = {
  joueur_actif: string;
  numero: number;
  phase: string;
  energie_posee: boolean;
  supporter_joue: boolean;
  retraite_faite: boolean;
};

/** La vue complète d'une partie pour un joueur donné (`pour`). */
export type VuePartie = {
  schema_version: number;
  pour: string;
  joueurs: VueJoueur[];
  tour: VueTour;
  stade: VueCarte | null;
  stade_proprietaire: string | null;
  terminee: boolean;
  vainqueur: string | null;
  raison_fin: string | null;
  demande?: unknown;
};

/** Enveloppe renvoyée par `GET /games/{id}/state` : la vue + les événements (vides sur cette route). */
export type EtatPartieReponse = { vue: VuePartie; evenements: unknown[] };

export const BANC_MAX = 5;
export const RECOMPENSES_MAX = 6;

/** Le joueur « moi » (celui à qui la vue est destinée) et son adversaire. */
export type CampsDuJeu = { moi: VueJoueur; adversaire: VueJoueur };

/**
 * Sépare « moi » de « l'adversaire » à partir de `vue.pour`.
 *
 * Lève si le destinataire n'est pas dans la partie, ou si une partie n'a pas exactement deux
 * joueurs : on ne devine jamais un camp par défaut (pas de repli silencieux — un plateau à moitié
 * défini masquerait une vue corrompue au lieu de la signaler).
 */
export function separerCamps(vue: VuePartie): CampsDuJeu {
  const moi = vue.joueurs.find((j) => j.id === vue.pour);
  const adversaire = vue.joueurs.find((j) => j.id !== vue.pour);
  if (!moi || !adversaire || vue.joueurs.length !== 2) {
    throw new Error(
      `Vue de partie incohérente : « ${vue.pour} » absent ou nombre de joueurs ≠ 2 ` +
        `(${vue.joueurs.map((j) => j.id).join(", ")}).`,
    );
  }
  return { moi, adversaire };
}

/** `true` si c'est au destinataire de la vue de jouer. */
export function estMonTour(vue: VuePartie): boolean {
  return vue.tour.joueur_actif === vue.pour;
}

/**
 * Le nombre de cartes en main d'un joueur, quel que soit le regard : `main.length` pour soi,
 * `main_nombre` pour l'adversaire. Jamais les identités adverses — elles ne sont pas dans la vue.
 */
export function nombreEnMain(joueur: VueJoueur): number {
  if (joueur.main) return joueur.main.length;
  return joueur.main_nombre ?? 0;
}

/**
 * Le banc complété à `max` emplacements : chaque case est un Pokémon ou `null` (emplacement vide).
 *
 * Le plateau dessine toujours les cinq cases du banc (une table réelle a des emplacements fixes) ;
 * cette fonction garantit la longueur attendue sans que le rendu ait à compter.
 */
export function bancAvecVides(joueur: VueJoueur, max: number = BANC_MAX): (VuePokemon | null)[] {
  const cases: (VuePokemon | null)[] = joueur.banc.slice(0, max);
  while (cases.length < max) cases.push(null);
  return cases;
}

/** Le nombre de récompenses encore à prendre (zone cachée : un nombre, jamais les identités). */
export function recompensesRestantes(joueur: VueJoueur): number {
  return joueur.recompenses_nombre;
}

/**
 * La carte du dessus d'un Pokémon : l'évolution la plus récente, c'est-à-dire ce qui est visible sur
 * la table. `null` si la pile est vide (cas impossible côté serveur, mais on ne devine pas).
 */
export function carteDessus(pokemon: VuePokemon): VueCarte | null {
  return pokemon.cartes[pokemon.cartes.length - 1] ?? null;
}
