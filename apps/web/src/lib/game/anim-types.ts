/**
 * Les effets d'attaque **par type d'énergie** (lot `j-anim-attaques-typees`) — module **pur** :
 * ni React, ni DOM, ni E/S.
 *
 * Une attaque Feu brûle la carte d'en face, l'éclair fait trembler le plateau, l'onde Psy déforme
 * l'image. C'est la demande explicite de JF, et c'est ce qui fait qu'un enfant a envie de rejouer :
 * l'attaque doit se **voir**, pas s'afficher en chiffres.
 *
 * ## Un système, pas dix animations
 *
 * Le risque nommé par le lot est précis : « dix animations écrites séparément : impossible à
 * maintenir, et l'une d'elles finira par cacher un compteur de dégâts au moment décisif ». La
 * parade est structurelle — il n'y a ici **aucune animation par type**. Il y a :
 *
 * - **six couches** ({@link Couche}) et **quatre gestes de carte** ({@link GesteCarte}), chacun avec
 *   *une* image-clé CSS, écrite une seule fois (`globals.css`, bloc « Effets typés ») ;
 * - **une table** ({@link SPECS}) qui dit, pour chacun des onze types, quelles couches composer,
 *   combien de particules et quel geste — c'est de la **donnée**, pas du code ;
 * - **une fonction** ({@link effetAttaque}) qui module le tout par une **intensité** calculée sur le
 *   résultat réel de l'attaque.
 *
 * Ajouter un type, c'est donc ajouter une ligne de table. Et comme tous les types partagent les
 * mêmes couches, une couche qui masquerait un compteur les masquerait **tous les onze** — donc ça
 * se verrait au premier essai, au lieu d'attendre la carte Dragon du dixième tour.
 *
 * ## Pourquoi du CSS et pas un canvas
 *
 * Le lot parle de « shaders/canvas légers ». On a tranché pour des couches **DOM animées en CSS**,
 * et c'est le plancher d'images par seconde qui décide : le socle (`animations.ts`) tient ses 30
 * images/s sur un téléphone d'entrée de gamme **parce que** rien ne passe par le fil principal —
 * seules `transform` et `opacity` sont animées, le navigateur les compose sur le processeur
 * graphique, et React ne rend qu'une fois par animation. Un canvas rendrait à la main, chaque
 * image, sur le fil principal : il reprendrait exactement ce qu'on a économisé. La garde
 * `src/__tests__/anim-css-garde.test.ts` s'applique telle quelle à ces images-clés, qui sont donc
 * nommées `pbm-anim-fx-*` — **pas** sous un autre préfixe qui les ferait échapper au contrôle.
 *
 * ## Ce que l'effet ne fait jamais
 *
 * - il ne **masque** pas l'état du plateau plus d'une seconde ({@link TOTAL_MAX_MS}, borné ici et
 *   vérifié par test pour les onze types et toutes les durées du socle) ;
 * - il ne **couvre** pas les compteurs de dégâts : la couche est rendue **avant** les indicateurs
 *   dans la carte, donc dessous (gardé par `board-card.test.tsx`) ;
 * - il n'**invente** pas un type : un type absent de {@link SPECS} ne donne **aucun** effet typé, et
 *   le socle garde son effet neutre (D9 — on n'approxime pas ce qu'on ne connaît pas).
 */

import { styleElement } from "@/lib/game/indicateurs";

/**
 * Les six **couches** dont se composent tous les effets. Chacune a une image-clé unique dans
 * `globals.css`, et n'animera jamais que `transform` et `opacity`.
 *
 * - `nappe` — un voile teinté qui monte puis retombe sur toute la carte (flammes qui lèchent,
 *   ombre qui engloutit, carte trempée) ;
 * - `balayage` — une bande qui traverse la carte (la vague d'Eau, l'éclat du Métal, le souffle
 *   du Dragon) ;
 * - `onde` — des anneaux concentriques qui s'élargissent (l'onde Psy, l'impact de Combat) ;
 * - `particules` — N éclats qui partent du centre (braises, pétales, étincelles, étoiles) ;
 * - `flash` — un blanchiment très bref de la carte (l'arc Électrique) ;
 * - `etreinte` — deux pans qui se referment depuis les bords (les lianes de Plante).
 */
