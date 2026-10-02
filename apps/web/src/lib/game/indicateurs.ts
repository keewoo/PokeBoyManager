/**
 * Indicateurs visuels du plateau (lot `j-plateau-etat-visuel`) — données **pures** d'affichage.
 *
 * Tout ce que l'écran dessine se lit sur l'état projeté par le serveur (PV restants, types, états) :
 * ce module ne fait que traduire ces données en repères visuels. Deux règles d'accessibilité le
 * gouvernent :
 *
 * - **jamais la couleur seule** : chaque type d'énergie porte une **abréviation** et chaque état
 *   une **icône**, pour rester lisibles en cas de daltonisme (critère d'acceptation du lot) ;
 * - **on n'invente pas** : un type inconnu du serveur (`null`) retombe sur un repère **neutre**
 *   explicite, jamais une couleur devinée (D9).
 *
 * Pur (aucun React, aucune E/S) : testable sans navigateur.
 */

/** Le style d'affichage d'un type d'élément : couleur de fond, abréviation (signe non coloré), nom. */
export type StyleElement = {
  /** Code moteur (`pbm_api.catalog.element_type`), ou `"inconnu"` pour le repère neutre. */
  code: string;
  /** Abréviation lisible — le **signe** qui double la couleur (daltonisme). */
  abbr: string;
  /** Nom complet, pour l'étiquette d'accessibilité. */
  label: string;
  /** Couleur de fond de la pastille. */
  couleur: string;
  /** Couleur du texte de l'abréviation, pour le contraste. */
  texte: string;
};

const NEUTRE: StyleElement = {
  code: "inconnu",
  abbr: "?",
  label: "Type inconnu",
  couleur: "#555B66",
  texte: "#FFFFFF",
};

/** Les onze types du jeu (codes de `pbm_api.catalog.element_type`), chacun avec son signe propre. */
export const ELEMENTS: Record<string, StyleElement> = {
  grass: { code: "grass", abbr: "Pl", label: "Plante", couleur: "#3FA34D", texte: "#06220E" },
  fire: { code: "fire", abbr: "Fe", label: "Feu", couleur: "#E2503B", texte: "#2A0A06" },
  water: { code: "water", abbr: "Ea", label: "Eau", couleur: "#3B82E2", texte: "#04142E" },
  lightning: { code: "lightning", abbr: "Él", label: "Électrique", couleur: "#E2C43B", texte: "#2A2206" },
  psychic: { code: "psychic", abbr: "Psy", label: "Psy", couleur: "#9B59B6", texte: "#1E0A26" },
  fighting: { code: "fighting", abbr: "Co", label: "Combat", couleur: "#B5651D", texte: "#2A1606" },
  darkness: { code: "darkness", abbr: "Ob", label: "Obscurité", couleur: "#2C3E50", texte: "#E6EAF0" },
  metal: { code: "metal", abbr: "Mé", label: "Métal", couleur: "#8694A3", texte: "#0E1620" },
  dragon: { code: "dragon", abbr: "Dr", label: "Dragon", couleur: "#C9A227", texte: "#241B04" },
  fairy: { code: "fairy", abbr: "Fé", label: "Fée", couleur: "#E27BA5", texte: "#2A0A18" },
  colorless: { code: "colorless", abbr: "In", label: "Incolore", couleur: "#C9C2B8", texte: "#1E1B16" },
};

/**
 * Le style d'un type d'élément, repère **neutre** si le code est absent ou inconnu — jamais une
 * couleur inventée (D9) : un type qu'on ne connaît pas se montre comme tel.
 */
export function styleElement(code?: string | null): StyleElement {
  if (!code) return NEUTRE;
  return ELEMENTS[code] ?? NEUTRE;
}

/** Le repère visuel d'un état spécial (R-11.1) : une icône (signe non coloré) et son nom. */
export type VisuelEtat = { cle: string; icone: string; label: string };

/** Les cinq états spéciaux (R-11.1), chacun montré par une icône **en plus** de l'orientation. */
export const ETATS: Record<string, VisuelEtat> = {
  endormi: { cle: "endormi", icone: "💤", label: "Endormi" },
  brule: { cle: "brule", icone: "🔥", label: "Brûlé" },
  confus: { cle: "confus", icone: "💫", label: "Confus" },
  paralyse: { cle: "paralyse", icone: "⚡", label: "Paralysé" },
  empoisonne: { cle: "empoisonne", icone: "☠️", label: "Empoisonné" },
};

/**
 * Le repère d'un état spécial : son icône et son nom. Un état inconnu du corpus est montré par un
 * point d'interrogation **nommé** (jamais masqué en silence — un repli muet cacherait un bug).
 */
export function visuelEtat(cle: string): VisuelEtat {
  return ETATS[cle] ?? { cle, icone: "❔", label: cle };
}

/** Le nombre de **compteurs de dégâts** (1 compteur = 10 dégâts, R-10.4) pour un total de dégâts. */
export function nombreCompteurs(degats: number): number {
  return Math.ceil(Math.max(0, degats) / 10);
}


/**
 * L'identité du Pokémon qui **vient d'agir**, lue sur les événements d'un coup — ou `null`.
 *
 * On retient le **dernier** événement qui désigne un Pokémon par l'instance de sa carte de base
 * (`donnees.pokemon` ou `donnees.base`) : pose, évolution, attachement d'énergie, K.O., promotion.
 * Un coup qui ne désigne aucun Pokémon (ex. piocher) ne met rien en évidence — on n'invente jamais
 * un agisseur (le halo ne ment pas). Tolérant à la forme des événements (temps réel, resync).
 */
export function agisseurDepuisEvenements(evenements: unknown[]): string | null {
  for (let i = evenements.length - 1; i >= 0; i -= 1) {
    const evt = evenements[i] as { donnees?: Record<string, unknown> } | null;
    const donnees = evt?.donnees;
    if (!donnees) continue;
    const identite = donnees.pokemon ?? donnees.base;
    if (typeof identite === "string" && identite) return identite;
  }
  return null;
}
