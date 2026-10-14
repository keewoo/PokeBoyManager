/**
 * Réglages de **confort et d'accessibilité** du jeu (lot `j-accessibilite-jeu`) — données **pures**.
 *
 * Le public de ce jeu est un enfant et son entourage : trois réglages, et chacun répond à un
 * obstacle réel plutôt qu'à une case à cocher de conformité.
 *
 * - **animations** : les couper *globalement*. `prefers-reduced-motion` le fait déjà au niveau du
 *   système, mais tout le monde ne sait pas où ce réglage se trouve — et un enfant sur le téléphone
 *   d'un parent n'y touchera pas. Le réglage du jeu s'ajoute au système : **l'un des deux suffit**
 *   pour que plus rien ne bouge (jamais l'inverse — un réglage de jeu ne rallume pas ce que le
 *   système demande d'éteindre).
 * - **taille du texte** : agrandir tout ce qui se lit. Elle agit en posant un `font-size` sur la
 *   racine du document, donc sur toutes les tailles exprimées en `rem` — c'est-à-dire tout le
 *   produit. L'**arène** de la partie, elle, est dimensionnée en unités de conteneur (`cqw`/`cqh`,
 *   voir `.pbm-arena` dans `globals.css`) : elle ne grossit pas, et c'est voulu — le plateau doit
 *   tenir sur l'écran sans défilement (lot `j-plateau-layout`), la lisibilité d'une carte en jeu
 *   passe par son agrandissement (`CardZoom`).
 * - **temps rallongé** : doubler les horloges (DJ4). Ce réglage-là n'est pas cosmétique, il change
 *   les règles du temps d'une partie : il est donc **persisté côté serveur** et appliqué au
 *   lancement (`pbm_api.jeu.confort`), jamais décidé par l'écran.
 *
 * Pur (aucun React, aucune E/S, aucun accès au DOM) : testable sans navigateur. Le stockage local
 * vit dans {@link ../confort-provider}, et le contrat serveur dans `lib/api/confort.ts`.
 */

import { DECORS_REGLABLES } from "@/lib/game/decors";

/** Les animations du jeu jouent normalement (défaut). */
export const ANIMATIONS_COMPLETES = "completes";
/** Aucune animation n'est rendue : l'état du plateau reste lisible, il ne bouge plus. */
export const ANIMATIONS_REDUITES = "reduites";

/** Le vocabulaire du réglage d'animation, dans l'ordre d'affichage. */
export const ANIMATIONS = [ANIMATIONS_COMPLETES, ANIMATIONS_REDUITES] as const;
export type ReglageAnimations = (typeof ANIMATIONS)[number];

/** Les trois tailles de texte, dans l'ordre croissant. */
export const TAILLES_TEXTE = ["normale", "grande", "tres_grande"] as const;
export type ReglageTailleTexte = (typeof TAILLES_TEXTE)[number];

/**
 * Le facteur appliqué à la taille de police de la racine, par taille.
 *
 * Deux crans seulement, et volontairement modestes (+12,5 % puis +25 %) : au-delà, les écrans du
 * jeu cessent de tenir sur un téléphone, et un écran qui déborde n'aide personne. Le zoom du
 * navigateur reste disponible pour aller plus loin — il n'est pas remplacé par ce réglage.
 */
export const ECHELLE_TEXTE: Record<ReglageTailleTexte, number> = {
  normale: 1,
  grande: 1.125,
  tres_grande: 1.25,
};

/** Les réglages de confort d'un compte. */
export type ReglagesConfort = {
  animations: ReglageAnimations;
  taille_texte: ReglageTailleTexte;
  /** Les horloges de mes parties sont rallongées (DJ4) — décidé au lancement, côté serveur. */
  temps_rallonge: boolean;
  /**
   * Décor d'arène choisi (lot `j-arene-decors`), ou `null` pour « laisse le jeu choisir d'après
   * mon deck ».
   *
   * Le décor est rangé ici, avec les animations et la taille du texte, parce que c'est la même
   * sorte de réglage : il ne change **aucune** règle, seulement ce que le joueur voit, et il doit
   * suivre le compte d'un appareil à l'autre. Le vocabulaire des clés vit dans `lib/game/decors.ts`
   * (côté serveur : `pbm_api.jeu.decors`), et c'est le serveur qui refuse une clé inconnue.
   */
  decor: string | null;
};

