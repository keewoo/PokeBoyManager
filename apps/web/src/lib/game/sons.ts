/**
 * Les sons du jeu (lot `j-son`) — **purs** : ni React, ni DOM, ni `AudioContext`, ni fichier.
 *
 * ## Pourquoi il n'y a aucun fichier audio dans ce dépôt
 *
 * Le risque nommé par le lot est précis : *« des sons pris au hasard sur Internet, c'est un risque
 * de droits pour quelques kilo-octets d'effet »*. On ne l'a donc pas encadré, on l'a **supprimé** :
 * chaque son de ce jeu est **décrit** ici, en données, et **fabriqué** par le navigateur
 * (`lib/sons-provider.tsx`). Il n'y a rien à télécharger, rien à créditer, rien à vérifier plus
 * tard — l'origine de chaque son est **ce fichier**, et le dépôt la porte en entier.
 *
 * Trois conséquences qui ne sont pas des effets secondaires mais des raisons de faire ainsi :
 *
 * - **la question des droits ne se pose pas** : une recette d'oscillateurs n'est l'œuvre de
 *   personne d'autre. Aucune licence à honorer, aucun fichier à re-sourcer si un site disparaît ;
 * - **zéro octet expédié** : le budget d'images d'une partie est contrôlé en CI
 *   (`docs/jeu/ASSETS.md`), et dix-sept sons l'auraient entamé pour rien ;
 * - **testable sans navigateur** : une recette est de la donnée. Les volumes relatifs, la file, le
 *   rattrapage se vérifient en `vitest`, exactement comme le moteur de jeu.
 *
 * ## Le son suit l'événement, jamais l'écran
 *
 * C'est la même doctrine que le socle d'animation (`lib/game/animations.ts`), et ce n'est pas une
 * coïncidence : {@link planifierSons} **part du plan d'animations** (`planifier()`). Un son et son
 * animation viennent donc littéralement de la même entrée, et il est impossible qu'ils se mettent
 * à parler de deux événements différents. Le serveur fait autorité ; un son ne décide de rien, ne
 * retient rien, et son absence ne bloque rien.
 *
 * ## Ce que la file garantit
 *
 * - **rien ne se rejoue** : une resynchronisation qui recouvre ne refait pas entendre un K.O. déjà
 *   passé ({@link FileSons.vues}) ;
 * - **rien ne devient un bourdonnement** : deux sons ne peuvent pas démarrer à moins de
 *   {@link ECART_MIN} millisecondes l'un de l'autre ;
 * - **une reprise ne joue pas vingt sons** : au-delà de {@link SEUIL_RATTRAPAGE_SONS} en attente,
 *   on ne garde que le dernier — celui qui explique la situation présente. Les autres sont
 *   **comptés** ({@link FileSons.ignores}), jamais perdus en silence : le journal de partie en
 *   porte déjà la phrase, et le compte est exposé pour qu'on puisse le voir.
 *
 * Le réglage, lui, est **mémorisé par appareil** (DJ9) et non par compte — contrairement au confort
 * (`lib/game/confort.ts`) ou aux emotes. C'est délibéré : le volume supportable dépend de l'endroit
 * et de l'appareil, pas de la personne. Le même enfant veut du son sur la tablette du salon et le
 * silence sur le téléphone emprunté dans le train.
 */

import { type Animation, type CoupAnimation, planifier } from "@/lib/game/animations";
import { SPECS, type Typage, intensiteDe } from "@/lib/game/anim-types";

/** Les formes d'onde dont une recette dispose. `bruit` n'a pas de hauteur : c'est du souffle. */
export type Forme = "sinus" | "triangle" | "carre" | "scie" | "bruit";

/**
 * Une composante d'un son : une onde qui glisse d'une fréquence à une autre.
 *
 * Le glissando n'est pas un ornement, c'est **ce qui fait le sens** : une fréquence qui tombe
 * s'entend comme une chute (K.O.), une fréquence qui monte comme une réussite (évolution,
 * victoire). Deux sons de même durée et de même volume peuvent ainsi raconter l'inverse l'un de
 * l'autre, sans qu'aucun mot soit prononcé.
 */
export type Partiel = {
  forme: Forme;
  /** Fréquence de départ, en hertz. Ignorée pour `bruit`, qui n'a pas de hauteur. */
  depart: number;
  /** Fréquence d'arrivée, en hertz : égale à `depart` pour une note tenue. */
  arrivee: number;
  /** Poids de cette composante dans le mélange, dans `]0, 1]`. */
  poids: number;
  /** Décalage du départ, en millisecondes — ce qui fait les sons à deux temps (la pièce). */
  retard: number;
};

/**
 * Un son, décrit entièrement. **Sérialisable** : aucune fonction, aucune référence au navigateur.
 *
 * L'enveloppe (`attaque` / `chute`) est ce qui empêche un son synthétique d'être agressif : une
 * onde qui démarre à plein volume produit un claquement (le « clic » de l'audio numérique). Toutes
 * les recettes d'ici montent et descendent progressivement — c'est le minimum pour qu'un son
 * fabriqué soit supportable à la vingtième écoute.
 */
