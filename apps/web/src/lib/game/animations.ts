/**
 * Socle d'animation du plateau (lot `j-anim-socle`) — **pur** : ni React, ni DOM, ni E/S.
 *
 * Le principe qui gouverne tout ce module, et qui est la raison même du lot : **les effets suivent
 * les événements, jamais l'inverse**. Le serveur fait autorité ; la vue affichée est toujours la
 * sienne (`VuePartie`, projetée par `pbm_game.sortie`). Une animation n'est qu'une **transition** —
 * elle raconte ce que le serveur a déjà décidé. Elle n'est jamais une source de vérité, et rien de
 * ce qu'elle fait (ni sa durée, ni sa fin) ne conditionne l'état montré ni le droit de jouer.
 *
 * Ce que cela interdit, explicitement (c'est le risque nommé par le lot) : faire dépendre l'état
 * affiché de la fin d'une animation. Au moindre onglet passé en arrière-plan, le plateau se
 * figerait dans un état faux. Ici la file ne retient **rien** : elle se vide, l'écran reste juste.
 *
 * Trois garanties, chacune tenue par un test de `animations.test.ts` :
 *
 * - **une seule animation à la fois** ({@link FileAnimations.courante}) : le nombre d'éléments
 *   animés simultanément est borné à un, quoi qu'il arrive. C'est ce qui tient le plancher
 *   d'images par seconde ({@link PLANCHER_FPS}) sur un téléphone d'entrée de gamme ;
 * - **aucun événement ne disparaît** : un type inconnu du registre {@link EFFETS} produit tout de
 *   même son entrée dans le plan, avec `effet: null` et une durée nulle — il traverse la file sans
 *   la bloquer et sans rien masquer (D9 : on n'approxime pas un effet qu'on ne connaît pas) ;
 * - **rattrapage** : à la reconnexion, les vingt événements manqués ne se rejouent pas un par un —
 *   ils se **résument** en une seule animation ({@link rattraper}).
 *
 * Les durées sont **bornées** ({@link DUREE_MAX}) et modulées par un {@link ModeAnimation} : normal,
 * accéléré (le joueur est pressé) ou réduit (`prefers-reduced-motion`, où tout devient instantané).
 */

import { type Typage } from "@/lib/game/anim-types";

/** Mode de restitution des animations. `reduit` gagne toujours sur `accelere`. */
export type ModeAnimation = "normal" | "accelere" | "reduit";

/** Le camp d'une animation, pour la teinter comme le journal (`CategorieLigne`). */
export type CampAnimation = "moi" | "adversaire" | "auto";

/** Un événement diffusé par le serveur, dans la forme tolérante du temps réel. */
export type EvenementAnimation = { type?: string; donnees?: Record<string, unknown> };

/** Un coup diffusé : son numéro de séquence et ses événements déjà projetés par le serveur. */
export type CoupAnimation = { numero: number; evenements: unknown[] };

/**
 * Une animation planifiée : tout ce qu'il faut pour la dessiner, sans jamais relire la vue.
 *
 * Elle est **auto-portée** (aucune dépendance à l'état courant) : c'est ce qui permet de la jeter à
 * tout instant — quand le joueur agit, quand l'onglet passe en arrière-plan, quand la file
 * rattrape son retard — sans rien casser.
 */
