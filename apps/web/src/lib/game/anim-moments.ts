/**
 * Les six **moments clés** d'une partie (lot `j-anim-evolution-ko`) — module **pur** : ni React,
 * ni DOM, ni E/S.
 *
 * Évoluer, mettre K.O., prendre une récompense, poser la mise en place, repiocher, lancer la pièce :
 * ce sont les instants qu'un joueur raconte après la partie. Les jouer platement, c'est perdre
 * l'essentiel de l'émotion du jeu — c'est le gain que nomme le lot.
 *
 * ## Deux files, pas une
 *
 * Le socle (`animations.ts`) garde sa file : une pastille à la fois, au rythme du registre
 * {@link EFFETS}. Les moments ont la **leur** ({@link reduireMoments}), et ce n'est pas un doublon :
 *
 * - un moment **vit plus longtemps que la case que le socle lui donne** (le socle borne tout à
 *   {@link DUREE_MAX} = 900 ms, et un K.O. qui bascule, se désature puis rejoint la défausse a
 *   besoin de ses trois temps) ;
 * - surtout, deux moments peuvent naître du **même** événement — un `ko` porte à la fois la mise
 *   K.O. *et* la prise de récompenses (`recompenses_prises`), que le serveur n'émet pas séparément.
 *   Le socle, lui, produit une entrée par événement : il ne pourrait pas en faire deux.
 *
 * Et c'est cette file séparée qui tient le **critère d'acceptation n°1** : un double K.O. produit
 * quatre moments (K.O., récompenses, K.O., récompenses), joués **un par un**, aucun perdu, aucun
 * superposé. Un simple `setState` par effet — ce que fait l'effet typé du lot précédent, qui n'en a
 * jamais deux à la fois — aurait écrasé le premier K.O. par le second, et personne ne l'aurait vu
 * manquer.
 *
 * ## Un système, pas six animations
 *
 * Même parade que `anim-types.ts`, et pour la même raison : **six couches** ({@link CoucheMoment})
 * et **cinq gestes** ({@link GesteMoment}), chacun avec *une* image-clé CSS écrite une seule fois,
 * composés par une **table** ({@link MOMENTS}) de six lignes — de la donnée, pas du code. Les
 * images-clés sont nommées `pbm-anim-fx-m-*` : elles passent donc sous la **même** garde statique
 * que tout le reste (`src/__tests__/anim-css-garde.test.ts`, qui n'autorise que `transform` et
 * `opacity`), et le plancher d'images par seconde reste tenu par construction.
 *
 * ## Ce que ces animations ne font jamais
 *
 * - **durer plus que le plaisir** : {@link MOMENT_MAX_MS} = 1,5 s, borne nommée par le lot
 *   (« au-delà d'une seconde et demie, elle agace au lieu de marquer »), tenue par construction et
 *   vérifiée pour les six genres ;
 * - **retenir l'état du plateau** : comme le socle, un moment ne conditionne rien. On le jette à
 *   tout instant (le joueur agit, l'onglet passe en arrière-plan) sans qu'un pixel de l'état bouge ;
 * - **inventer un résultat** : le pile ou face est **honnête** — voir {@link effetMoment} et la
 *   raison détaillée sur {@link EffetMoment.revelationA}.
 */

import { type CampAnimation, type CoupAnimation, type EvenementAnimation } from "@/lib/game/animations";

/**
 * Les six genres de moments. Un genre, c'est **une** composition de couches et de gestes — pas une
 * animation écrite à part.
 */
export type GenreMoment =
  | "evolution"
  | "ko"
  | "recompense"
  | "mise-en-place"
  | "mulligan"
  | "piece";

/**
 * Les six **couches** dont se composent tous les moments. Chacune a une image-clé unique dans
 * `globals.css` (`pbm-anim-fx-m-*`), et n'animera jamais que `transform` et `opacity`.
 *
 * - `halo` — une auréole lumineuse qui gonfle puis retombe (l'évolution, la récompense révélée) ;
 * - `fondu` — un fondu enchaîné de l'image entrante sur la sortante (l'évolution, la révélation) ;
 * - `voile` — un voile sombre qui éteint l'objet (le K.O. qui se désature) ;
 * - `traine` — une traînée le long du trajet parcouru (vers la défausse, vers la main) ;
 * - `eclat` — un éclat bref (la révélation simultanée, la récompense qui se retourne) ;
 * - `rotation` — la pièce qui tourne (le pile ou face, et lui seul).
 */
export type CoucheMoment = "halo" | "fondu" | "voile" | "traine" | "eclat" | "rotation";

/**
 * Ce que l'**objet** du moment (une carte, une pièce) fait de lui-même.
 *
 * Toujours un `transform` : aucune boîte de disposition ne change, donc rien ne peut provoquer de
 * défilement — le plateau n'en tolère aucun (lot `j-plateau-layout`).
 */