export type Recette = {
  /** Ce que le son raconte, en français : affiché par la banque `/jeu/sons`. */
  libelle: string;
  /** Les composantes à mélanger. */
  partiels: Partiel[];
  /** Durée totale, en millisecondes, bornée à {@link DUREE_SON_MAX}. */
  duree: number;
  /** Montée du volume, en millisecondes (jamais nulle : une montée nulle claque). */
  attaque: number;
  /** Descente du volume, en millisecondes. */
  chute: number;
  /** Volume relatif, dans `]0, GAIN_MAX]`. */
  gain: number;
  /**
   * Coupure d'un filtre passe-bas, en hertz.
   *
   * C'est le réglage qui rend un son « non agressif » (exigence du lot) : une onde carrée ou en
   * dents de scie est riche en harmoniques aiguës, et ce sont elles qui fatiguent. On les rabote
   * systématiquement plutôt que d'éviter ces formes — on perdrait le claquement de l'éclair et le
   * choc du métal, qui sont justement ce qu'on veut entendre.
   */
  passeBas: number;
};

/** Durée maximale d'un son, en millisecondes : au-delà, un bruitage devient une musique. */
export const DUREE_SON_MAX = 1200;

/** Durée maximale d'un son **de coup** : la fin de partie seule a droit de durer plus. */
export const DUREE_COUP_MAX = 700;

/**
 * Volume relatif maximal d'une recette.
 *
 * Plafonné bien en dessous de 1 pour une raison mesurable : deux sons peuvent se chevaucher
 * (l'écart minimum est de {@link ECART_MIN} ms, pas de la durée d'un son), et deux gains proches de
 * 1 qui s'additionnent saturent — ce qui s'entend comme une distorsion sale. La marge est ici.
 */
export const GAIN_MAX = 0.4;

/** Écart minimum entre deux départs de son, en millisecondes. En dessous, c'est un bourdonnement. */
export const ECART_MIN = 90;

/** Au-delà de ce nombre de sons en attente, on ne garde que le dernier (reprise après coupure). */
export const SEUIL_RATTRAPAGE_SONS = 4;

/** Nombre de clés mémorisées pour ne pas rejouer un son déjà entendu (borne mémoire). */
const MEMOIRE_CLES = 300;

/**
 * La **banque de sons** : dix-sept recettes, et l'origine de chacune est la ligne qui la décrit.
 *
 * Les neuf sons exigés par le lot y sont — carte posée, énergie attachée, attaque, K.O.,
 * récompense, pile ou face, minuterie, victoire, défaite — et huit voisins qui leur évitent d'être
 * des exceptions : laisser la pioche, l'évolution ou le début de tour muets aurait fabriqué un jeu
 * qui sonne par intermittence, ce qui s'entend plus mal que pas de son du tout.
 *
 * Chaque recette est construite autour d'un sens, pas d'un timbre :
 *
 * | | ce que l'oreille doit comprendre |
 * |---|---|
 * | `pose`, `energie` | quelque chose vient de se poser : court, mat, sans hauteur marquée |
 * | `pioche` | du papier : surtout du souffle, presque pas de note |
 * | `evolution`, `victoire` | ça **monte** |
 * | `ko`, `defaite` | ça **tombe** |
 * | `piece` | deux temps — le lancer, puis la retombée |
 * | `minuterie` | le plus discret de tous, et c'est un invariant testé |
 */