export type Animation = {
  /** Clé stable `numero:rang` (ou `resume:…`) : identité de l'animation, et anti-doublon de resync. */
  cle: string;
  /** Numéro du coup d'où vient l'événement. */
  numero: number;
  /** Rang de l'événement dans le coup (`-1` pour une animation de rattrapage). */
  rang: number;
  /** Type brut de l'événement moteur (`degats`, `ko`…), ou `rattrapage` pour un résumé. */
  type: string;
  /** Nom de l'effet visuel à jouer, ou `null` quand aucun effet n'est défini pour ce type. */
  effet: string | null;
  /** Durée en millisecondes, bornée à {@link DUREE_MAX}. `0` quand il n'y a pas d'effet. */
  duree: number;
  /** `instance_id` de la carte de base concernée, ou `null` (on n'invente jamais une cible). */
  cible: string | null;
  /** Camp concerné, pour la teinte. */
  camp: CampAnimation;
  /** `true` si cette animation **résume** plusieurs événements rattrapés. */
  resume: boolean;
  /** Nombre d'événements que l'animation représente (1 hors rattrapage). */
  nombre: number;
  /**
   * Ce que le serveur dit de l'attaque, quand cette animation en est une — ou `null`.
   *
   * C'est ce qui permet l'effet **par type** (lot `j-anim-attaques-typees`) : type d'énergie,
   * dégâts, faiblesse, résistance, échec. Le champ est **obligatoire** (quitte à valoir `null`)
   * pour qu'aucun producteur d'animation ne puisse l'oublier sans que TypeScript le dise : un
   * `typage` oublié ferait disparaître l'effet typé en silence, et le plateau continuerait
   * d'avoir l'air de marcher.
   */
  typage: Typage | null;
};

/** Durée maximale d'une animation, en millisecondes : au-delà, le jeu attend l'écran. */
export const DUREE_MAX = 900;

/** Facteur du mode accéléré : une animation y dure le quart de sa durée nominale. */
export const FACTEUR_ACCELERE = 4;

/**
 * Plancher d'images par seconde tenu sur l'**appareil de référence** — un téléphone d'entrée de
 * gamme, modélisé en recette par une fenêtre de 844×390 et un bridage processeur ×4
 * (`e2e/anim-fluidite.spec.ts`). Ce plancher n'est pas une intention : il est **mesuré** en CI, et
 * il est tenu par construction (une seule animation à la fois, et des propriétés CSS composables —
 * `transform`/`opacity` uniquement, gardé par `src/__tests__/anim-css-garde.test.ts`).
 */
export const PLANCHER_FPS = 30;

/** Durée de l'animation de résumé quand la file rattrape son retard. */
export const DUREE_RESUME = 450;

/** Au-delà de ce nombre d'animations en attente, la file résume au lieu de tout rejouer. */
export const SEUIL_RATTRAPAGE = 6;

/** Budget de temps (ms) d'une rafale d'animations : au-delà, la file résume. */
export const BUDGET_RATTRAPAGE = 2400;

/** Nombre d'animations récentes conservées telles quelles par un rattrapage. */
export const GARDEES_RATTRAPAGE = 2;

/** Nombre de clés mémorisées pour ne pas rejouer un coup déjà animé (borne mémoire). */
const MEMOIRE_CLES = 300;

/**
 * Le registre des effets : à quel type d'événement moteur correspond quel effet visuel, et pendant
 * combien de temps.
 *
 * Il est **délibérément partiel**. Les 42 types que le serveur diffuse (`TYPES_EVENEMENT_CONNUS`
 * de `journal.ts`) n'ont pas tous à bouger l'écran : un mélange de pioche ou un verrou d'effet se
 * lit dans le journal, pas en fanfare. Un type absent d'ici n'est donc **pas** une lacune — c'est
 * un choix, et il reste visible : son entrée existe dans le plan, avec `effet: null`.
 *
 * Les effets fins (une attaque Feu qui brûle la carte d'en face, le Pokémon qui apparaît au-dessus
 * de sa carte) sont les lots aval `j-anim-attaques-typees`, `j-anim-evolution-ko` et
 * `j-anim-pokemon-apparition` : ils enrichiront ce registre, pas la mécanique.
 */