export type GesteMoment = "aucun" | "bascule" | "envol" | "retournement" | "pose";

/**
 * Un **temps** du moment : ce qui se joue, et pour quelle part de la durée totale.
 *
 * Les moments de ce lot sont des récits en deux ou trois temps (« la carte bascule, se désature,
 * *puis* rejoint la défausse »). Les découper en phases pondérées, plutôt qu'en durées fixes, est ce
 * qui permet de **comprimer** le moment entier quand la file est en retard sans réécrire la table :
 * les parts restent les mêmes, le total change.
 */
export type PhaseMoment = {
  /** Nom du temps, posé en `data-phase` et lu par le CSS. */
  nom: string;
  /** Les couches à composer pendant ce temps, dans l'ordre de rendu. */
  couches: CoucheMoment[];
  /** Ce que l'objet fait pendant ce temps. */
  geste: GesteMoment;
  /** Part de la durée totale (poids relatif, pas des millisecondes). */
  poids: number;
};

/** La composition d'un genre : ses temps, son tempo, son nom. C'est de la **donnée**. */
export type SpecMoment = {
  /** Le genre décrit. */
  genre: GenreMoment;
  /** Le mot qui coiffe le moment à l'écran. */
  libelle: string;
  /** Les temps du moment, dans l'ordre. */
  phases: PhaseMoment[];
  /** Durée nominale en millisecondes, avant compression. Toujours ≤ {@link MOMENT_MAX_MS}. */
  duree: number;
  /** `true` si le **plateau entier** tremble (le K.O., et lui seul). */
  secousse: boolean;
  /** `true` si le moment fait voyager **plusieurs** objets, échelonnés. */
  echelonne: boolean;
};

/**
 * Le temps **maximal** qu'un moment peut occuper l'écran.
 *
 * C'est le risque que le lot nomme, mot pour mot : « faire durer l'animation de K.O. plus que le
 * plaisir : au-delà d'une seconde et demie, elle agace au lieu de marquer ». La borne est donc
 * écrite ici, appliquée par {@link effetMoment} et vérifiée **pour les six genres** — pas laissée à
 * la vigilance de celui qui ajoutera la septième ligne.
 */
export const MOMENT_MAX_MS = 1500;

/** Décalage visé entre deux objets échelonnés (deux récompenses, sept cartes), avant rabotage. */
export const DECALAGE_OBJET = 90;

/**
 * Plafond d'objets réellement rendus dans un moment.
 *
 * Sept, parce qu'une main de départ en compte sept (R-4.1) : c'est le moment le plus chargé, et le
 * raboter aurait fait mentir l'écran sur le nombre de cartes repiochées.
 */
export const OBJETS_MAX = 7;

/**
 * Combien de temps la **version réduite** d'un moment reste à l'écran.
 *
 * Elle ne bouge pas : il lui faut donc le temps d'être lue, là où une animation se comprend en la
 * voyant passer. Même valeur que la version réduite des effets typés, pour que les deux ne se
 * contredisent pas à l'écran.
 */
export const DUREE_REDUITE_MOMENT = 1000;

/** Au-delà de ce nombre de moments en attente, la file **comprime** au lieu de laisser filer. */
export const COMPRESSION_SEUIL = 2;

/**
 * Compression minimale : un moment ne descend jamais sous cette fraction de sa durée.
 *
 * Il n'y a **pas** de plancher à zéro, et c'est volontaire : comprimer jusqu'à l'invisible
 * reviendrait à perdre le moment, ce que le critère d'acceptation n°1 interdit. Une rafale va donc
 * vite, mais elle se voit encore — et le bouton « Passer » reste là pour qui ne veut pas la voir.
 */
export const COMPRESSION_MIN = 0.45;

/** Nombre de clés mémorisées pour ne pas rejouer un moment déjà vu (borne mémoire). */
const MEMOIRE_CLES = 200;

/**
 * Les six moments, et ce dont ils sont faits.
 *
 * ⚠️ Toute ligne ajoutée ici doit avoir ses couches et ses gestes déclarés dans `globals.css` : le
 * test `src/__tests__/anim-moments-css-garde.test.ts` le vérifie et nomme la ligne fautive. Une
 * couche sans image-clé ne bougerait pas — un moment muet, donc un moment qui mentirait.
 */