export const SONS = {
  pose: {
    libelle: "Une carte se pose sur le plateau",
    partiels: [
      { forme: "triangle", depart: 420, arrivee: 300, poids: 0.7, retard: 0 },
      { forme: "bruit", depart: 0, arrivee: 0, poids: 0.3, retard: 0 },
    ],
    duree: 180,
    attaque: 8,
    chute: 140,
    gain: 0.2,
    passeBas: 2600,
  },
  energie: {
    libelle: "Une Énergie s'attache",
    partiels: [
      { forme: "sinus", depart: 600, arrivee: 900, poids: 0.8, retard: 0 },
      { forme: "triangle", depart: 1200, arrivee: 1800, poids: 0.2, retard: 20 },
    ],
    duree: 220,
    attaque: 10,
    chute: 180,
    gain: 0.18,
    passeBas: 3200,
  },
  pioche: {
    // Du papier qui glisse : presque pas de note, parce qu'une note transforme une pioche en
    // événement. On pioche beaucoup — ce son est entendu plus souvent que tous les autres.
    libelle: "Une carte est piochée",
    partiels: [
      { forme: "bruit", depart: 0, arrivee: 0, poids: 0.85, retard: 0 },
      { forme: "sinus", depart: 700, arrivee: 520, poids: 0.15, retard: 0 },
    ],
    duree: 150,
    attaque: 12,
    chute: 120,
    gain: 0.16,
    passeBas: 2200,
  },
  evolution: {
    libelle: "Un Pokémon évolue",
    partiels: [
      { forme: "sinus", depart: 440, arrivee: 880, poids: 0.55, retard: 0 },
      { forme: "triangle", depart: 660, arrivee: 1320, poids: 0.35, retard: 60 },
      { forme: "sinus", depart: 880, arrivee: 1760, poids: 0.1, retard: 120 },
    ],
    duree: 520,
    attaque: 20,
    chute: 340,
    gain: 0.28,
    passeBas: 3600,
  },
  impact: {
    libelle: "Les dégâts portent",
    partiels: [
      { forme: "carre", depart: 180, arrivee: 90, poids: 0.5, retard: 0 },
      { forme: "bruit", depart: 0, arrivee: 0, poids: 0.5, retard: 0 },
    ],
    duree: 220,
    attaque: 4,
    chute: 190,
    gain: 0.3,
    passeBas: 1800,
  },
  echec: {
    // L'attaque est partie et n'a rien touché : ça descend et ça s'éteint, sans impact.
    libelle: "L'attaque échoue",
    partiels: [
      { forme: "triangle", depart: 520, arrivee: 200, poids: 0.7, retard: 0 },
      { forme: "bruit", depart: 0, arrivee: 0, poids: 0.3, retard: 40 },
    ],
    duree: 300,
    attaque: 14,
    chute: 250,
    gain: 0.18,
    passeBas: 1600,
  },
  ko: {
    libelle: "Un Pokémon est mis K.O.",
    partiels: [
      { forme: "scie", depart: 300, arrivee: 70, poids: 0.55, retard: 0 },
      { forme: "carre", depart: 150, arrivee: 50, poids: 0.25, retard: 30 },
      { forme: "bruit", depart: 0, arrivee: 0, poids: 0.2, retard: 0 },
    ],
    duree: 560,
    attaque: 6,
    chute: 460,
    gain: 0.34,
    passeBas: 1400,
  },
  recompense: {
    libelle: "Une récompense est prise",
    partiels: [
      { forme: "sinus", depart: 880, arrivee: 1320, poids: 0.6, retard: 0 },
      { forme: "sinus", depart: 1320, arrivee: 1760, poids: 0.4, retard: 90 },
    ],
    duree: 380,
    attaque: 10,
    chute: 300,
    gain: 0.26,
    passeBas: 4000,
  },
  piece: {
    // Deux temps, et c'est tout le sens : on entend le lancer, puis la retombée. Le hasard doit
    // s'entendre pour être accepté (R-12.1) — la même raison qui lui vaut une animation.
    libelle: "Une pièce est lancée",
    partiels: [
      { forme: "triangle", depart: 1400, arrivee: 1900, poids: 0.45, retard: 0 },
      { forme: "triangle", depart: 1100, arrivee: 700, poids: 0.4, retard: 240 },
      { forme: "bruit", depart: 0, arrivee: 0, poids: 0.15, retard: 240 },
    ],
    duree: 460,
    attaque: 6,
    chute: 180,
    gain: 0.22,
    passeBas: 5000,
  },
  objet: {
    libelle: "Une carte Dresseur est jouée",
    partiels: [
      { forme: "triangle", depart: 520, arrivee: 380, poids: 0.6, retard: 0 },
      { forme: "bruit", depart: 0, arrivee: 0, poids: 0.4, retard: 0 },
    ],
    duree: 200,
    attaque: 10,
    chute: 160,
    gain: 0.18,
    passeBas: 2400,
  },
  talent: {
    libelle: "Un talent s'active",
    partiels: [
      { forme: "sinus", depart: 300, arrivee: 760, poids: 0.7, retard: 0 },
      { forme: "sinus", depart: 450, arrivee: 1140, poids: 0.3, retard: 50 },
    ],
    duree: 340,
    attaque: 24,
    chute: 280,
    gain: 0.22,
    passeBas: 3000,
  },
  tour: {
    libelle: "C'est ton tour",
    partiels: [
      { forme: "sinus", depart: 660, arrivee: 660, poids: 0.6, retard: 0 },
      { forme: "sinus", depart: 990, arrivee: 990, poids: 0.4, retard: 110 },
    ],
    duree: 300,
    attaque: 16,
    chute: 150,
    gain: 0.14,
    passeBas: 3000,
  },
  minuterie: {
    // Le son le plus discret de la banque, et ce n'est pas une préférence : le lot l'exige
    // nommément (« qu'aucun son ne surprenne, la minuterie surtout »). Un test interdit qu'une
    // recette descende jamais plus bas que celle-ci — la garde est dans le code, pas dans ce
    // commentaire. Il sonne **une fois** au passage du seuil, jamais à chaque seconde : un tic
    // répété sur un enfant qui cherche son coup, c'est de la pression, pas de l'information.
    libelle: "Le temps presse",
    partiels: [{ forme: "sinus", depart: 880, arrivee: 820, poids: 1, retard: 0 }],
    duree: 140,
    attaque: 18,
    chute: 110,
    gain: 0.1,
    passeBas: 2000,
  },
  victoire: {
    libelle: "Tu gagnes",
    partiels: [
      { forme: "sinus", depart: 523, arrivee: 523, poids: 0.3, retard: 0 },
      { forme: "sinus", depart: 659, arrivee: 659, poids: 0.3, retard: 140 },
      { forme: "sinus", depart: 784, arrivee: 784, poids: 0.25, retard: 280 },
      { forme: "sinus", depart: 1047, arrivee: 1047, poids: 0.15, retard: 420 },
    ],
    duree: 1100,
    attaque: 16,
    chute: 520,
    gain: 0.38,
    passeBas: 4400,
  },
  defaite: {
    // La défaite descend, mais elle ne se moque pas : pas de dissonance, pas de « buzzer ». Le
    // public de ce jeu a onze ans, et perdre suffit — le son n'a pas à en rajouter. C'est la même
    // règle que le catalogue d'emotes, où aucune emote ne peut narguer (DJ10).
    libelle: "Tu perds",
    partiels: [
      { forme: "sinus", depart: 523, arrivee: 523, poids: 0.35, retard: 0 },
      { forme: "sinus", depart: 440, arrivee: 440, poids: 0.35, retard: 180 },
      { forme: "sinus", depart: 349, arrivee: 330, poids: 0.3, retard: 360 },
    ],
    duree: 950,
    attaque: 20,
    chute: 480,
    gain: 0.3,
    passeBas: 2600,
  },
  egalite: {
    libelle: "Égalité",
    partiels: [
      { forme: "sinus", depart: 523, arrivee: 523, poids: 0.5, retard: 0 },
      { forme: "sinus", depart: 523, arrivee: 523, poids: 0.5, retard: 300 },
    ],
    duree: 700,
    attaque: 20,
    chute: 340,
    gain: 0.26,
    passeBas: 3000,
  },
  attaque: {
    // Le **geste** de l'attaque, délibérément neutre : c'est l'impact qui porte le type
    // ({@link sonImpact}), parce que c'est l'événement `degats` qui porte la donnée. Ce son existe
    // pour qu'une attaque s'entende partir même quand elle ne touchera personne — un silence
    // ferait croire que rien n'a été joué.
    libelle: "Une attaque est déclarée",
    partiels: [
      { forme: "triangle", depart: 420, arrivee: 260, poids: 0.6, retard: 0 },
      { forme: "bruit", depart: 0, arrivee: 0, poids: 0.4, retard: 0 },
    ],
    duree: 300,
    attaque: 8,
    chute: 240,
    gain: 0.26,
    passeBas: 2800,
  },
} satisfies Record<string, Recette>;

