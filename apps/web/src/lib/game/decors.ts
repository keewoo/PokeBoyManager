/**
 * **Décors d'arène** (lot `j-arene-decors`) — on joue quelque part, pas sur un fond gris.
 *
 * Module **pur** : il ne décrit que des couleurs et une règle de choix. Aucun rendu, aucun appel
 * réseau, aucun accès au DOM — ce qui le rend mesurable au ratio de contraste près
 * (`src/__tests__/contraste-decors.test.ts`) et vérifiable face au CSS
 * (`src/__tests__/decors-css-garde.test.ts`).
 *
 * ## Trois choix de conception, et pourquoi
 *
 * **1. Les décors sont peints en CSS, pas en images.** Quatre JPG de décor existaient déjà
 * (`apps/web/public/arenes/`, produits pour la maquette) : 1,24 Mo à eux quatre, ~300 Ko pièce.
 * Le critère d'acceptation du lot est que « le poids des décors entre dans le budget de la
 * partie » : six décors en images, c'est près de 2 Mo pour de la décoration, sur un jeu qu'on
 * ouvre au téléphone. En dégradés, c'est **zéro octet transféré** — et, accessoirement, la seule
 * forme dont on puisse *calculer* le contraste au lieu de l'estimer à l'œil.
 *
 * **2. Chaque décor n'a que quatre teintes porteuses, toutes sombres.** Le fond doit rester
 * derrière : la carte, les jetons et les énergies sont ce qu'on voit en premier (risque nommé du
 * lot). Quatre teintes suffisent à composer un tapis, une lueur périphérique et un vignettage —
 * et quatre teintes, ça se mesure exhaustivement contre les quinze repères du plateau.
 *
 * **3. La nuit est *dérivée*, jamais recopiée.** Le CSS l'obtient par
 * `color-mix(in srgb, <teinte> 72%, #000000)` ; ici, {@link teintesNuit} applique le même calcul.
 * Une seule source de vérité pour douze ambiances (six décors × jour/nuit) : impossible de
 * corriger une teinte de jour en oubliant sa nuit.
 */

import { melangerSrgb } from "@/lib/a11y/contraste";

/** Les quatre teintes porteuses d'une ambiance, du centre vers le bord. */
export type TeintesDecor = {
  /** Tapis de jeu : l'ovale mat du centre, là où les cartes se posent. */
  tapis: string;
  /** Fond général de l'arène, entre le tapis et les bords. */
  fond: string;
  /** Bords : le vignettage qui referme le cadre. La teinte la plus sombre. */
  bord: string;
  /** Lueur périphérique (les 15-20 % hauts du cadre). La teinte la plus claire. */
  lueur: string;
};

/** Un décor : son identité, son ambiance et les types d'énergie auxquels il répond. */
export type Decor = {
  /** Clé stable — portée par `data-decor` dans le DOM et stockée dans les réglages du compte. */
  cle: string;
  /** Nom montré au joueur. */
  libelle: string;
  /** Une phrase qui dit l'endroit, pour l'écran de choix et les lecteurs d'écran. */
  phrase: string;
  /** Teintes de jour. Celles de nuit en sont dérivées par {@link teintesNuit}. */
  teintes: TeintesDecor;
  /**
   * Types d'énergie dont ce décor est le thème automatique. Les onze types du jeu sont couverts
   * exactement une fois par l'ensemble des décors — un type sans décor retomberait sur le défaut
   * sans qu'on sache que c'est un oubli ; la garde de parité de `decors.test.ts` l'interdit.
   */
  types: string[];
};

/** Part de la teinte de jour conservée la nuit — doit refléter le `color-mix` de `globals.css`. */
export const NUIT_PART = 0.72;
/**
 * Teinte d'appoint de la nuit — même valeur que dans `globals.css`.
 *
 * Noir pur, et pas un bleu nuit : la nuit **baisse la lumière**, elle ne repeint pas le décor. Un
 * appoint teinté éclaircissait la composante bleue des teintes déjà très sombres (le bord de
 * « Faille obscure » est à `#020304`), c'est-à-dire qu'il rendait la nuit *plus claire* que le
 * jour sur ces teintes-là — l'inverse de ce qu'on annonce. Avec du noir, l'assombrissement est
 * strict, pour les six décors et leurs quatre teintes.
 */
export const NUIT_APPOINT = "#000000";

/**
 * Les six décors, du plus neutre au plus marqué.
 *
 * `arene` reprend **exactement** les deux teintes du fond livré par `j-plateau-layout`
 * (`#0E2A1E` → `#06120B`) : le décor par défaut ne change donc rien à ce que le joueur connaît,
 * et la maquette du jeu reste la référence.
 */