export type Couche = "nappe" | "balayage" | "onde" | "particules" | "flash" | "etreinte";

/**
 * Ce que l'effet fait faire à la **carte elle-même** (et non à une couche posée dessus).
 *
 * Toujours un `transform` : il ne change aucune boîte de disposition, donc il ne peut pas provoquer
 * de défilement — le plateau n'en tolère aucun (lot `j-plateau-layout`). Même raisonnement que
 * l'orientation des cartes endormies/confuses, déjà en place.
 */
export type GesteCarte = "aucun" | "distorsion" | "recul" | "tremblement";

/** Le palier d'intensité — ce que le CSS lit pour doser l'amplitude. */
export type Palier = "echec" | "faible" | "moyen" | "fort";

/**
 * La composition d'un type : quelles couches, combien de particules, quel geste.
 *
 * C'est de la **donnée**. Rien ici ne décrit *comment* ça bouge (c'est le CSS) ni *combien fort*
 * (c'est l'intensité) : seulement **de quoi** l'effet est fait.
 */
export type SpecType = {
  /** Code moteur du type (`pbm_api.catalog.element_type`), tel que le serveur l'envoie. */
  code: string;
  /** Clé courte sans accent, utilisée en attribut CSS (`data-fx`) et en jeton de teinte. */
  cle: string;
  /** Nom français du type, pour les phrases et les étiquettes d'accessibilité. */
  libelle: string;
  /** Le geste de l'attaque, en français d'enfant — c'est ce que la version réduite raconte. */
  geste: string;
  /** Les couches à composer, dans l'ordre de rendu (la dernière est au-dessus). */
  couches: Couche[];
  /** Nombre de particules à intensité pleine (`0` = cet effet n'en a pas). */
  particules: number;
  /** Ce que la carte visée fait d'elle-même. */
  gesteCarte: GesteCarte;
  /** `true` si le **plateau entier** tremble (l'éclair, l'impact de Combat). */
  secousse: boolean;
  /** `true` si une **trace** subsiste brièvement après l'effet (bords noircis, carte trempée). */
  trace: boolean;
};

/**
 * Les onze types, et ce dont leur effet est fait.
 *
 * Les dix types exigés par le lot y sont, plus **Incolore** — qui n'est pas un bonus : un Pokémon
 * de type `colorless` attaque comme les autres, et le laisser sans effet aurait fabriqué un
 * onzième cas muet que personne n'aurait cherché.
 *
 * ⚠️ Toute ligne ajoutée ici doit avoir sa teinte dans `globals.css` (`--pbm-fx-<cle>-*`) : le test
 * `src/__tests__/anim-types-css-garde.test.ts` le vérifie et nomme la ligne fautive. Un type sans
 * teinte s'afficherait transparent — un effet invisible, donc un effet qui mentirait.
 */