/** Les clés de la banque — l'union réelle, pas une liste recopiée à côté. */
export type CleSon = keyof typeof SONS & string;

/**
 * Le **timbre** de chaque type d'énergie : de quoi retimbrer le son d'un coup porté
 * ({@link sonImpact}).
 *
 * Une ligne par type de `SPECS` (`lib/game/anim-types.ts`), et c'est vérifié par un test : ajouter
 * un douzième type d'énergie à l'effet visuel sans lui donner de timbre ferait jouer un son
 * d'attaque neutre là où l'écran montrerait un effet typé — l'image et le son se mettraient à
 * raconter deux choses, et personne ne l'aurait su.
 *
 * Les valeurs suivent ce que l'effet visuel montre déjà (`SpecType.geste`) : le Feu crépite (du
 * bruit, bas), l'Éclair claque (une carrée haute qui s'effondre), la Fée tinte (une sinusoïde
 * presque sans bruit). Le son ne raconte pas autre chose que l'image.
 */
export type Timbre = { forme: Forme; depart: number; arrivee: number; bruit: number };

export const TIMBRES_TYPE = {
  fire: { forme: "scie", depart: 180, arrivee: 90, bruit: 0.45 },
  water: { forme: "sinus", depart: 520, arrivee: 180, bruit: 0.3 },
  grass: { forme: "triangle", depart: 740, arrivee: 420, bruit: 0.2 },
  lightning: { forme: "carre", depart: 1200, arrivee: 260, bruit: 0.5 },
  psychic: { forme: "sinus", depart: 320, arrivee: 880, bruit: 0.1 },
  fighting: { forme: "carre", depart: 140, arrivee: 70, bruit: 0.35 },
  darkness: { forme: "triangle", depart: 200, arrivee: 110, bruit: 0.25 },
  metal: { forme: "carre", depart: 1500, arrivee: 900, bruit: 0.3 },
  dragon: { forme: "scie", depart: 260, arrivee: 130, bruit: 0.3 },
  fairy: { forme: "sinus", depart: 980, arrivee: 1320, bruit: 0.05 },
  colorless: { forme: "triangle", depart: 420, arrivee: 300, bruit: 0.15 },
} satisfies Record<string, Timbre>;

/**
 * Le timbre d'un type d'énergie, ou `undefined` si ce type n'en a pas.
 *
 * Passe par une lecture gardée plutôt qu'un index direct : `typage.type` vient du serveur, donc
 * c'est une chaîne quelconque, et un index non vérifié rendrait `undefined` en prétendant rendre un
 * timbre. Le test de parité avec `SPECS` fait que ce cas ne peut venir que d'un type que l'écran
 * ignore aussi — jamais d'un oubli de notre côté.
 */