export const EFFETS: Record<string, { effet: string; duree: number }> = {
  // Le cœur d'un échange : on annonce, on frappe, on tombe.
  attaque_declaree: { effet: "attaque", duree: 360 },
  degats: { effet: "impact", duree: 420 },
  ko: { effet: "ko", duree: 600 },
  // Ce que le joueur fait de ses mains.
  cartes_piochees: { effet: "pioche", duree: 260 },
  mulligan: { effet: "pioche", duree: 260 },
  pokemon_pose: { effet: "pose", duree: 300 },
  evolution: { effet: "evolution", duree: 520 },
  energie_attachee: { effet: "energie", duree: 300 },
  objet_joue: { effet: "carte-jouee", duree: 280 },
  supporter_joue: { effet: "carte-jouee", duree: 280 },
  stade_joue: { effet: "carte-jouee", duree: 280 },
  outil_attache: { effet: "outil", duree: 260 },
  outil_retire: { effet: "outil", duree: 260 },
  talent_active: { effet: "talent", duree: 320 },
  // Les déplacements de l'Actif.
  retraite_effectuee: { effet: "retraite", duree: 320 },
  echange_force_effectue: { effet: "retraite", duree: 320 },
  promotion_effectuee: { effet: "promotion", duree: 320 },
  // Ce que le jeu fait tout seul, et qu'il faut comprendre sans lire.
  etat_checkup: { effet: "etat", duree: 340 },
  effet_expire: { effet: "etat", duree: 220 },
  tour_commence: { effet: "tour", duree: 240 },
  // Le hasard, qui doit se voir pour être accepté (R-12.1).
  dsl_pile_ou_face: { effet: "piece", duree: 480 },
  confusion_resolue: { effet: "piece", duree: 480 },
  // La fin.
  partie_terminee: { effet: "fin", duree: 700 },
};

/** Borne une durée dans `[0, DUREE_MAX]` : aucune animation ne fait attendre le jeu. */
export function borner(duree: number): number {
  if (!Number.isFinite(duree) || duree <= 0) return 0;
  return Math.min(Math.round(duree), DUREE_MAX);
}

/** Lit une chaîne de `donnees`, ou `undefined` (jamais une supposition). */
function chaine(d: Record<string, unknown>, cle: string): string | undefined {
  const v = d[cle];
  return typeof v === "string" && v ? v : undefined;
}

/**
 * La carte de base du Pokémon concerné par un événement, ou `null`.
 *
 * Les événements de coup désignent leur Pokémon par `pokemon` ou `base` ; les dégâts et les K.O.
 * désignent leur **cible**. On ne devine rien au-delà : sans l'une de ces trois clés, l'animation
 * n'a pas de cible et se joue au centre de l'arène.
 */
export function cibleEvenement(donnees: Record<string, unknown>): string | null {
  return chaine(donnees, "pokemon") ?? chaine(donnees, "base") ?? chaine(donnees, "cible") ?? null;
}

/**
 * Le camp d'un événement : celui du destinataire de la vue, l'adversaire, ou « auto » quand
 * l'événement n'appartient à personne (Checkup, fin de partie). Jamais une déduction de règle.
 */
export function campEvenement(donnees: Record<string, unknown>, pour: string): CampAnimation {
  const joueur = chaine(donnees, "joueur");
  if (!joueur) return "auto";
  return joueur === pour ? "moi" : "adversaire";
}