export const MOMENTS: Record<GenreMoment, SpecMoment> = {
  /**
   * L'évolution : la carte d'évolution se pose en fondu lumineux sur la précédente, et **la pile se
   * voit** — les deux cartes restent empilées, c'est ce qui fait comprendre qu'on a évolué et non
   * remplacé.
   */
  evolution: {
    genre: "evolution",
    libelle: "Évolution !",
    phases: [
      { nom: "montee", couches: ["halo"], geste: "pose", poids: 2 },
      { nom: "fondu", couches: ["fondu", "eclat"], geste: "aucun", poids: 3 },
    ],
    duree: 620,
    secousse: false,
    echelonne: false,
  },

  /**
   * La mise K.O. : la carte bascule, se désature, puis rejoint la défausse. Trois temps, parce que
   * les trois se lisent — une carte qui disparaît d'un coup ne raconte rien.
   */
  ko: {
    genre: "ko",
    libelle: "K.O. !",
    phases: [
      { nom: "bascule", couches: [], geste: "bascule", poids: 2 },
      { nom: "extinction", couches: ["voile"], geste: "aucun", poids: 2 },
      { nom: "defausse", couches: ["traine"], geste: "envol", poids: 3 },
    ],
    duree: 760,
    secousse: true,
    echelonne: false,
  },

  /**
   * La prise de récompense : la carte quitte la ligne des récompenses et rejoint la main, **au dos
   * puis révélée**.
   *
   * `echelonne` est le critère d'acceptation n°2 : deux récompenses se voient comme **deux** cartes,
   * décalées, et non comme un unique vol groupé.
   */
  recompense: {
    genre: "recompense",
    libelle: "Récompense",
    phases: [
      { nom: "vol", couches: ["traine"], geste: "envol", poids: 3 },
      { nom: "revelation", couches: ["halo", "eclat"], geste: "retournement", poids: 2 },
    ],
    duree: 680,
    secousse: false,
    echelonne: true,
  },

  /**
   * La mise en place initiale : les cartes se distribuent, les récompenses s'alignent, et la
   * **révélation simultanée est un moment**.
   *
   * C'est le premier effet que voit un joueur (point 2 de la mission du lot) : il a donc droit à la
   * durée la plus longue des six, et à ses trois temps entiers.
   */
  "mise-en-place": {
    genre: "mise-en-place",
    libelle: "En place !",
    phases: [
      { nom: "distribution", couches: ["traine"], geste: "pose", poids: 3 },
      { nom: "alignement", couches: [], geste: "pose", poids: 2 },
      { nom: "revelation", couches: ["fondu", "eclat", "halo"], geste: "retournement", poids: 3 },
    ],
    duree: 1200,
    secousse: false,
    echelonne: true,
  },

  /** Le mulligan : la main est révélée, puis remélangée (R-4.4). Deux temps, dans cet ordre. */
  mulligan: {
    genre: "mulligan",
    libelle: "Reprise",
    phases: [
      { nom: "revelation", couches: ["fondu"], geste: "retournement", poids: 3 },
      { nom: "remelange", couches: ["traine"], geste: "envol", poids: 2 },
    ],
    duree: 900,
    secousse: false,
    echelonne: true,
  },

  /**
   * Le pile ou face : la pièce tourne, puis s'arrête sur le résultat **du serveur**.
   *
   * Les deux temps ne sont pas décoratifs, ils portent le critère d'acceptation n°3 : le résultat
   * n'existe à l'écran qu'au temps `arret`. Voir {@link EffetMoment.revelationA}.
   */
  piece: {
    genre: "piece",
    libelle: "Pile ou face",
    phases: [
      { nom: "rotation", couches: ["rotation"], geste: "aucun", poids: 3 },
      { nom: "arret", couches: ["eclat"], geste: "pose", poids: 1 },
    ],
    duree: 820,
    secousse: false,
    echelonne: true,
  },
};

/**
 * Le résultat d'un lancer, **tel que le serveur l'a tranché**.
 *
 * Le serveur n'envoie que des **comptes** (`pieces`, `faces` de `dsl_pile_ou_face`) : il ne dit pas
 * *quelle* pièce est tombée sur face, parce que le moteur n'a pas d'ordre à leur donner. L'écran en
 * fabrique donc un — les `faces` premières — et c'est de la **présentation**, pas de l'information
 * inventée : le compte affiché est exactement celui du serveur, et c'est le seul fait qui existe.
 */
export type ResultatPiece = {
  /** Nombre de pièces lancées (≥ 1). */
  pieces: number;
  /** Nombre de faces obtenues, entre 0 et {@link ResultatPiece.pieces}. */
  faces: number;
};

/**
 * Un moment **planifié** : tout ce qu'il faut pour le jouer, sans jamais relire la vue.
 *
 * Auto-porté comme une `Animation` du socle : c'est ce qui permet de le jeter à tout instant sans
 * rien casser, puisque l'état affiché n'en dépend pas.
 */
export type MomentPlanifie = {
  /** Clé stable `numero:rang:genre` — un `ko` en produit deux, elles ne peuvent pas se confondre. */
  cle: string;
  /** Le genre du moment. */
  genre: GenreMoment;
  /** Numéro du coup d'où vient l'événement. */
  numero: number;
  /** Rang de l'événement dans le coup. */
  rang: number;
  /** `instance_id` de la carte concernée, ou `null` (on n'invente jamais une cible). */
  cible: string | null;
  /** Camp concerné, pour la teinte — celui à qui le moment **profite**. */
  camp: CampAnimation;
  /** Nombre d'objets à faire voyager (cartes, pièces), déjà borné à {@link OBJETS_MAX}. */
  objets: number;
  /** Le résultat du lancer, pour le genre `piece` — `null` partout ailleurs. */
  piece: ResultatPiece | null;
  /** Précision libre tirée de l'événement (le nom de l'évolution), ou `null`. */
  detail: string | null;
};