export const DECORS: Record<string, Decor> = {
  arene: {
    cle: "arene",
    libelle: "Arène municipale",
    phrase: "Le gymnase du quartier, tapis vert et projecteurs tamisés.",
    teintes: { tapis: "#0E2A1E", fond: "#06120B", bord: "#030A06", lueur: "#15402C" },
    types: ["grass", "colorless"],
  },
  caldeira: {
    cle: "caldeira",
    libelle: "Caldeira",
    phrase: "Un cratère endormi, la roche encore tiède sous les braises.",
    teintes: { tapis: "#2A1008", fond: "#150603", bord: "#0A0301", lueur: "#4A1608" },
    types: ["fire", "fighting"],
  },
  lagon: {
    cle: "lagon",
    libelle: "Lagon",
    phrase: "Une plage à marée basse, l'eau noire et calme au loin.",
    teintes: { tapis: "#06223A", fond: "#03101D", bord: "#010710", lueur: "#0B3A5E" },
    types: ["water"],
  },
  orage: {
    cle: "orage",
    libelle: "Plateau d'orage",
    phrase: "Un plateau battu par le vent, l'éclair encore à l'horizon.",
    teintes: { tapis: "#1B1C2E", fond: "#0C0D18", bord: "#05060C", lueur: "#33355A" },
    types: ["lightning", "metal"],
  },
  temple: {
    cle: "temple",
    libelle: "Temple oublié",
    phrase: "Des dalles gravées sous la mousse, et quelque chose qui veille.",
    teintes: { tapis: "#1E1030", fond: "#0F0819", bord: "#07040D", lueur: "#38175A" },
    types: ["psychic", "fairy", "dragon"],
  },
  faille: {
    cle: "faille",
    libelle: "Faille obscure",
    phrase: "Le fond d'une crevasse, juste assez de lumière pour jouer.",
    teintes: { tapis: "#101418", fond: "#07090C", bord: "#020304", lueur: "#1C2630" },
    types: ["darkness"],
  },
};

/** Décor servi quand rien n'est choisi et que rien ne se déduit : celui du plateau d'origine. */
export const DECOR_DEFAUT = "arene";

/** Valeur de réglage qui veut dire « laisse le jeu choisir d'après mon deck ». */
export const DECOR_AUTO = "auto";

/** Les clés réglables, dans l'ordre d'affichage de l'écran de choix. */
export const DECORS_REGLABLES: string[] = Object.keys(DECORS);

/** Les deux moments de la journée. Le décor ne change pas, son éclairage change. */
export type MomentJour = "jour" | "nuit";

/** Heure (locale) à partir de laquelle on passe en ambiance de nuit, et celle du retour au jour. */
export const NUIT_DEBUT_H = 20;
export const NUIT_FIN_H = 7;

/**
 * Teintes de nuit d'un décor : chaque teinte de jour assombrie vers le noir.
 *
 * Miroir exact du `color-mix(in srgb, … 72%, #000000)` de `globals.css` — c'est ce qui permet au
 * test de contraste de mesurer les douze ambiances sans qu'aucune valeur de nuit soit écrite à la
 * main (donc sans qu'aucune puisse être oubliée).
 */
export function teintesNuit(teintes: TeintesDecor): TeintesDecor {
  const tirer = (c: string) => melangerSrgb(c, NUIT_APPOINT, NUIT_PART);
  return {
    tapis: tirer(teintes.tapis),
    fond: tirer(teintes.fond),
    bord: tirer(teintes.bord),
    lueur: tirer(teintes.lueur),
  };
}

/** Teintes réellement affichées pour un décor à un moment donné. */
export function teintesDecor(cle: string, moment: MomentJour): TeintesDecor {
  const decor = DECORS[cle] ?? DECORS[DECOR_DEFAUT]!;
  return moment === "nuit" ? teintesNuit(decor.teintes) : decor.teintes;
}

/** Le moment de la journée pour une heure locale donnée (0-23). */
export function momentPourHeure(heure: number): MomentJour {
  return heure >= NUIT_DEBUT_H || heure < NUIT_FIN_H ? "nuit" : "jour";
}

/**
 * Le décor dont un type d'énergie est le thème. `null` pour un type inconnu — l'appelant retombe
 * alors sur le défaut, et le sait (D9 : on ne devine pas un décor pour un type qu'on ne connaît
 * pas, on le dit).
 */
export function decorPourType(type: string | null | undefined): string | null {
  if (!type) return null;
  const code = type.toLowerCase();
  for (const decor of Object.values(DECORS)) {
    if (decor.types.includes(code)) return decor.cle;
  }
  return null;
}

/**
 * Type dominant d'un ensemble de cartes : le plus fréquent, et à égalité le premier par ordre
 * alphabétique du code — jamais l'ordre d'arrivée, qui dépendrait de la pioche et ferait changer
 * le décor d'une partie à l'autre avec le même deck.
 */
export function typeDominant(types: readonly (string | null | undefined)[]): string | null {
  const comptes = new Map<string, number>();
  for (const t of types) {
    if (!t) continue;
    const code = t.toLowerCase();
    comptes.set(code, (comptes.get(code) ?? 0) + 1);
  }
  if (comptes.size === 0) return null;
  return [...comptes.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]![0];
}

/**
 * Le décor à afficher : **le choix du joueur d'abord**, le thème du deck ensuite, le défaut en
 * dernier.
 *
 * Cet ordre n'est pas négociable : un joueur qui a choisi « Lagon » le garde même en jouant un
 * deck Feu. Le thème automatique n'est là que pour celui qui n'a rien choisi — il ne corrige
 * jamais une décision prise.
 *
 * @param choix   réglage du compte : une clé de {@link DECORS}, `"auto"`, ou rien du tout.
 * @param types   les types d'énergie connus du camp du joueur (pour le thème automatique).
 */
export function decorEffectif(
  choix: string | null | undefined,
  types: readonly (string | null | undefined)[] = [],
): string {
  if (choix && choix !== DECOR_AUTO && DECORS[choix]) return choix;
  return decorPourType(typeDominant(types)) ?? DECOR_DEFAUT;
}

/** Libellé d'un décor, pour un écran ou un lecteur d'écran. Nomme l'inconnu plutôt que de le taire. */
export function libelleDecor(cle: string): string {
  return DECORS[cle]?.libelle ?? `décor inconnu (${cle})`;
}