/**
 * Les défauts : le jeu est animé, lisible et chronométré normalement.
 *
 * Ils doivent rester d'accord avec ceux du serveur (`pbm_api.jeu.confort.ReglagesConfort`) et avec
 * les `server_default` de la table : un test de parité le vérifie de chaque côté. Deux jeux de
 * défauts qui divergent, c'est un réglage qui change de sens selon qu'une ligne existe ou non.
 */
export const CONFORT_DEFAUT: ReglagesConfort = {
  animations: ANIMATIONS_COMPLETES,
  taille_texte: "normale",
  temps_rallonge: false,
  // Aucun décor imposé : le jeu suit le deck joué (lot `j-arene-decors`).
  decor: null,
};

/** Clé du cache local des réglages — il n'existe que pour éviter le clignotement au chargement. */
export const CLE_CONFORT = "pbm.jeu.confort";

/**
 * Ramène n'importe quelle forme (réponse serveur, cache local d'une version précédente, `null`) à
 * des réglages valides, en **retombant champ par champ** sur les défauts.
 *
 * Tolérant par nécessité : le cache local survit aux déploiements, et un réglage inconnu ne doit
 * jamais empêcher les deux autres de s'appliquer. Mais tolérant **sans silence** : une valeur hors
 * vocabulaire est remplacée par le défaut, elle n'est pas conservée telle quelle — l'écran afficherait
 * sinon un choix que le serveur refusera.
 */
export function normaliserConfort(brut: unknown): ReglagesConfort {
  const o = (brut ?? {}) as Record<string, unknown>;
  const animations = ANIMATIONS.includes(o.animations as ReglageAnimations)
    ? (o.animations as ReglageAnimations)
    : CONFORT_DEFAUT.animations;
  const taille = TAILLES_TEXTE.includes(o.taille_texte as ReglageTailleTexte)
    ? (o.taille_texte as ReglageTailleTexte)
    : CONFORT_DEFAUT.taille_texte;
  // Un décor inconnu (clé retirée depuis, cache local d'une version précédente) retombe sur
  // l'automatique : le joueur voit alors un décor cohérent avec son deck, jamais un fond nu.
  const decor =
    typeof o.decor === "string" && DECORS_REGLABLES.includes(o.decor) ? o.decor : CONFORT_DEFAUT.decor;
  return {
    animations,
    taille_texte: taille,
    temps_rallonge:
      typeof o.temps_rallonge === "boolean" ? o.temps_rallonge : CONFORT_DEFAUT.temps_rallonge,
    decor,
  };
}

/**
 * Les attributs à poser sur `<html>` pour que `globals.css` applique ces réglages.
 *
 * On passe par des attributs de données plutôt que par des styles en ligne pour une raison
 * pratique : le script anti-clignotement du `layout` les pose **avant** le premier rendu, avec la
 * même logique et sans React — et le CSS reste la seule source de vérité de ce que « animations
 * réduites » veut dire.
 */
export function attributsConfort(r: ReglagesConfort): Record<string, string> {
  return { "data-anim": r.animations, "data-texte": r.taille_texte };
}

/** Le nom du réglage d'animation, tel qu'un enfant le lit. */
export function libelleAnimations(valeur: string): string {
  if (valeur === ANIMATIONS_COMPLETES) return "Montrer les animations";
  if (valeur === ANIMATIONS_REDUITES) return "Ne pas animer (le plateau reste lisible)";
  return valeur;
}

/** Le nom d'une taille de texte, tel qu'un enfant le lit. */
export function libelleTailleTexte(valeur: string): string {
  if (valeur === "normale") return "Normale";
  if (valeur === "grande") return "Grande";
  if (valeur === "tres_grande") return "Très grande";
  return valeur;
}