/** Lit une chaîne de `donnees`, ou `undefined` (jamais une supposition). */
function chaine(d: Record<string, unknown>, cle: string): string | undefined {
  const v = d[cle];
  return typeof v === "string" && v ? v : undefined;
}

/** Lit un entier positif de `donnees`, ou `undefined` (jamais une supposition). */
function entier(d: Record<string, unknown>, cle: string): number | undefined {
  const v = d[cle];
  return typeof v === "number" && Number.isFinite(v) ? Math.trunc(v) : undefined;
}

/** Borne un nombre d'objets dans `[1, OBJETS_MAX]`. */
function bornerObjets(n: number): number {
  if (!Number.isFinite(n) || n < 1) return 1;
  return Math.min(OBJETS_MAX, Math.trunc(n));
}

/** Le camp d'un joueur nommé, du point de vue du destinataire de la vue. */
function campDe(joueur: string | undefined, pour: string): CampAnimation {
  if (!joueur) return "auto";
  return joueur === pour ? "moi" : "adversaire";
}

/**
 * Les moments d'**un** événement — zéro, un, ou **deux**.
 *
 * Deux est le cas du `ko` : le serveur ne sépare pas la mise K.O. de la prise de récompenses
 * (`recompenses_prises` voyage sur le même événement), alors que ce sont bien deux moments
 * distincts dans la demande du lot. On les sépare donc ici, et la file les joue l'un après l'autre.
 *
 * Zéro est le cas normal de la grande majorité des événements : un mélange de pioche ou un verrou
 * d'effet n'est pas un moment clé. Les laisser sans moment n'est pas une lacune — leur en inventer
 * un noierait les six qui comptent.
 */
export function momentsEvenement(
  evt: EvenementAnimation,
  numero: number,
  rang: number,
  pour: string,
): MomentPlanifie[] {
  const type = typeof evt.type === "string" ? evt.type : "";
  const d = evt.donnees && typeof evt.donnees === "object" ? evt.donnees : {};
  const base = { numero, rang, piece: null, detail: null } as const;
  const cle = (genre: GenreMoment) => `${numero}:${rang}:${genre}`;

  switch (type) {
    case "evolution":
      return [
        {
          ...base,
          cle: cle("evolution"),
          genre: "evolution",
          cible: chaine(d, "base") ?? null,
          camp: campDe(chaine(d, "joueur"), pour),
          // Deux cartes : la base dessous, l'évoluée dessus. C'est **la pile qui se voit** — et
          // deux est tout ce que l'événement permet d'affirmer (il ne porte pas l'étage).
          objets: 2,
          detail: chaine(d, "nom") ?? null,
        },
      ];

    case "ko": {
      const prises = entier(d, "recompenses_prises") ?? 0;
      const moments: MomentPlanifie[] = [
        {
          ...base,
          cle: cle("ko"),
          genre: "ko",
          cible: chaine(d, "pokemon") ?? null,
          // `joueur` est le propriétaire du Pokémon tombé : le K.O. est un moment de SON camp.
          camp: campDe(chaine(d, "joueur"), pour),
          objets: 1,
        },
      ];
      if (prises > 0) {
        moments.push({
          ...base,
          cle: cle("recompense"),
          genre: "recompense",
          // Les récompenses ne sont pas sur le Pokémon tombé : elles viennent de la ligne de
          // récompenses de celui qui les prend. Pas de carte cible, donc.
          cible: null,
          // `par` et non `joueur` : la récompense profite à l'ADVERSAIRE du K.O. Teinter du camp
          // du perdant aurait dit le contraire de ce qui se passe.
          camp: campDe(chaine(d, "par"), pour),
          objets: bornerObjets(prises),
        });
      }
      return moments;
    }

    case "mise_en_place_revelee": {
      const joueurs = Array.isArray(d.joueurs) ? d.joueurs : [];
      // Le nombre de récompenses alignées, lu sur le premier joueur annoncé (R-4.3 : les deux en
      // posent autant). Absent → une, plutôt qu'une supposition sur le format de partie.
      const premier = joueurs[0];
      const nb =
        premier && typeof premier === "object"
          ? (entier(premier as Record<string, unknown>, "recompenses_nombre") ?? 1)
          : 1;
      return [
        {
          ...base,
          cle: cle("mise-en-place"),
          genre: "mise-en-place",
          cible: null,
          // La révélation est **simultanée** (R-4.2/R-4.3) : elle n'appartient à personne. C'est
          // exactement ce que `auto` veut dire, et c'est ce qui en fait un moment partagé.
          camp: "auto",
          objets: bornerObjets(nb),
        },
      ];
    }

    case "main_revelee": {
      const cartes = Array.isArray(d.cartes) ? d.cartes : [];
      return [
        {
          ...base,
          cle: cle("mulligan"),
          genre: "mulligan",
          cible: null,
          camp: campDe(chaine(d, "joueur"), pour),
          objets: bornerObjets(cartes.length),
        },
      ];
    }

    case "dsl_pile_ou_face": {
      const pieces = entier(d, "pieces") ?? 0;
      // Zéro pièce lancée : il n'y a rien à montrer, et une pièce fantôme laisserait croire à un
      // lancer qui n'a pas eu lieu.
      if (pieces < 1) return [];
      const faces = Math.min(Math.max(0, entier(d, "faces") ?? 0), pieces);
      return [
        {
          ...base,
          cle: cle("piece"),
          genre: "piece",
          cible: null,
          camp: campDe(chaine(d, "joueur"), pour),
          objets: bornerObjets(pieces),
          piece: { pieces: bornerObjets(pieces), faces: Math.min(faces, bornerObjets(pieces)) },
        },
      ];
    }

    case "confusion_resolue": {
      // R-11.5 : une pièce, et une seule. `attaque_annulee` vaut pile — donc zéro face.
      const annulee = d.attaque_annulee === true;
      return [
        {
          ...base,
          cle: cle("piece"),
          genre: "piece",
          cible: chaine(d, "pokemon") ?? null,
          camp: campDe(chaine(d, "joueur"), pour),
          objets: 1,
          piece: { pieces: 1, faces: annulee ? 0 : 1 },
        },
      ];
    }

    default:
      return [];
  }
}