export const SPECS: Record<string, SpecType> = {
  fire: {
    code: "fire",
    cle: "feu",
    libelle: "Feu",
    geste: "les flammes lèchent la carte et ses bords noircissent",
    couches: ["nappe", "particules"],
    particules: 8,
    gesteCarte: "aucun",
    secousse: false,
    trace: true,
  },
  water: {
    code: "water",
    cle: "eau",
    libelle: "Eau",
    geste: "une vague traverse la carte, qui reste trempée",
    couches: ["balayage", "nappe"],
    particules: 6,
    gesteCarte: "aucun",
    secousse: false,
    trace: true,
  },
  grass: {
    code: "grass",
    cle: "plante",
    libelle: "Plante",
    geste: "des lianes enserrent la carte et des pétales retombent",
    couches: ["etreinte", "particules"],
    particules: 6,
    gesteCarte: "aucun",
    secousse: false,
    trace: false,
  },
  lightning: {
    code: "lightning",
    cle: "electrique",
    libelle: "Électrique",
    geste: "un arc claque, tout blanchit et le plateau tremble",
    couches: ["flash", "balayage", "particules"],
    particules: 4,
    gesteCarte: "tremblement",
    secousse: true,
    trace: false,
  },
  psychic: {
    code: "psychic",
    cle: "psy",
    libelle: "Psy",
    geste: "une onde traverse la carte et déforme son image",
    couches: ["onde", "nappe"],
    particules: 0,
    gesteCarte: "distorsion",
    secousse: false,
    trace: false,
  },
  fighting: {
    code: "fighting",
    cle: "combat",
    libelle: "Combat",
    geste: "un impact fissure la carte et la fait reculer",
    couches: ["onde", "nappe"],
    particules: 0,
    gesteCarte: "recul",
    secousse: true,
    trace: true,
  },
  darkness: {
    code: "darkness",
    cle: "obscurite",
    libelle: "Obscurité",
    geste: "une ombre engloutit la carte",
    couches: ["nappe", "etreinte"],
    particules: 0,
    gesteCarte: "aucun",
    secousse: false,
    trace: true,
  },
  metal: {
    code: "metal",
    cle: "metal",
    libelle: "Métal",
    geste: "un éclat raye la carte et des étincelles jaillissent",
    couches: ["balayage", "flash", "particules"],
    particules: 7,
    gesteCarte: "aucun",
    secousse: false,
    trace: false,
  },
  dragon: {
    code: "dragon",
    cle: "dragon",
    libelle: "Dragon",
    geste: "un souffle balaie la carte de part en part",
    couches: ["balayage", "nappe", "particules"],
    particules: 5,
    gesteCarte: "aucun",
    secousse: true,
    trace: false,
  },
  fairy: {
    code: "fairy",
    cle: "fee",
    libelle: "Fée",
    geste: "une pluie d'étoiles tombe sur la carte",
    couches: ["particules", "onde"],
    particules: 9,
    gesteCarte: "aucun",
    secousse: false,
    trace: false,
  },
  colorless: {
    code: "colorless",
    cle: "incolore",
    libelle: "Incolore",
    geste: "un choc net secoue la carte",
    couches: ["onde"],
    particules: 0,
    gesteCarte: "aucun",
    secousse: false,
    trace: false,
  },
};

/**
 * Les dégâts au-delà desquels l'effet ne grossit plus.
 *
 * 200 parce que c'est l'ordre de grandeur d'une **grosse** attaque du jeu (les plus fortes montent
 * vers 300, mais au-delà de 200 l'écran ne saurait plus montrer la différence). Sans ce plafond,
 * une attaque à 300 écraserait toutes les autres et l'intensité ne dirait plus rien.
 */
export const DEGATS_REFERENCE = 200;

/** Ce que la **faiblesse** ajoute à l'intensité, en plus du doublement des dégâts (R-10.2). */
export const FACTEUR_FAIBLESSE = 1.3;

/** Ce que la **résistance** retire à l'intensité, en plus de la réduction des dégâts (R-10.3). */
export const FACTEUR_RESISTANCE = 0.65;

/** L'intensité d'une attaque **ratée** : l'effet part, puis retombe sans toucher. */
export const INTENSITE_ECHEC = 0.15;

/** Au-dessus de cette intensité, le palier est `moyen`. */
export const SEUIL_MOYEN = 0.34;

/** Au-dessus de cette intensité, le palier est `fort`. */
export const SEUIL_FORT = 0.67;

