// Visuel de remplacement des cartes sans image officielle (lot `pbm-carte-remplacement`).
//
// 3 827 cartes du catalogue n'ont aucune image officielle et aucun import ne les rapportera :
// les sources publiques ne les ont pas. Plutôt qu'un cadre vide, la carte est COMPOSÉE à partir
// de ses vraies données, et seule la zone d'illustration reçoit un fond générique, choisi de
// façon déterministe d'après l'identifiant — la même carte garde donc toujours le même visuel.

/** Les onze types du jeu, chacun avec ses neuf fonds `public/fonds/<code>-01.webp`…`-09.webp`. */
export type ElementCode =
  | "grass"
  | "fire"
  | "water"
  | "lightning"
  | "psychic"
  | "fighting"
  | "darkness"
  | "metal"
  | "dragon"
  | "fairy"
  | "colorless";

const ELEMENT_CODES: ReadonlySet<string> = new Set<ElementCode>([
  "grass",
  "fire",
  "water",
  "lightning",
  "psychic",
  "fighting",
  "darkness",
  "metal",
  "dragon",
  "fairy",
  "colorless",
]);

/** Nombre de fonds par type (`<code>-01.webp` … `-09.webp`). */
export const FONDS_PAR_TYPE = 9;

/** Libellé français du type, pour l'afficher sur la carte composée. */
export const ELEMENT_LABELS: Record<ElementCode, string> = {
  grass: "Plante",
  fire: "Feu",
  water: "Eau",
  lightning: "Électrique",
  psychic: "Psy",
  fighting: "Combat",
  darkness: "Obscurité",
  metal: "Métal",
  dragon: "Dragon",
  fairy: "Fée",
  colorless: "Incolore",
};

/**
 * Empreinte entière stable d'une chaîne (FNV-1a 32 bits, non signée). Déterministe et sans
 * dépendance : la même carte donne toujours le même fond, sur tous les navigateurs et à chaque
 * rendu. Ce n'est PAS une empreinte de sécurité — juste un choix reproductible.
 */
export function empreinte(value: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    // Multiplication FNV en arithmétique 32 bits (Math.imul évite le débordement des flottants).
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

/** Ramène un type élémentaire (code du jeu ou `null`) à un code de fond utilisable. */
export function codeFond(elementType: string | null | undefined): ElementCode {
  if (elementType && ELEMENT_CODES.has(elementType)) {
    return elementType as ElementCode;
  }
  // Une carte sans type (Dresseur, Énergie, type inconnu) prend "colorless".
  return "colorless";
}

/**
 * Chemin du fond générique pour une carte, choisi de façon déterministe :
 * `empreinte(card_id) % 9` sur le type de la carte. Numérotation `01`…`09`.
 */
export function fondPour(cardId: string, elementType: string | null | undefined): string {
  const code = codeFond(elementType);
  const index = (empreinte(cardId) % FONDS_PAR_TYPE) + 1;
  const numero = String(index).padStart(2, "0");
  return `/fonds/${code}-${numero}.webp`;
}

/** Couleur de teinte du type, déclarée en jeton dans `globals.css` (jamais un texte). */
export function couleurType(elementType: string | null | undefined): string {
  return `var(--type-${codeFond(elementType)})`;
}