/** Les moments d'un coup, dans l'ordre de ses événements. */
export function planifierMomentsCoup(coup: CoupAnimation, pour: string): MomentPlanifie[] {
  return (coup.evenements ?? []).flatMap((brut, rang) =>
    momentsEvenement((brut ?? {}) as EvenementAnimation, coup.numero, rang, pour),
  );
}

/** Les moments d'une suite de coups, rangés par numéro croissant. */
export function planifierMoments(coups: CoupAnimation[], pour: string): MomentPlanifie[] {
  return [...coups]
    .sort((a, b) => a.numero - b.numero)
    .flatMap((coup) => planifierMomentsCoup(coup, pour));
}

/** Un temps du moment, **calculé** : où il commence, combien il dure. */
export type PhaseCalculee = {
  /** Nom du temps (`data-phase`). */
  nom: string;
  /** Les couches de ce temps. */
  couches: CoucheMoment[];
  /** Le geste de ce temps. */
  geste: GesteMoment;
  /** Début du temps, en millisecondes depuis le début du moment. */
  debut: number;
  /** Durée du temps, en millisecondes. */
  duree: number;
};

/**
 * Un objet qui voyage dans le moment : une carte, une pièce.
 *
 * `face` n'existe que pour le pile ou face, et il n'est **pas** lu avant {@link
 * EffetMoment.revelationA} — voir là-bas pourquoi c'est tout l'enjeu du critère n°3.
 */
export type ObjetMoment = {
  /** Rang de l'objet (0, 1, 2…) : il fixe sa place à l'écran. */
  index: number;
  /** Retard de départ, en millisecondes : c'est lui qui fait **deux** cartes et non une. */
  retard: number;
  /** Pour une pièce : `true` si elle s'arrête sur face. `null` pour tout autre objet. */
  face: boolean | null;
};

/** Tout ce qu'il faut pour dessiner un moment — auto-porté, comme un `EffetAttaque`. */
export type EffetMoment = {
  /** Le genre joué. */
  genre: GenreMoment;
  /** La clé du moment : elle relance les images-clés CSS à chaque nouveau moment. */
  cle: string;
  /** Le mot qui coiffe le moment. */
  libelle: string;
  /** `false` = **version réduite** : rien ne bouge, le moment se lit. */
  anime: boolean;
  /** Les temps calculés, dans l'ordre (vide en version réduite). */
  phases: PhaseCalculee[];
  /** Les objets qui voyagent (vide en version réduite). */
  objets: ObjetMoment[];
  /** `instance_id` de la carte concernée, ou `null`. */
  cible: string | null;
  /** Camp concerné, pour la teinte. */
  camp: CampAnimation;
  /** `true` si le plateau tremble (jamais en version réduite). */
  secousse: boolean;
  /** Durée totale du moment, en millisecondes — **toujours** ≤ {@link MOMENT_MAX_MS}. */
  duree: number;
  /**
   * Le moment, en millisecondes, où le **résultat** devient visible — et `0` quand il n'y a pas de
   * résultat à cacher (cinq genres sur six).
   *
   * C'est le critère d'acceptation n°3, rendu mesurable : « le pile ou face ne donne jamais une
   * impression de résultat prédéterminé côté client ». Deux faits le tiennent, et tous deux sont
   * testés :
   *
   * - **la rotation ne sait rien du résultat.** Le nombre d'objets, leurs retards, les phases et
   *   leurs durées sont calculés *sans jamais lire* `faces` : deux lancers opposés produisent donc
   *   un effet identique au champ {@link ObjetMoment.face} près. Un joueur qui observerait la
   *   vitesse, le sens ou la durée de la rotation n'en tirerait **rien** ;
   * - **le résultat n'arrive qu'à la fin** : `revelationA` vaut la fin du temps `rotation`, donc
   *   strictement plus que zéro. Le CSS ne pose la pose finale qu'à partir de là.
   *
   * Et le fait le plus important est ailleurs, en amont : **aucun tirage n'a lieu ici**. Pas un
   * `Math.random`, pas une graine — le résultat vient du serveur, qui fait autorité, et l'animation
   * ne fait que s'arrêter dessus. Une garde statique le vérifie sur la source du module.
   */
  revelationA: number;
  /** La phrase complète : version réduite affichée, et étiquette d'accessibilité. */
  phrase: string;
  /** Le texte court du badge réduit. */
  badge: string;
};