export function timbrePourType(type: string): Timbre | undefined {
  return Object.prototype.hasOwnProperty.call(TIMBRES_TYPE, type)
    ? TIMBRES_TYPE[type as keyof typeof TIMBRES_TYPE]
    : undefined;
}

/** Borne un gain dans `]0, GAIN_MAX]` : aucune recette ne peut saturer la sortie. */
export function bornerGain(gain: number): number {
  if (!Number.isFinite(gain) || gain <= 0) return 0;
  return Math.min(gain, GAIN_MAX);
}

/** Borne une durée dans `[0, DUREE_SON_MAX]`. */
export function bornerDuree(duree: number): number {
  if (!Number.isFinite(duree) || duree <= 0) return 0;
  return Math.min(Math.round(duree), DUREE_SON_MAX);
}

/**
 * La recette d'un coup **porté**, retimbrée par le type d'énergie et l'intensité réelle.
 *
 * ## Pourquoi le timbre est ici, et non sur l'attaque déclarée
 *
 * Ce n'est pas un choix esthétique, c'est **là qu'est la donnée**. Le socle d'animation ne typpe
 * `attaque_declaree` que lorsque l'attaque a **raté** (`typageEvenement` de `animations.ts`) :
 * pour un coup qui porte, c'est l'événement `degats` qui porte le type, les dégâts réels, la
 * faiblesse et la résistance. Poser le timbre sur l'attaque déclarée aurait donné un son typé
 * seulement pour les attaques ratées, donc jamais quand ça compte — et le silence de ce défaut
 * aurait été indistinguable d'un choix. C'est le test
 * « retimbre l'impact depuis le typage que le plan d'animation a calculé » qui l'a trouvé.
 *
 * L'intensité vient de {@link intensiteDe} — la même fonction qui dimensionne l'effet visuel. Un
 * coup faible est donc à la fois plus discret à l'écran et plus discret à l'oreille, sans qu'aucun
 * seuil ne soit recopié ici : les deux sortent du même calcul, à partir des dégâts que le serveur
 * a réellement appliqués.
 *
 * @param typage ce que le serveur dit du coup. Type inconnu → la recette de base, inchangée.
 */
export function sonImpact(typage: Typage | null): Recette {
  const base = SONS.impact;
  if (!typage || !typage.type) return base;
  const timbre = timbrePourType(typage.type);
  // Type absent du tableau des timbres : on garde la base plutôt que d'inventer un son. Le test de
  // parité avec `SPECS` fait que ce cas ne peut venir que d'un type que l'écran ignore aussi.
  if (!timbre) return base;

  const intensite = intensiteDe(typage);
  return {
    ...base,
    libelle: `Impact ${SPECS[typage.type]?.libelle ?? typage.type}`,
    partiels: [
      {
        forme: timbre.forme,
        depart: timbre.depart,
        arrivee: timbre.arrivee,
        poids: 1 - timbre.bruit,
        retard: 0,
      },
      { forme: "bruit", depart: 0, arrivee: 0, poids: timbre.bruit, retard: 0 },
    ],
    // Un coup léger ne doit pas sonner comme un coup décisif, mais il doit rester audible : le
    // gain va de 55 % à 100 % de la recette de base, jamais à zéro.
    gain: bornerGain(base.gain * (0.55 + 0.45 * intensite)),
    passeBas: timbre.forme === "carre" || timbre.forme === "scie" ? 2200 : 3200,
  };
}

/**
 * La recette d'une attaque **déclarée** : le geste, pas le coup.
 *
 * Volontairement **neutre** quand l'attaque part normalement — c'est l'impact qui portera le type
 * ({@link sonImpact}). Le seul cas où elle change, c'est l'**échec** : une attaque qui n'a touché
 * personne ne doit pas sonner comme une attaque qui a porté, sinon le joueur croit avoir gagné des
 * dégâts qu'il n'a pas infligés. Et c'est précisément le cas que le socle typpe.
 */
export function sonAttaque(typage: Typage | null): Recette {
  return typage?.echec ? SONS.echec : SONS.attaque;
}

/**
 * Le registre **événement → son**, délibérément partiel.
 *
 * Partiel pour la même raison que celui des animations : les quarante-deux types que le serveur
 * diffuse n'ont pas tous à faire du bruit. Un mélange de pioche, un verrou d'effet, un Checkup
 * d'état se lisent dans le journal — les sonoriser ferait un jeu qui cliquette en permanence, et
 * c'est exactement ce qui pousse quelqu'un à couper le son pour de bon.
 *
 * ⚠️ Chaque clé doit être un type d'événement que le serveur émet réellement
 * (`TYPES_EVENEMENT_CONNUS` de `journal.ts`) : un test le vérifie et nomme la ligne fautive. Une
 * faute de frappe ici produirait un son qui ne se déclenche jamais — la pire des pannes, celle
 * qu'on ne voit pas, puisque le silence est une sortie plausible.
 */