/**
 * Le temps **total** qu'un effet peut occuper la carte, animation et trace comprises.
 *
 * C'est le critère d'acceptation n°2 du lot (« l'effet ne masque jamais l'état du plateau plus
 * d'une seconde »), tenu **par construction** : {@link effetAttaque} rabote la trace pour que la
 * somme ne dépasse jamais cette borne, quelle que soit la durée que le socle lui donne.
 */
export const TOTAL_MAX_MS = 1000;

/** Durée visée d'une trace résiduelle (bords noircis, carte trempée), avant rabotage. */
export const TRACE_MS = 420;

/** Plafond de particules réellement rendues — au-delà, c'est du bruit, et ça coûte des images. */
export const PARTICULES_MAX = 10;

/**
 * Combien de temps la **version réduite** reste à l'écran.
 *
 * Elle ne bouge pas : il faut donc qu'elle reste assez longtemps pour être lue, là où une animation
 * se comprend en la voyant passer. Une seconde, soit la borne du critère — pas plus.
 */
export const DUREE_REDUITE = TOTAL_MAX_MS;

/**
 * Ce que le serveur dit d'une attaque, et dont l'effet se déduit entièrement.
 *
 * Tout vient des événements : `type` de `attaque_declaree`, `degats` / `faiblesse` / `resistance`
 * de `degats`, `echec` d'un pile ou face perdu. Rien n'est lu dans la vue courante — elle a pu
 * bouger depuis.
 */
export type Typage = {
  /** Code moteur du type de l'attaque, `""` si le serveur ne le connaît pas. */
  type: string;
  /** Dégâts réellement infligés (après faiblesse, résistance et plancher). */
  degats: number;
  /** La faiblesse a joué (R-10.2) : l'effet est **renforcé**. */
  faiblesse: boolean;
  /** La résistance a joué (R-10.3) : l'effet est **atténué**. */
  resistance: boolean;
  /** L'attaque a raté (pile ou face perdu, Confusion sur pile) : effet particulier. */
  echec: boolean;
};

/** Un typage vide — aucun type connu, donc aucun effet typé. */
export const TYPAGE_VIDE: Typage = {
  type: "",
  degats: 0,
  faiblesse: false,
  resistance: false,
  echec: false,
};

/** Tout ce qu'il faut pour dessiner un effet typé — auto-porté, comme une {@link Animation}. */
export type EffetAttaque = {
  /** Code moteur du type. */
  type: string;
  /** Clé CSS du type (`feu`, `eau`…), posée en `data-fx`. */
  cle: string;
  /** Nom français du type. */
  libelle: string;
  /** `false` = **version réduite** : rien ne bouge, l'effet se lit. */
  anime: boolean;
  /** Les couches à rendre, dans l'ordre (vide en version réduite). */
  couches: Couche[];
  /** Nombre de particules à rendre réellement (0 en version réduite). */
  particules: number;
  /** Le geste de la carte visée (`aucun` en version réduite). */
  gesteCarte: GesteCarte;
  /** `true` si le plateau tremble (jamais en version réduite). */
  secousse: boolean;
  /** Le palier, lu par le CSS pour doser l'amplitude. */
  palier: Palier;
  /** L'intensité continue, au centième — pour les amplitudes fines. */
  intensite: number;
  /** La faiblesse a joué : l'effet porte un marqueur en plus d'être plus fort. */
  renforce: boolean;
  /** La résistance a joué : l'effet est amorti, et le dit. */
  attenue: boolean;
  /** L'attaque a raté. */
  echec: boolean;
  /** Durée de la phase animée, en millisecondes (0 en version réduite). */
  duree: number;
  /** Durée de la trace résiduelle, en millisecondes (0 si ce type n'en laisse pas). */
  trace: number;
  /** `duree + trace` — **toujours** ≤ {@link TOTAL_MAX_MS}. */
  dureeTotale: number;
  /** La phrase complète : version réduite affichée, et étiquette d'accessibilité. */
  phrase: string;
  /** Le texte court du badge réduit (abréviation du type, dégâts, marqueur). */
  badge: string;
};