/**
 * Le facteur de compression d'un moment, selon le nombre de moments qui attendent derrière.
 *
 * Une rafale — double K.O. avec récompenses, reprise après coupure — ne doit pas se transformer en
 * film de cinq secondes. Mais elle ne doit pas non plus **perdre** un moment : on accélère, borné
 * par {@link COMPRESSION_MIN}, et tout se joue quand même. C'est la différence avec le rattrapage du
 * socle, qui *résume* : ici les moments sont déjà peu nombreux et chacun compte.
 */
export function facteurCompression(enAttente: number): number {
  if (!Number.isFinite(enAttente) || enAttente <= COMPRESSION_SEUIL) return 1;
  return Math.max(COMPRESSION_MIN, COMPRESSION_SEUIL / enAttente);
}

/** Le mot du camp, pour les phrases (jamais une couleur seule). */
const MOTS_CAMP: Record<CampAnimation, string> = {
  moi: "toi",
  adversaire: "l'adversaire",
  auto: "les deux joueurs",
};

/**
 * La phrase que dit un moment — c'est **toute** l'information de la version réduite.
 *
 * Elle doit se lire sans connaître les règles : « K.O. ! Le Pokémon de l'adversaire est mis K.O. et
 * rejoint la défausse. » Chaque phrase nomme le fait, et le compte quand il y en a un (deux
 * récompenses, sept cartes, une face sur deux) — parce que c'est précisément le compte qui
 * disparaîtrait si on coupait les animations.
 */
export function phraseMoment(m: MomentPlanifie): string {
  const qui = MOTS_CAMP[m.camp];
  switch (m.genre) {
    case "evolution":
      return m.detail
        ? `Évolution : ${qui} fait évoluer un Pokémon en ${m.detail} — la carte se pose sur la précédente.`
        : `Évolution : ${qui} fait évoluer un Pokémon — la carte se pose sur la précédente.`;
    case "ko":
      return `K.O. : le Pokémon de ${qui} tombe et rejoint la défausse.`;
    case "recompense":
      return `Récompense : ${qui} prend ${m.objets} carte${m.objets > 1 ? "s" : ""} récompense${
        m.objets > 1 ? "s" : ""
      }.`;
    case "mise-en-place":
      return `Mise en place : les placements sont dévoilés en même temps et ${m.objets} récompense${
        m.objets > 1 ? "s sont posées" : " est posée"
      } de chaque côté.`;
    case "mulligan":
      return `Reprise : la main de ${qui} (${m.objets} carte${
        m.objets > 1 ? "s" : ""
      }) est révélée puis remélangée.`;
    case "piece": {
      const p = m.piece;
      if (!p) return "Pile ou face.";
      return `Pile ou face : ${p.faces} face${p.faces > 1 ? "s" : ""} sur ${p.pieces}.`;
    }
    default:
      return "";
  }
}

/** Le texte court du badge réduit : le fait, et son compte. */
export function badgeMoment(m: MomentPlanifie): string {
  switch (m.genre) {
    case "evolution":
      return "Évolution";
    case "ko":
      return "K.O.";
    case "recompense":
      return `+${m.objets} récompense${m.objets > 1 ? "s" : ""}`;
    case "mise-en-place":
      return "En place";
    case "mulligan":
      return `Reprise ${m.objets}`;
    case "piece":
      return m.piece ? `${m.piece.faces}/${m.piece.pieces} face${m.piece.faces > 1 ? "s" : ""}` : "Pièce";
    default:
      return "";
  }
}