export const SONS_PAR_EVENEMENT: Record<string, CleSon> = {
  // Ce que le joueur fait de ses mains.
  pokemon_pose: "pose",
  energie_attachee: "energie",
  cartes_piochees: "pioche",
  mulligan: "pioche",
  evolution: "evolution",
  objet_joue: "objet",
  supporter_joue: "objet",
  stade_joue: "objet",
  outil_attache: "objet",
  outil_retire: "objet",
  talent_active: "talent",
  // Les déplacements de l'Actif : un Pokémon qui vient se mettre en place se pose, comme une carte.
  retraite_effectuee: "pose",
  echange_force_effectue: "pose",
  promotion_effectuee: "pose",
  // Le cœur d'un échange. `attaque_declaree` est retimbrée par le type (voir {@link sonAttaque}),
  // `ko` produit en plus le son de récompense quand le serveur en a fait prendre.
  attaque_declaree: "attaque",
  degats: "impact",
  ko: "ko",
  // Le hasard, qui doit s'entendre pour être accepté (R-12.1).
  dsl_pile_ou_face: "piece",
  confusion_resolue: "piece",
  // Le rythme, et la fin.
  tour_commence: "tour",
  partie_terminee: "victoire",
};

/**
 * Un coup diffusé, tel que la file de sons le consomme.
 *
 * C'est exactement `CoupAnimation` : le son et l'image lisent la **même** forme, et ce n'est pas une
 * commodité — c'est ce qui rend impossible qu'un jour l'une accepte un coup que l'autre refuse.
 */
export type CoupSons = CoupAnimation;

/** Un son planifié : la recette à jouer, et de quel événement elle vient. */
export type SonPlanifie = {
  /** Clé stable `numero:rang[:suffixe]` — identité du son, et anti-doublon de resynchronisation. */
  cle: string;
  /** Clé de banque d'origine, pour le débogage et la galerie `/jeu/sons`. */
  son: CleSon;
  /** La recette exacte à jouer, retimbrage compris : auto-portée, comme une `Animation`. */
  recette: Recette;
};

