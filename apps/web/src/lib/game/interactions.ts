/**
 * Machine à états **pure** de l'interaction de jeu (lot `j-plateau-interactions`).
 *
 * Elle pilote, au-dessus de `actions_legales` (produit par le serveur), les deux modes d'entrée —
 * **tap-tap** et **glisser-déposer** — qui aboutissent aux mêmes transitions : choisir un coup,
 * choisir une cible, confirmer un coup irréversible, ou annuler tant que rien n'est validé. Aucune
 * règle n'est rejouée ici : elle ne fait que naviguer entre les coups que le moteur a déclarés.
 *
 * Tout est pur (aucune E/S, aucun React, aucun temps) : testable sans navigateur. `reduire` ne
 * **soumet** rien — elle rend l'état suivant et, le cas échéant, la `Soumission` à envoyer, que la
 * couche React exécute. C'est ce qui permet de prouver tout l'enchaînement en mémoire.
 */

import type { VueActionLegale, VueCible } from "@/lib/game/plateau";

/**
 * La sélection courante du joueur pendant qu'il prépare un coup :
 * - `repos` : rien de sélectionné ;
 * - `cible` : un coup à cibler est choisi, ses cibles valides sont illuminées ;
 * - `confirmation` : un coup irréversible attend un « oui » explicite (avec sa cible, si ciblé).
 */
export type Selection =
  | { phase: "repos" }
  | { phase: "cible"; action: VueActionLegale }
  | { phase: "confirmation"; action: VueActionLegale; cible: VueCible | null };

/** La sélection « rien en cours » — partagée, immuable. */
export const REPOS: Selection = { phase: "repos" };

/** Un coup prêt à partir au serveur : l'action exacte et, le cas échéant, la cible retenue. */
export type Soumission = { action: VueActionLegale; cible: VueCible | null };

/** Les gestes que l'écran traduit en transitions (tap-tap comme glisser-déposer y aboutissent). */
export type Evenement =
  | { t: "choisir-action"; action: VueActionLegale }
  | { t: "choisir-cible"; cible: VueCible }
  | { t: "confirmer" }
  | { t: "annuler" };

/** Ce que rend `reduire` : la sélection suivante et, si le coup part maintenant, sa `soumission`. */
export type Resultat = { selection: Selection; soumission?: Soumission };

function aCibles(action: VueActionLegale): boolean {
  return action.cibles.length > 0;
}

/** Un coup prêt : soit on demande confirmation (irréversible), soit on le soumet tout de suite. */
function jouerOuConfirmer(action: VueActionLegale, cible: VueCible | null): Resultat {
  if (action.irreversible) return { selection: { phase: "confirmation", action, cible } };
  return { selection: REPOS, soumission: { action, cible } };
}

/**
 * La transition pure : `(selection, evenement) → { selection suivante, soumission? }`.
 *
 * Un geste hors contexte (choisir une cible sans coup en cours, confirmer sans coup à confirmer, une
 * cible qui n'est pas dans la liste valide) **ne fait rien** : il rend la sélection inchangée, sans
 * jamais soumettre — une interface ne force pas une transition que l'état n'autorise pas.
 */
export function reduire(selection: Selection, evt: Evenement): Resultat {
  switch (evt.t) {
    case "choisir-action": {
      if (aCibles(evt.action)) return { selection: { phase: "cible", action: evt.action } };
      return jouerOuConfirmer(evt.action, null);
    }
    case "choisir-cible": {
      if (selection.phase !== "cible") return { selection };
      // La cible doit figurer parmi les cibles valides du coup : on ne soumet jamais une cible
      // que le serveur n'a pas illuminée (garde d'écran, le serveur revalide de toute façon).
      const valide = selection.action.cibles.some(
        (c) => c.reference === evt.cible.reference && c.genre === evt.cible.genre,
      );
      if (!valide) return { selection };
      return jouerOuConfirmer(selection.action, evt.cible);
    }
    case "confirmer": {
      if (selection.phase !== "confirmation") return { selection };
      return {
        selection: REPOS,
        soumission: { action: selection.action, cible: selection.cible },
      };
    }
    case "annuler":
      return { selection: REPOS };
  }
}

/** Les références des cibles à illuminer (vide hors de la phase de ciblage). */
export function ciblesIlluminees(selection: Selection): ReadonlySet<string> {
  if (selection.phase !== "cible") return new Set();
  return new Set(selection.action.cibles.map((c) => c.reference));
}

/** Vrai dès qu'un coup est en préparation (ciblage ou confirmation) : l'écran est « occupé ». */
export function enAttente(selection: Selection): boolean {
  return selection.phase !== "repos";
}

/** La cible valide correspondant à une référence pendant le ciblage, ou `null`. */
export function cibleParReference(selection: Selection, reference: string): VueCible | null {
  if (selection.phase !== "cible") return null;
  return selection.action.cibles.find((c) => c.reference === reference) ?? null;
}