/** Ce qu'il faut savoir en plus du moment pour le dimensionner. */
export type OptionsMoment = {
  /** `true` → **version réduite** : rien ne bouge (réglage système ou réglage du jeu). */
  reduit?: boolean;
  /** Nombre de moments qui attendent derrière, pour la compression. */
  enAttente?: number;
};

/**
 * Découpe une durée totale entre les phases d'un genre, au prorata de leurs poids.
 *
 * Le dernier temps absorbe l'arrondi : la somme des phases vaut **exactement** la durée totale,
 * sinon le moment finirait une poignée de millisecondes avant ou après sa minuterie, et le CSS
 * laisserait voir un sursaut à chaque fois.
 */
function decouper(phases: PhaseMoment[], total: number): PhaseCalculee[] {
  const somme = phases.reduce((s, p) => s + Math.max(0, p.poids), 0) || 1;
  const calculees: PhaseCalculee[] = [];
  let debut = 0;
  phases.forEach((p, i) => {
    const dernier = i === phases.length - 1;
    const duree = dernier
      ? Math.max(0, total - debut)
      : Math.round((total * Math.max(0, p.poids)) / somme);
    calculees.push({ nom: p.nom, couches: p.couches, geste: p.geste, debut, duree });
    debut += duree;
  });
  return calculees;
}

/**
 * L'effet d'un moment, prêt à dessiner.
 *
 * La **version réduite** (`reduit: true`) n'est pas « la même chose en plus court » : c'est un objet
 * sans aucune phase, sans aucun objet qui voyage, dont toute la charge d'information est dans
 * {@link EffetMoment.phrase} et {@link EffetMoment.badge}. Elle existe pour les six genres, et un
 * test le vérifie genre par genre — « animations réduites » ne doit jamais vouloir dire « tu ne
 * sauras pas ce qui vient de se passer ».
 *
 * Contrairement à `effetAttaque`, la durée ne vient **pas** du socle : elle vient de la table, parce
 * que ces six moments ont leur propre tempo (le socle borne tout à 900 ms, et il n'accorde même
 * rien du tout à `main_revelee`, absent de son registre). Elle reste bornée à
 * {@link MOMENT_MAX_MS}, compression comprise.
 */
export function effetMoment(m: MomentPlanifie, options: OptionsMoment = {}): EffetMoment {
  const spec = MOMENTS[m.genre];
  const commun = {
    genre: m.genre,
    cle: m.cle,
    libelle: spec.libelle,
    cible: m.cible,
    camp: m.camp,
    phrase: phraseMoment(m),
    badge: badgeMoment(m),
  };

  if (options.reduit) {
    return {
      ...commun,
      anime: false,
      phases: [],
      objets: [],
      secousse: false,
      duree: DUREE_REDUITE_MOMENT,
      // Rien ne tourne : il n'y a aucun résultat à cacher, et prétendre le contraire ferait croire
      // à une révélation différée qui n'existe pas.
      revelationA: 0,
    };
  }

  const duree = Math.min(
    MOMENT_MAX_MS,
    Math.max(1, Math.round(spec.duree * facteurCompression(options.enAttente ?? 0))),
  );
  const phases = decouper(spec.phases, duree);

  // Le retard entre deux objets se rabote pour que le dernier parti ait encore sa phase entière à
  // l'écran : sans ça, deux récompenses sur un moment comprimé verraient la seconde coupée net.
  const nombre = spec.echelonne ? Math.max(1, m.objets) : 1;
  const premiere = phases[0]?.duree ?? duree;
  const decalage = nombre <= 1 ? 0 : Math.min(DECALAGE_OBJET, Math.floor(premiere / nombre));
  const objets: ObjetMoment[] = Array.from({ length: nombre }, (_, index) => ({
    index,
    retard: index * decalage,
    // ⚠️ `face` est la SEULE valeur de cet objet qui dépende du résultat. Tout le reste — combien
    // d'objets, quel retard, quelles phases, quelle durée — est calculé sans l'avoir lu. C'est ce
    // qui rend le lancer honnête, et c'est testé en comparant deux lancers opposés.
    face: m.piece ? index < m.piece.faces : null,
  }));

  // La révélation tombe à la fin du temps `rotation`, et nulle part ailleurs. Un genre sans
  // rotation n'a pas de résultat à cacher : zéro.
  const rotation = phases.find((p) => p.nom === "rotation");
  const revelationA = rotation ? rotation.debut + rotation.duree : 0;

  return {
    ...commun,
    anime: true,
    phases,
    objets,
    secousse: spec.secousse,
    duree,
    revelationA,
  };
}

/**
 * L'état de la file de moments : **au plus un** moment en cours, le reste en attente.
 *
 * Sérialisable de bout en bout (aucune fonction, aucune référence DOM) : elle se teste par milliers
 * de cas sans navigateur, exactement comme le socle et comme le moteur.
 */