/** Lit un entier de `donnees`, ou `undefined` (jamais une supposition). */
function entier(d: Record<string, unknown>, cle: string): number | undefined {
  const v = d[cle];
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

/**
 * L'issue d'une fin de partie, du point de vue du destinataire de la vue.
 *
 * Le serveur dit qui gagne (`donnees.vainqueur`) ; on compare, on ne déduit rien d'autre. Pas de
 * vainqueur = égalité — et l'égalité a son propre son, parce que la faire sonner comme une défaite
 * serait annoncer un résultat qui n'est pas arrivé.
 */
export function issueFin(donnees: Record<string, unknown>, pour: string): CleSon {
  const vainqueur = donnees.vainqueur;
  if (typeof vainqueur !== "string" || !vainqueur) return "egalite";
  return vainqueur === pour ? "victoire" : "defaite";
}

/**
 * Les sons d'**une** animation planifiée — zéro, un, ou deux.
 *
 * Deux dans un seul cas, et il compte : un `ko` qui fait prendre des récompenses est **deux**
 * moments (le Pokémon tombe, puis l'adversaire prend ses cartes), que le serveur envoie sur un
 * seul événement. La file des moments clés fait déjà ce découpage côté image
 * (`anim-moments.ts`) ; le son le fait ici, pour la même raison : les entendre fondus en un seul
 * bruit ferait disparaître l'information la plus importante de la partie — le compte des
 * récompenses.
 *
 * @param donnees les données brutes de l'événement (le plan d'animation ne les conserve pas).
 * @param pour    le destinataire de la vue, pour trancher victoire ou défaite.
 */
export function sonsPourAnimation(
  animation: Animation,
  donnees: Record<string, unknown>,
  pour: string,
): SonPlanifie[] {
  const clef = SONS_PAR_EVENEMENT[animation.type];
  if (!clef) return [];

  if (animation.type === "attaque_declaree") {
    const recette = sonAttaque(animation.typage);
    return [{ cle: animation.cle, son: recette === SONS.echec ? "echec" : "attaque", recette }];
  }

  if (animation.type === "degats") {
    return [{ cle: animation.cle, son: "impact", recette: sonImpact(animation.typage) }];
  }

  if (animation.type === "partie_terminee") {
    const issue = issueFin(donnees, pour);
    return [{ cle: animation.cle, son: issue, recette: SONS[issue] }];
  }

  const premier: SonPlanifie = { cle: animation.cle, son: clef, recette: SONS[clef] };
  if (animation.type === "ko" && (entier(donnees, "recompenses_prises") ?? 0) > 0) {
    return [
      premier,
      { cle: `${animation.cle}:recompense`, son: "recompense", recette: SONS.recompense },
    ];
  }
  return [premier];
}

/**
 * Planifie les sons d'une suite de coups diffusés.
 *
 * Elle **part du plan d'animations** (`planifier()`), et c'est le point important du lot : le son
 * et l'image naissent de la même entrée, dans le même ordre, avec le même typage d'attaque. Il n'y
 * a pas deux lectures des événements qui pourraient divergir — il n'y en a qu'une.
 *
 * Les données brutes, elles, ne survivent pas au plan d'animation (une `Animation` est
 * volontairement auto-portée) : on les relit en parallèle, par coup et par rang, pour les deux
 * seuls sons qui en dépendent — les récompenses d'un K.O. et le vainqueur d'une fin de partie.
 */
export function planifierSons(coups: CoupAnimation[], pour: string): SonPlanifie[] {
  // Index `numero:rang` → données brutes, pour retrouver ce que le plan d'animation a laissé.
  const brutes = new Map<string, Record<string, unknown>>();
  for (const coup of coups) {
    (coup.evenements ?? []).forEach((brut, rang) => {
      const evt = (brut ?? {}) as { donnees?: Record<string, unknown> };
      const donnees = evt.donnees && typeof evt.donnees === "object" ? evt.donnees : {};
      brutes.set(`${coup.numero}:${rang}`, donnees);
    });
  }
  return planifier(coups, pour).flatMap((animation) =>
    sonsPourAnimation(animation, brutes.get(`${animation.numero}:${animation.rang}`) ?? {}, pour),
  );
}

/**
 * L'état de la file de sons.
 *
 * Sérialisable de bout en bout, comme la file d'animations : elle se teste par milliers de cas sans
 * navigateur et sans `AudioContext`.
 */
export type FileSons = {
  /** Les sons à jouer, dans l'ordre. */
  attente: SonPlanifie[];
  /** Instant (ms, échelle de l'appelant) du dernier départ, ou `null` si rien n'a encore sonné. */
  dernierDepart: number | null;
  /** Clés déjà jouées : une resynchronisation qui recouvre ne refait pas entendre le passé. */
  vues: string[];
  /**
   * Nombre de sons **volontairement** non joués — par rattrapage, par coupure, ou parce que le
   * joueur n'avait pas encore interagi quand ils sont arrivés.
   *
   * Compté et exposé, jamais tu : c'est la différence entre un choix de conception (on ne joue pas
   * vingt sons d'affilée après une reconnexion) et un repli silencieux, que ce dépôt interdit. Le
   * journal de partie porte de son côté la phrase de chacun de ces événements.
   */
  ignores: number;
};

/** Une file vide. */
export const FILE_SONS_VIDE: FileSons = {
  attente: [],
  dernierDepart: null,
  vues: [],
  ignores: 0,
};

/** Ce qu'on peut demander à la file de sons. */
export type ActionSons =
  | { type: "empiler"; sons: SonPlanifie[] }
  | { type: "passer"; sons: SonPlanifie[] }
  | { type: "couper" }
  | { type: "reinitialiser" };

/** Mémorise des clés jouées, en bornant la mémoire (une partie longue ne doit pas enfler). */
function memoriser(vues: string[], cles: string[]): string[] {
  const fusion = [...vues, ...cles];
  return fusion.length > MEMOIRE_CLES ? fusion.slice(fusion.length - MEMOIRE_CLES) : fusion;
}

/**
 * Le réducteur de la file — **pur**.
 *
 * `empiler` applique le rattrapage tout de suite : la file ne détient donc jamais vingt sons en
 * attente, même une fraction de seconde. C'est volontaire — un rattrapage appliqué au tirage
 * aurait laissé une fenêtre où un changement de réglage ou une coupure aurait trouvé une file
 * invraisemblable à vider.
 */
export function reduireSons(file: FileSons, action: ActionSons): FileSons {
  switch (action.type) {
    case "reinitialiser":
      // Changement de partie : file neuve, mémoire comprise (les numéros de coup d'une autre
      // partie n'ont rien à voir avec ceux-ci).
      return { ...FILE_SONS_VIDE };

    case "couper":
      // Couper doit être **immédiat** : ce qui attendait ne sonnera pas, et ne sonnera jamais —
      // on le mémorise pour qu'un rétablissement ne déverse pas l'arriéré d'un coup.
      return {
        ...file,
        attente: [],
        vues: memoriser(
          file.vues,
          file.attente.map((s) => s.cle),
        ),
        ignores: file.ignores + file.attente.length,
      };

    case "passer":
      // Des sons qu'on **décide** de ne pas jouer, sans même les mettre en attente.
      //
      // Le cas réel : les coups déjà diffusés quand le joueur arrive sur la page. Un F5 au
      // quatre-vingtième tour fait livrer toute la partie d'un bloc, et le navigateur interdit de
      // toute façon de sonner avant un geste. Les tenir en réserve pour les lâcher au premier clic
      // ferait entendre un K.O. d'il y a dix minutes au moment où le joueur touche l'écran : le son
      // raconte ce qui arrive, pas ce qui est arrivé avant qu'on écoute.
      //
      // Ils sont mémorisés (donc jamais rejoués plus tard) **et comptés** : c'est un choix de
      // conception, et un choix se montre.
      return {
        ...file,
        vues: memoriser(
          file.vues,
          action.sons.map((s) => s.cle),
        ),
        ignores: file.ignores + action.sons.length,
      };

    case "empiler": {
      const connues = new Set([...file.vues, ...file.attente.map((s) => s.cle)]);
      const nouvelles = action.sons.filter((s) => !connues.has(s.cle));
      if (nouvelles.length === 0) return file;
      const attente = [...file.attente, ...nouvelles];
      if (attente.length <= SEUIL_RATTRAPAGE_SONS) return { ...file, attente };
      // Reprise après coupure : on ne garde que le dernier son — celui qui explique la situation
      // présente. Les autres sont comptés, et leur phrase est dans le journal.
      const garde = attente.slice(-1);
      return {
        ...file,
        attente: garde,
        vues: memoriser(
          file.vues,
          attente.slice(0, -1).map((s) => s.cle),
        ),
        ignores: file.ignores + attente.length - 1,
      };
    }

    default:
      return file;
  }
}

/**
 * Tire le prochain son à jouer, si l'écart minimum est respecté.
 *
 * Renvoie la file **et** le son, plutôt que de poser le son dans l'état : un son n'est pas un état,
 * c'est un événement. Le laisser dans la file obligerait l'appelant à le reconsommer — et un
 * re-rendu de React au mauvais moment le ferait entendre deux fois.
 *
 * @param maintenant instant courant, en millisecondes (horloge de l'appelant, injectable en test).
 */
export function tirerSon(
  file: FileSons,
  maintenant: number,
): { file: FileSons; son: SonPlanifie | null } {
  const suivant = file.attente[0];
  if (!suivant) return { file, son: null };
  if (file.dernierDepart !== null && maintenant - file.dernierDepart < ECART_MIN) {
    return { file, son: null };
  }
  return {
    file: {
      ...file,
      attente: file.attente.slice(1),
      dernierDepart: maintenant,
      vues: memoriser(file.vues, [suivant.cle]),
    },
    son: suivant,
  };
}

/* ────────────────────────────── Les réglages, par appareil ────────────────────────────── */

/** Clé de stockage local des réglages de son. Par **appareil** (DJ9), jamais par compte. */
export const CLE_SONS = "pbm.jeu.sons";

/** Les réglages de son d'un appareil. */
export type ReglagesSons = {
  /** Les bruitages jouent. Activés par défaut (DJ9). */
  bruitages: boolean;
  /** La musique d'ambiance joue. **Coupée** par défaut (DJ9). */
  musique: boolean;
  /** Volume général, dans `[0, 1]`. */
  volume: number;
};

/**
 * Les défauts, et ils sont la décision DJ9 mot pour mot : *« Bruitages activés, musique coupée,
 * réglage mémorisé par appareil »*.
 *
 * Le volume part à 0,7 et non à 1 : le plafond de gain des recettes ({@link GAIN_MAX}) est déjà
 * calculé pour ne pas saturer, et 0,7 laisse au joueur de la marge **vers le haut** — un réglage
 * qui ne peut que baisser s'entend comme une panne.
 */
export const SONS_DEFAUT: ReglagesSons = {
  bruitages: true,
  musique: false,
  volume: 0.7,
};

/**
 * Normalise des réglages venus du stockage local : une version précédente, un JSON bricolé à la
 * main ou une clé manquante retombent sur les défauts **champ par champ**, jamais en bloc.
 */
export function normaliserSons(brut: unknown): ReglagesSons {
  const o = (brut ?? {}) as Partial<Record<keyof ReglagesSons, unknown>>;
  const volume = typeof o.volume === "number" && Number.isFinite(o.volume) ? o.volume : SONS_DEFAUT.volume;
  return {
    bruitages: typeof o.bruitages === "boolean" ? o.bruitages : SONS_DEFAUT.bruitages,
    musique: typeof o.musique === "boolean" ? o.musique : SONS_DEFAUT.musique,
    volume: Math.min(1, Math.max(0, volume)),
  };
}

/**
 * La musique d'ambiance : une boucle lente, **coupée par défaut** (DJ9).
 *
 * Une phrase de cinq notes sur une gamme pentatonique — l'échelle qui ne produit aucun intervalle
 * dissonant, quel que soit l'ordre des notes. C'est ce qui permet de la faire tourner pendant une
 * partie de vingt minutes sans qu'elle agace : il n'y a pas de tension à résoudre, donc pas
 * d'attente qu'on déçoit à chaque tour de boucle.
 *
 * Son gain est le plus bas de tout le fichier, minuterie comprise : c'est un fond, et un fond qui
 * s'entend n'est plus un fond.
 */
export const MUSIQUE: { notes: number[]; duree: number; ecart: number; gain: number; passeBas: number } = {
  notes: [261.63, 293.66, 349.23, 392.0, 440.0],
  duree: 1800,
  ecart: 1500,
  gain: 0.06,
  passeBas: 1400,
};

/** Le temps d'un tour complet de la boucle de musique, en millisecondes. */
export function dureeBoucleMusique(): number {
  return MUSIQUE.notes.length * MUSIQUE.ecart + MUSIQUE.duree;
}

/**
 * Seuil, en millisecondes, sous lequel la minuterie se fait entendre — **une fois**.
 *
 * Dix secondes : assez pour agir (poser une Énergie, choisir une cible), trop peu pour qu'un
 * rappel soit une politesse. En dessous, un enfant n'aurait pas le temps de faire quoi que ce soit
 * du son qu'il vient d'entendre, et on l'aurait juste pressé.
 */
export const SEUIL_MINUTERIE_MS = 10_000;
