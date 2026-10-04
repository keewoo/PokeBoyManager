/**
 * Catégories de blocage d'un constat de légalité, côté écran — miroir de
 * `pbm_api.decks.legality` (lot `j-effets-couverture-outil`). Le serveur fait autorité : l'écran
 * ne fait que NOMMER ce qu'il renvoie (possession / légalité / script), pour que le constructeur
 * dise à chaque carte refusée CE QUI la bloque (critère n°1). Aucune règle n'est rejouée ici.
 */

export const LEGALITY_CATEGORY_POSSESSION = "possession";
export const LEGALITY_CATEGORY_LEGALITE = "legalite";
export const LEGALITY_CATEGORY_SCRIPT = "script";

/** Le code de constat « effet non scripté » (D9), tel que le renvoie l'API. */
export const CODE_UNSUPPORTED_EFFECT = "unsupported_effect";

const LABELS: Record<string, string> = {
  [LEGALITY_CATEGORY_POSSESSION]: "Possession",
  [LEGALITY_CATEGORY_LEGALITE]: "Légalité",
  [LEGALITY_CATEGORY_SCRIPT]: "Effet non géré",
};

/** Le libellé affichable d'une catégorie ; repli prudent sur « Légalité » pour une valeur inconnue. */
export function categoryLabel(category: string): string {
  return LABELS[category] ?? "Légalité";
}

type IssueLike = { code: string; card_id: string | null };

/**
 * Les `card_id` dont un effet n'est pas (encore) scripté — les constats `unsupported_effect`.
 * Sert au constructeur à marquer ces cartes « Effet non géré » et à proposer de les demander.
 */
export function scriptBlockedCardIds(issues: IssueLike[]): Set<string> {
  const out = new Set<string>();
  for (const issue of issues) {
    if (issue.code === CODE_UNSUPPORTED_EFFECT && issue.card_id) {
      out.add(issue.card_id);
    }
  }
  return out;
}