export type FileMoments = {
  /** Les moments à jouer, dans l'ordre. */
  attente: MomentPlanifie[];
  /** Le moment en cours — **au plus un**. C'est l'invariant du critère d'acceptation n°1. */
  courant: MomentPlanifie | null;
  /**
   * Combien de moments attendaient **à l'instant où le courant a été tiré**.
   *
   * C'est lui, et non la longueur courante de l'attente, qui dose la compression
   * ({@link facteurCompression}). La nuance n'est pas théorique : l'attente diminue pendant que le
   * moment se joue, donc s'en servir directement ferait **recalculer la durée en cours de route**,
   * et l'écran redémarrerait l'animation à chaque arrivée de coup. Figé à la prise, le tempo d'un
   * moment ne change plus une fois qu'il a commencé.
   */
  retard: number;
  /** Clés déjà passées : une resynchronisation qui recouvre ne rejoue pas ce qui a été vu. */
  vues: string[];
};

/** Une file de moments vide. */
export const FILE_MOMENTS_VIDE: FileMoments = {
  attente: [],
  courant: null,
  retard: 0,
  vues: [],
};

/**
 * Ce qu'on peut demander à la file de moments.
 *
 * - `empiler` : de nouveaux moments arrivent (un coup diffusé, ou une resync) ;
 * - `avancer` : le moment en cours est fini (minuterie) **ou** le joueur l'a passé ;
 * - `vider` : on jette tout (le joueur agit, l'onglet passe en arrière-plan) ;
 * - `reinitialiser` : changement de partie — mémoire comprise.
 */
export type ActionMoments =
  | { type: "empiler"; moments: MomentPlanifie[] }
  | { type: "avancer" }
  | { type: "vider" }
  | { type: "reinitialiser" };

/** Mémorise des clés vues, en bornant la mémoire (une partie longue ne doit pas enfler). */
function memoriser(vues: string[], cles: string[]): string[] {
  const fusion = [...vues, ...cles];
  return fusion.length > MEMOIRE_CLES ? fusion.slice(fusion.length - MEMOIRE_CLES) : fusion;
}

/**
 * Prend la tête de l'attente comme nouveau moment courant (ou `null` si plus rien), et **fige** le
 * retard qui dosera sa compression — voir {@link FileMoments.retard}.
 */
function tirer(file: FileMoments): FileMoments {
  const attente = [...file.attente];
  const suivant = attente.shift() ?? null;
  return { ...file, attente, courant: suivant, retard: attente.length };
}

/**
 * Le réducteur de la file de moments — **pur** : même entrée, même sortie, aucun effet de bord.
 *
 * Il ne **résume** jamais et ne jette jamais un moment en attente : un double K.O. produit quatre
 * moments, et les quatre se jouent. Ce que la file fait quand elle est en retard, c'est accélérer
 * ({@link facteurCompression}) — jamais effacer. C'est la différence de nature avec le rattrapage du
 * socle, qui a vingt pastilles à condenser là où la file de moments en a quatre à faire voir.
 */
export function reduireMoments(file: FileMoments, action: ActionMoments): FileMoments {
  switch (action.type) {
    case "reinitialiser":
      return FILE_MOMENTS_VIDE;

    case "vider":
      // On mémorise ce qu'on jette : une resync ultérieure ne doit pas le rejouer.
      return {
        attente: [],
        courant: null,
        retard: 0,
        vues: memoriser(
          file.vues,
          [file.courant, ...file.attente].filter((m): m is MomentPlanifie => !!m).map((m) => m.cle),
        ),
      };

    case "empiler": {
      const connues = new Set([
        ...file.vues,
        ...file.attente.map((m) => m.cle),
        ...(file.courant ? [file.courant.cle] : []),
      ]);
      const nouveaux = action.moments.filter((m) => !connues.has(m.cle));
      if (nouveaux.length === 0) return file;
      const avec: FileMoments = { ...file, attente: [...file.attente, ...nouveaux] };
      return file.courant ? avec : tirer(avec);
    }

    case "avancer": {
      if (!file.courant) return file;
      return tirer({ ...file, vues: memoriser(file.vues, [file.courant.cle]) });
    }

    default:
      return file;
  }
}

/** Les six genres, dans l'ordre de la table — pour la galerie de recette et les tests exhaustifs. */
export const GENRES_MOMENT: readonly GenreMoment[] = Object.keys(MOMENTS) as GenreMoment[];

/** Toutes les couches utilisées par au moins un genre — ce que le CSS doit savoir dessiner. */
export const COUCHES_UTILISEES: readonly CoucheMoment[] = Array.from(
  new Set(GENRES_MOMENT.flatMap((g) => MOMENTS[g].phases.flatMap((p) => p.couches))),
);

/** Tous les gestes utilisés par au moins un genre, hors `aucun`. */
export const GESTES_UTILISES: readonly GesteMoment[] = Array.from(
  new Set(GENRES_MOMENT.flatMap((g) => MOMENTS[g].phases.map((p) => p.geste))),
).filter((g) => g !== "aucun");