/** Borne un nombre dans `[0, 1]`. */
function borner01(v: number): number {
  if (!Number.isFinite(v)) return 0;
  return Math.min(1, Math.max(0, v));
}

/**
 * L'intensité d'un effet, dans `[0, 1]`, depuis le **résultat réel** de l'attaque.
 *
 * Les dégâts donnent le socle. La faiblesse et la résistance s'y ajoutent **en plus** du doublement
 * / de la réduction qu'elles ont déjà produit sur les dégâts : sans ce supplément, une attaque de
 * 60 doublée par faiblesse serait visuellement identique à une attaque de 120 sans faiblesse, et
 * le joueur ne verrait pas *pourquoi* ça a fait mal. Un échec court-circuite tout : l'effet part et
 * retombe.
 */
export function intensiteDe(typage: Typage): number {
  if (typage.echec) return INTENSITE_ECHEC;
  let i = borner01(Math.max(0, typage.degats) / DEGATS_REFERENCE);
  if (typage.faiblesse) i = borner01(i * FACTEUR_FAIBLESSE);
  if (typage.resistance) i = borner01(i * FACTEUR_RESISTANCE);
  return Math.round(i * 100) / 100;
}

/** Le palier correspondant à une intensité (un échec a son palier à lui). */
export function palierDe(intensite: number, echec: boolean): Palier {
  if (echec) return "echec";
  if (intensite >= SEUIL_FORT) return "fort";
  if (intensite >= SEUIL_MOYEN) return "moyen";
  return "faible";
}

/** Le mot qui dit la force d'un effet, pour la version réduite et les lecteurs d'écran. */
const MOTS_PALIER: Record<Palier, string> = {
  echec: "ratée",
  faible: "légère",
  moyen: "nette",
  fort: "violente",
};

/**
 * La phrase que dit un effet — c'est **toute** l'information de la version réduite.
 *
 * Elle nomme le type, ce qui s'est passé et pourquoi c'était fort ou faible. Un enfant doit pouvoir
 * la lire sans connaître les règles : « Feu — attaque violente, 120 dégâts : c'est une faiblesse. »
 */
export function phraseEffet(spec: SpecType, typage: Typage, palier: Palier): string {
  if (typage.echec) {
    return `${spec.libelle} — attaque ratée : rien ne touche la carte.`;
  }
  const bouts = [`${spec.libelle} — attaque ${MOTS_PALIER[palier]}, ${typage.degats} dégâts`];
  if (typage.faiblesse) bouts.push("c'est une faiblesse, ça fait double mal");
  if (typage.resistance) bouts.push("la résistance a amorti le coup");
  bouts.push(spec.geste);
  return `${bouts.join(" : ")}.`;
}

/** Le texte court du badge réduit : l'abréviation du type (jamais la couleur seule) et le chiffre. */
export function badgeEffet(spec: SpecType, typage: Typage): string {
  const abbr = styleElement(spec.code).abbr;
  if (typage.echec) return `${abbr} ratée`;
  const marque = typage.faiblesse ? " ×2" : typage.resistance ? " −" : "";
  return `${abbr} ${typage.degats}${marque}`;
}

/** Ce qu'il faut savoir en plus du typage pour dimensionner l'effet. */
export type OptionsEffet = {
  /** La durée que le socle accorde à cette animation (`dureeEffective`), en millisecondes. */
  duree: number;
  /** `true` → **version réduite** : rien ne bouge (réglage système ou réglage du jeu). */
  reduit?: boolean;
};