/** Lit un entier de `donnees`, ou `undefined` (jamais une supposition). */
function entier(d: Record<string, unknown>, cle: string): number | undefined {
  const v = d[cle];
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

/**
 * Ce que le **coup entier** dit de l'attaque en cours : son type, et si elle a raté.
 *
 * Ces deux faits ne sont pas sur l'événement qui s'anime, mais sur ses voisins du même coup :
 * `attaque_declaree` porte le **type** (lot `j-anim-attaques-typees`, côté moteur), et c'est un
 * `dsl_pile_ou_face` sans aucune face — ou une Confusion tombée sur pile (R-11.5) — qui dit
 * l'**échec**. On lit donc le coup en entier avant de planifier ses événements un par un.
 *
 * Sans `attaque_declaree`, pas de type : le coup n'est pas une attaque (ou vient d'un chemin sans
 * catalogue), et aucun effet typé ne sera joué (D9).
 */
function contexteAttaque(evenements: unknown[]): { type: string; echec: boolean } {
  let type = "";
  let echec = false;
  for (const brut of evenements) {
    const evt = (brut ?? {}) as EvenementAnimation;
    const donnees = evt.donnees && typeof evt.donnees === "object" ? evt.donnees : {};
    if (evt.type === "attaque_declaree") {
      type = chaine(donnees, "type") ?? type;
    } else if (evt.type === "dsl_pile_ou_face") {
      // Zéro face sur au moins une pièce lancée : le hasard a tranché contre l'attaquant.
      const pieces = entier(donnees, "pieces") ?? 0;
      if (pieces > 0 && (entier(donnees, "faces") ?? 0) === 0) echec = true;
    } else if (evt.type === "confusion_resolue" && donnees.attaque_annulee === true) {
      echec = true;
    }
  }
  return { type, echec };
}

/**
 * Le typage d'**un** événement, ou `null` quand cet événement n'est pas un coup porté.
 *
 * Trois événements seulement sont typés, et chacun pour une raison :
 *
 * - `degats` — le coup a porté : type, dégâts réels, faiblesse et résistance viennent du serveur ;
 * - `attaque_declaree` avec un échec dans le coup — l'attaque est partie et n'a rien touché ;
 * - `dsl_pile_ou_face` / `confusion_resolue` perdus — le moment même du ratage.
 *
 * Tous les autres valent `null` : une pioche ou une évolution n'a pas de type d'attaque, et lui en
 * inventer un ferait brûler une carte sans raison.
 */
function typageEvenement(
  typeEvt: string,
  donnees: Record<string, unknown>,
  contexte: { type: string; echec: boolean },
): Typage | null {
  if (!contexte.type) return null;
  if (typeEvt === "degats") {
    return {
      type: contexte.type,
      degats: entier(donnees, "degats") ?? 0,
      faiblesse: donnees.faiblesse === true,
      resistance: donnees.resistance === true,
      echec: false,
    };
  }
  if (!contexte.echec) return null;
  if (
    typeEvt === "attaque_declaree" ||
    typeEvt === "dsl_pile_ou_face" ||
    typeEvt === "confusion_resolue"
  ) {
    return { type: contexte.type, degats: 0, faiblesse: false, resistance: false, echec: true };
  }
  return null;
}

/**
 * Planifie les animations d'**un** coup : une entrée par événement, dans l'ordre, sans exception.
 *
 * Un événement dont le type est absent du registre {@link EFFETS} produit tout de même son entrée
 * (`effet: null`, `duree: 0`) : c'est le critère « un événement sans animation définie ne bloque ni
 * ne disparaît ». Il traverse la file en un instant, et le journal en porte la phrase.
 *
 * Chaque entrée reçoit en plus son {@link Animation.typage} — ce que le serveur a dit de l'attaque,
 * d'où l'effet typé se déduit entièrement. Le contexte est lu sur le **coup entier** d'abord :
 * l'événement `degats` précède `attaque_declaree` dans la liste, et c'est ce dernier qui porte le
 * type.
 */
export function planifierCoup(coup: CoupAnimation, pour: string): Animation[] {
  const evenements = coup.evenements ?? [];
  const contexte = contexteAttaque(evenements);
  return evenements.map((brut, rang) => {
    const evt = (brut ?? {}) as EvenementAnimation;
    const type = typeof evt.type === "string" ? evt.type : "";
    const donnees = evt.donnees && typeof evt.donnees === "object" ? evt.donnees : {};
    const defini = EFFETS[type];
    return {
      cle: `${coup.numero}:${rang}`,
      numero: coup.numero,
      rang,
      type: type || "inconnu",
      effet: defini ? defini.effet : null,
      duree: defini ? borner(defini.duree) : 0,
      cible: cibleEvenement(donnees),
      camp: campEvenement(donnees, pour),
      resume: false,
      nombre: 1,
      typage: typageEvenement(type, donnees, contexte),
    };
  });
}

/** Planifie les animations d'une suite de coups, rangés par numéro croissant. */
export function planifier(coups: CoupAnimation[], pour: string): Animation[] {
  return [...coups]
    .sort((a, b) => a.numero - b.numero)
    .flatMap((coup) => planifierCoup(coup, pour));
}

/** Réglages du rattrapage, pour les tests et pour un éventuel ajustement mesuré. */
export type OptionsRattrapage = { seuil?: number; budget?: number; gardees?: number };

/**
 * **Rattrape** une file en retard : au-delà d'un seuil (nombre d'animations ou temps total), on ne
 * rejoue pas tout — on résume.
 *
 * C'est la situation de la reprise après coupure : le canal temps réel resynchronise depuis le
 * dernier coup appliqué et livre d'un bloc les vingt événements manqués. Les rejouer un par un
 * ferait attendre dix secondes devant un film que personne n'a demandé. On garde donc les
 * {@link GARDEES_RATTRAPAGE} dernières animations — celles qui expliquent la situation présente —
 * et on remplace tout ce qui précède par **une** animation de résumé qui dit combien.
 *
 * Les entrées **sans effet** sont toutes conservées : elles ne coûtent rien (durée nulle) et les
 * perdre reviendrait à masquer des événements, ce que ce module ne fait jamais.
 */
export function rattraper(animations: Animation[], options: OptionsRattrapage = {}): Animation[] {
  const seuil = options.seuil ?? SEUIL_RATTRAPAGE;
  const budget = options.budget ?? BUDGET_RATTRAPAGE;
  const gardees = options.gardees ?? GARDEES_RATTRAPAGE;

  const animees = animations.filter((a) => a.effet !== null);
  const total = animees.reduce((s, a) => s + a.duree, 0);
  if (animees.length <= seuil && total <= budget) return animations;

  const conservees = new Set(animees.slice(-gardees).map((a) => a.cle));
  const resumees = animees.filter((a) => !conservees.has(a.cle));
  const premier = resumees[0];
  const dernier = resumees[resumees.length - 1];
  if (!premier || !dernier) return animations;

  const resume: Animation = {
    cle: `resume:${premier.cle}-${dernier.cle}`,
    numero: dernier.numero,
    rang: -1,
    type: "rattrapage",
    effet: "rattrapage",
    duree: borner(DUREE_RESUME),
    cible: null,
    camp: "auto",
    resume: true,
    // On somme les `nombre` plutôt que de compter les entrées : un résumé déjà en attente qui se
    // fait résumer à son tour (deux coupures de suite) continue de dire combien d'événements réels
    // il représente, et non « 1 ».
    nombre: resumees.reduce((s, a) => s + a.nombre, 0),
    // Un résumé n'a pas de type : il représente plusieurs coups, peut-être de plusieurs types. Lui
    // donner celui du dernier ferait brûler le plateau pour des dégâts déjà encaissés.
    typage: null,
  };
  const restantes = animations.filter((a) => a.effet === null || conservees.has(a.cle));
  return [resume, ...restantes];
}

/**
 * L'état de la file d'animations : au plus **une** animation en cours, le reste en attente.
 *
 * Sérialisable de bout en bout (aucune fonction, aucune référence DOM) : la file se teste par
 * milliers de cas sans navigateur, exactement comme le moteur.
 */
export type FileAnimations = {
  /** Les animations à jouer, dans l'ordre. */
  attente: Animation[];
  /** L'animation en cours — **au plus une**, c'est l'invariant qui tient la fluidité. */
  courante: Animation | null;
  /** Temps déjà écoulé sur l'animation courante, en millisecondes. */
  ecoule: number;
  /** Mode de restitution courant. */
  mode: ModeAnimation;
  /** Clés déjà passées : une resynchronisation qui recouvre ne rejoue pas ce qui a été vu. */
  vues: string[];
};

/** Une file vide, au mode normal. */
export const FILE_VIDE: FileAnimations = {
  attente: [],
  courante: null,
  ecoule: 0,
  mode: "normal",
  vues: [],
};

/**
 * Ce qu'on peut demander à la file.
 *
 * - `empiler` : de nouvelles animations arrivent (un coup diffusé, ou une resync) ;
 * - `avancer` : le temps passe de `dt` millisecondes ;
 * - `sauter` : le joueur passe l'animation en cours ;
 * - `vider` : on jette tout (le joueur agit, l'onglet passe en arrière-plan) — l'état affiché ne
 *   bouge pas d'un pixel, puisqu'il ne dépend pas de la file ;
 * - `mode` : normal, accéléré, ou réduit.
 */
export type ActionFile =
  | { type: "empiler"; animations: Animation[]; options?: OptionsRattrapage }
  | { type: "avancer"; dt: number }
  | { type: "sauter" }
  | { type: "vider" }
  | { type: "reinitialiser" }
  | { type: "mode"; mode: ModeAnimation };

/** La durée réellement jouée d'une animation, selon le mode (réduit = instantané). */
export function dureeEffective(animation: Animation, mode: ModeAnimation): number {
  if (mode === "reduit") return 0;
  if (mode === "accelere") return Math.round(animation.duree / FACTEUR_ACCELERE);
  return animation.duree;
}

/** Mémorise une clé vue, en bornant la mémoire (une partie longue ne doit pas enfler). */
function memoriser(vues: string[], cles: string[]): string[] {
  const fusion = [...vues, ...cles];
  return fusion.length > MEMOIRE_CLES ? fusion.slice(fusion.length - MEMOIRE_CLES) : fusion;
}

/** Prend la tête de l'attente comme nouvelle animation courante (ou `null` si plus rien). */
function tirer(file: FileAnimations): FileAnimations {
  const attente = [...file.attente];
  const suivante = attente.shift() ?? null;
  return { ...file, attente, courante: suivante, ecoule: 0 };
}

/**
 * Le réducteur de la file — **pur** : même entrée, même sortie, aucun effet de bord.
 *
 * `avancer` consomme le temps donné et enchaîne autant d'animations que ce temps permet : une
 * rafale d'entrées sans effet (durée nulle) se vide donc en **un seul** appel, sans jamais retenir
 * la suivante. C'est ce qui fait qu'un événement non animé ne bloque pas la file.
 */
export function reduireFile(file: FileAnimations, action: ActionFile): FileAnimations {
  switch (action.type) {
    case "mode":
      return { ...file, mode: action.mode };

    case "reinitialiser":
      // Changement de partie : on repart d'une file neuve, mémoire comprise (les numéros de coup
      // d'une autre partie n'ont rien à voir avec ceux-ci). Le mode choisi, lui, survit.
      return { ...FILE_VIDE, mode: file.mode };

    case "vider":
      // On mémorise ce qu'on jette : une resync ultérieure ne doit pas le rejouer.
      return {
        ...file,
        attente: [],
        courante: null,
        ecoule: 0,
        vues: memoriser(
          file.vues,
          [file.courante, ...file.attente].filter((a): a is Animation => !!a).map((a) => a.cle),
        ),
      };

    case "empiler": {
      const connues = new Set([
        ...file.vues,
        ...file.attente.map((a) => a.cle),
        ...(file.courante ? [file.courante.cle] : []),
      ]);
      const nouvelles = action.animations.filter((a) => !connues.has(a.cle));
      if (nouvelles.length === 0) return file;
      const attente = rattraper([...file.attente, ...nouvelles], action.options);
      const avec: FileAnimations = { ...file, attente };
      return file.courante ? avec : tirer(avec);
    }

    case "sauter": {
      if (!file.courante) return file;
      const vues = memoriser(file.vues, [file.courante.cle]);
      return tirer({ ...file, vues });
    }

    case "avancer": {
      if (!file.courante) return file;
      let courant: FileAnimations = file;
      let reste = Math.max(0, action.dt);
      // Tant que le temps disponible couvre l'animation en cours, on l'achève et on enchaîne.
      while (courant.courante) {
        const duree = dureeEffective(courant.courante, courant.mode);
        if (courant.ecoule + reste < duree) {
          courant = { ...courant, ecoule: courant.ecoule + reste };
          break;
        }
        reste -= duree - courant.ecoule;
        courant = tirer({
          ...courant,
          vues: memoriser(courant.vues, [courant.courante.cle]),
        });
      }
      return courant;
    }

    default:
      return file;
  }
}

/** Le temps qu'il reste à jouer sur l'animation courante (0 si la file est au repos). */
export function restant(file: FileAnimations): number {
  if (!file.courante) return 0;
  return Math.max(0, dureeEffective(file.courante, file.mode) - file.ecoule);
}