/**
 * L'effet typé d'une attaque, ou `null` quand il n'y en a pas à jouer.
 *
 * Renvoie `null` dans deux cas, et c'est voulu : **type inconnu** (le socle garde son effet neutre
 * — D9) et **rien à montrer** (aucun dégât et pas d'échec : une attaque purement à effet se lit
 * dans le journal, pas en fanfare).
 *
 * La **version réduite** (`reduit: true`) n'est pas « la même chose en plus court » : c'est un
 * objet sans aucune couche, sans geste, sans secousse, dont toute la charge d'information est dans
 * {@link EffetAttaque.phrase} et {@link EffetAttaque.badge}. Elle existe pour les onze types, et un
 * test le vérifie type par type — « animations réduites » ne doit jamais vouloir dire « tu ne sauras
 * pas ce qui vient de se passer ».
 */
export function effetAttaque(typage: Typage, options: OptionsEffet): EffetAttaque | null {
  const spec = SPECS[typage.type];
  if (!spec) return null;
  if (typage.degats <= 0 && !typage.echec) return null;

  const intensite = intensiteDe(typage);
  const palier = palierDe(intensite, typage.echec);
  const phrase = phraseEffet(spec, typage, palier);
  const badge = badgeEffet(spec, typage);
  const commun = {
    type: spec.code,
    cle: spec.cle,
    libelle: spec.libelle,
    palier,
    intensite,
    renforce: typage.faiblesse,
    attenue: typage.resistance,
    echec: typage.echec,
    phrase,
    badge,
  };

  if (options.reduit) {
    return {
      ...commun,
      anime: false,
      couches: [],
      particules: 0,
      gesteCarte: "aucun",
      secousse: false,
      duree: 0,
      trace: 0,
      dureeTotale: DUREE_REDUITE,
    };
  }

  // La durée vient du socle : on ne la rallonge jamais, on se contente d'y tenir. La trace est
  // ce qui reste de marge sous la borne d'une seconde — c'est elle qui se fait raboter, jamais
  // l'animation, parce qu'une animation tronquée se voit et qu'une trace écourtée non.
  const duree = Math.max(0, Math.min(Math.round(options.duree), TOTAL_MAX_MS));
  const trace = spec.trace ? Math.max(0, Math.min(TRACE_MS, TOTAL_MAX_MS - duree)) : 0;
  // Un échec ne pose aucune particule : l'effet doit se lire comme un ratage, pas comme un coup
  // faible. Sinon on ne distingue pas « ça a raté » de « ça a fait 10 ».
  const particules =
    spec.particules > 0 && !typage.echec
      ? Math.min(PARTICULES_MAX, Math.max(1, Math.round(spec.particules * intensite)))
      : 0;

  return {
    ...commun,
    anime: true,
    couches: spec.couches,
    particules,
    // Un échec ne secoue rien et ne déforme rien : le coup n'a pas porté.
    gesteCarte: typage.echec ? "aucun" : spec.gesteCarte,
    secousse: typage.echec ? false : spec.secousse,
    duree,
    trace,
    dureeTotale: duree + trace,
  };
}

/** Le « coût visuel » d'un type à intensité pleine : couches, particules, gestes. */
export function coutVisuel(spec: SpecType): number {
  return (
    spec.couches.length +
    spec.particules +
    (spec.gesteCarte === "aucun" ? 0 : 1) +
    (spec.secousse ? 1 : 0)
  );
}

/**
 * Le type dont l'effet est le **plus lourd** à rendre.
 *
 * Il est calculé, pas choisi : l'e2e de fluidité (`e2e/anim-attaques-typees.spec.ts`) mesure le
 * plancher d'images par seconde **sur celui-là** — critère d'acceptation n°4. Le nommer en dur dans
 * l'e2e aurait voulu dire mesurer le mauvais type le jour où la table change, en continuant
 * d'afficher un verdict vert.
 */
export const TYPE_LE_PLUS_LOURD: string = Object.values(SPECS).reduce(
  (pire, spec) => (coutVisuel(spec) > coutVisuel(SPECS[pire] as SpecType) ? spec.code : pire),
  Object.keys(SPECS)[0] as string,
);
