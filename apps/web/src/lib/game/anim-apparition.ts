/**
 * L'apparition du Pokémon au-dessus de sa carte — le « bel effet » du jalon J3 (décision DJ3).
 *
 * DJ3, tranchée par JF le 15/10/2026 : *« l'apparition est fabriquée à partir de l'illustration de
 * la carte elle-même (découpe du Pokémon par segmentation, détourage, mise en volume, particules) :
 * aucune image nouvelle n'est introduite, ni sprite ni modèle officiel. »* Côté serveur, la découpe
 * est produite hors ligne (`apps/api/src/pbm_api/jeu/decoupe.py`) et son URL arrive dans
 * `VueRenduCarte.apparition`. Ici on ne fait que la **mettre en scène**.
 *
 * ## Le module est pur, et c'est ce qui le rend testable
 *
 * Comme `anim-types.ts` et `anim-moments.ts` : aucune référence au DOM, à React ou au temps. Une
 * entrée (l'animation en cours, l'URL de la découpe) donne une sortie sérialisable, que le
 * composant se contente de poser en variables CSS.
 *
 * ## Trois moments, et seulement trois
 *
 * La fiche du lot les nomme : **la pose**, **l'évolution**, **l'attaque**. Rien d'autre ne
 * déclenche d'apparition — pas parce que ce serait difficile, mais parce qu'un Pokémon qui jaillit
 * à chaque énergie attachée cesserait d'être un événement.
 *
 * ⛔ **Jamais pendant la mise en place.** Les poses du début de partie passent par
 * `mise_en_place_revelee`, pas par `pokemon_pose` : six apparitions d'affilée feraient de la
 * première impression une bousculade, et surtout chaque découpe pèse jusqu'à 40 Kio — le budget de
 * mise en place (432 Kio, 2,2 s en 4G, `docs/jeu/ASSETS.md`) ne les supporterait pas. C'est aussi
 * pour cela que le budget serveur ne compte **qu'une** apparition par partie : une à la fois.
 *
 * ## La parallaxe, sans modèle 3D
 *
 * « Mise en volume » ne veut pas dire 3D. On empile quatre calques qui partagent la **même** image
 * et se déplacent d'amplitudes différentes : le fond bouge peu, le sujet bouge beaucoup, et l'œil
 * lit du relief. C'est la plus ancienne astuce du dessin animé, et elle coûte quatre `transform`
 * composés par le compositeur — donc rien sur le fil principal.
 *
 * ⚠️ Le flou et la teinte des calques arrière sont posés en CSS **statique** (`mask-image`,
 * `opacity` fixe), jamais animés : la garde `anim-css-garde.test.ts` n'autorise que `transform` et
 * `opacity` dans une image-clé, et c'est elle qui tient le plancher de 30 images/s.
 *
 * ## La dégradation est le cas courant, pas l'exception
 *
 * Onze cartes ont une découpe ; le catalogue en compte plus de vingt-deux mille. `apparitionDe`
 * rend donc `null` la plupart du temps, et ce `null` ne laisse aucun trou : l'effet de type
 * générique (`anim-types.ts`) joue exactement comme avant, et le journal porte la même phrase. Une
 * carte sans découpe n'affiche aucun message, aucun cadre vide, aucune icône « image manquante ».
 */

import type { Animation } from "@/lib/game/animations";
import { SPECS, type Typage, intensiteDe } from "@/lib/game/anim-types";

/** Les trois moments qui méritent une apparition. */
export type MotifApparition = "pose" | "evolution" | "attaque";

/**
 * Les quatre calques empilés, du fond vers l'avant. Chacun a son image-clé
 * `pbm-anim-fx-a-<calque>` dans `globals.css`, et la parité est tenue par un test.
 */
export type CalqueApparition = "halo" | "echo" | "sujet" | "particules";

/** L'ordre d'empilement : le premier est au fond. Changer cet ordre change le rendu. */
export const CALQUES: readonly CalqueApparition[] = ["halo", "echo", "sujet", "particules"];

/**
 * Quel type d'événement moteur donne quel motif. Table, pas cascade de `if` : ajouter un moment,
 * c'est ajouter une ligne — et `mise_en_place_revelee` en est **volontairement** absent.
 */
export const MOTIFS: Record<string, MotifApparition> = {
  pokemon_pose: "pose",
  evolution: "evolution",
  attaque_declaree: "attaque",
};

/** Durée totale de chaque motif, en millisecondes, avant bornage. */
export const DUREES: Record<MotifApparition, number> = {
  pose: 760,
  evolution: 900,
  attaque: 820,
};

/**
 * Plafond absolu, repris de `anim-types.ts` et pour la même raison : au-delà d'une seconde,
 * l'effet ne raconte plus un coup, il masque le plateau au moment où on veut le lire.
 */
export const TOTAL_MAX_MS = 1000;

/** Amplitude de la dérive du calque le plus en avant, en pourcentage de la largeur de la carte. */
export const AMPLITUDE_BASE = 9;

/** Hauteur dont le sujet s'élève au-dessus de la carte, en pourcentage de la hauteur de la carte. */
export const ELEVATION_BASE = 34;

/**
 * Nombre maximal de particules, quel que soit le type.
 *
 * **Sept, et pas huit.** La première version en mettait huit : avec les quatre calques, cela
 * faisait douze nœuds animés en même temps, soit un de plus que l'effet typé le plus lourd
 * (`fairy`, coût 11) — celui sur lequel le plancher de 30 images/s a été mesuré au navigateur. Le
 * test de coût l'a refusé. La réponse n'a pas été de relever le plafond, qui n'est pas un réglage
 * mais le résultat d'une mesure : c'est l'apparition qui s'y plie. On ne voit pas la différence
 * entre sept et huit particules ; on verrait un plateau qui saccade.
 */
export const PARTICULES_MAX = 7;

/**
 * Profondeur de chaque calque, de 0 (au fond, presque immobile) à 1 (devant, pleine amplitude).
 * C'est **la** donnée de la parallaxe : tout le reste en découle.
 */
export const PROFONDEURS: Record<CalqueApparition, number> = {
  halo: 0.15,
  echo: 0.45,
  sujet: 1,
  particules: 0.75,
};

/** Un calque prêt à poser : son nom, sa profondeur, son amplitude et son retard. */
export type CalqueCalcule = {
  calque: CalqueApparition;
  profondeur: number;
  /** Déplacement latéral, en pourcentage de la largeur de la carte. */
  amplitude: number;
  /** Élévation, en pourcentage de la hauteur de la carte. */
  elevation: number;
  /** Décalage de départ en ms : les calques arrière partent les premiers, c'est ce qui fait le relief. */
  retard: number;
};

/** Une particule : son angle de départ et son retard, le CSS fait le reste. */
export type ParticuleApparition = { index: number; angle: number; retard: number };

/** Ce que le socle d'animation dit à l'apparition : quel moment, sur quelle carte, avec quelle force. */
export type SignalApparition = {
  motif: MotifApparition;
  cible: string;
  cle: string;
  /** 0 à 1. Pour une attaque, l'intensité réelle du coup ; sinon la valeur nominale du motif. */
  intensite: number;
  /** Le type de l'attaque, quand il y en a un : il décide de la teinte et des particules. */
  type: string | null;
};

/** L'apparition complète, telle que le composant la pose. */
export type Apparition = {
  cle: string;
  motif: MotifApparition;
  /** L'URL de la découpe — jamais vide : sans elle, `apparitionDe` rend `null`. */
  url: string;
  cible: string;
  type: string | null;
  intensite: number;
  duree: number;
  calques: CalqueCalcule[];
  particules: ParticuleApparition[];
  /** Ce que le journal dirait — porté en `aria-label`, pour que l'effet ne soit pas muet. */
  phrase: string;
};

/** Intensité nominale d'un motif qui n'est pas une attaque : une pose est calme, une évolution non. */
const INTENSITE_MOTIF: Record<MotifApparition, number> = {
  pose: 0.45,
  evolution: 0.8,
  attaque: 0.6,
};

/** Borne une durée dans `[0, TOTAL_MAX_MS]`. */
function borner(duree: number): number {
  if (!Number.isFinite(duree) || duree <= 0) return 0;
  return Math.min(Math.round(duree), TOTAL_MAX_MS);
}

/**
 * Le signal d'apparition porté par l'animation en cours, ou `null`.
 *
 * Lit l'`Animation` du socle plutôt que l'effet typé : c'est elle qui porte les trois types
 * d'événement d'un coup, et elle est déjà filtrée, ordonnée et rattrapée par la file. Une animation
 * de **résumé** (rattrapage après coupure) n'en produit jamais : elle représente plusieurs coups à
 * la fois, et faire surgir un Pokémon pour « 18 coups rejoués » n'aurait aucun sens.
 */
export function signalApparition(animation: Animation | null): SignalApparition | null {
  if (!animation || animation.resume || !animation.cible) return null;
  const motif = MOTIFS[animation.type];
  if (!motif) return null;
  const typage: Typage | null = animation.typage;
  const intensite =
    motif === "attaque" && typage ? intensiteDe(typage) : INTENSITE_MOTIF[motif];
  return {
    motif,
    cible: animation.cible,
    cle: `${animation.cle}:apparition`,
    intensite: Math.max(0, Math.min(1, intensite)),
    type: typage?.type ?? null,
  };
}

/**
 * Ce que l'apparition raconte, en une phrase.
 *
 * ⚠️ Elle ne part **pas** en `aria-label` sur le plateau : la couche d'animation y est
 * `aria-hidden` et c'est le journal de partie qui porte le texte (`docs/jeu/ANIMATIONS.md`) —
 * doubler l'annonce ferait entendre deux fois le même coup. Elle sert à la galerie `/jeu/effets`,
 * où il n'y a pas de journal, et aux tests.
 */
export function phraseApparition(motif: MotifApparition): string {
  if (motif === "pose") return "Le Pokémon apparaît au-dessus de sa carte.";
  if (motif === "evolution") return "Le Pokémon évolué surgit au-dessus de sa carte.";
  return "Le Pokémon s'élance au-dessus de sa carte pour attaquer.";
}

/**
 * Compose l'apparition d'une carte, ou `null` s'il n'y a rien à jouer.
 *
 * Rend `null` — et c'est le cas **courant**, pas une erreur — quand : il n'y a pas de signal, le
 * signal ne vise pas cette carte, la carte n'a pas de découpe publiée, ou les animations sont
 * réduites. Dans tous ces cas l'écran ne montre rien de particulier et l'effet de type joue seul.
 *
 * @param signal ce que le socle d'animation raconte, ou `null`
 * @param cible l'`instance_id` de la carte qui demande son apparition
 * @param url l'URL de la découpe (`VueRenduCarte.apparition`), absente pour la quasi-totalité du catalogue
 * @param reduit vrai si le joueur ou son système demande des animations réduites
 */
export function apparitionDe(
  signal: SignalApparition | null,
  cible: string,
  url: string | null | undefined,
  { reduit = false }: { reduit?: boolean } = {},
): Apparition | null {
  if (!signal || !url || reduit) return null;
  if (signal.cible !== cible) return null;

  const duree = borner(DUREES[signal.motif]);
  if (duree === 0) return null;

  const spec = signal.type ? SPECS[signal.type] : undefined;
  // L'intensité module l'amplitude, jamais la durée : un coup faible doit se voir aussi longtemps
  // qu'un coup fort, sinon il passerait inaperçu — il doit seulement se voir moins fort.
  const facteur = 0.55 + 0.45 * signal.intensite;

  const calques: CalqueCalcule[] = CALQUES.map((calque) => {
    const profondeur = PROFONDEURS[calque];
    return {
      calque,
      profondeur,
      amplitude: Math.round(AMPLITUDE_BASE * profondeur * facteur * 10) / 10,
      elevation: Math.round(ELEVATION_BASE * profondeur * facteur * 10) / 10,
      // Les calques du fond démarrent les premiers : c'est ce décalage, et pas l'échelle, qui
      // donne la sensation que le sujet se détache de la carte.
      retard: Math.round((1 - profondeur) * duree * 0.12),
    };
  });

  const nombre = Math.min(
    PARTICULES_MAX,
    Math.round((spec?.particules ?? 0) * signal.intensite),
  );
  const particules: ParticuleApparition[] = Array.from({ length: nombre }, (_, index) => ({
    index,
    // Réparties sur un demi-tour vers le haut : les particules montent avec le Pokémon, elles ne
    // tombent pas sous la carte où elles seraient cachées par le plateau.
    angle: Math.round(-150 + (index * 120) / Math.max(1, nombre - 1)),
    retard: Math.round((index * duree * 0.3) / Math.max(1, nombre)),
  }));

  return {
    cle: signal.cle,
    motif: signal.motif,
    url,
    cible,
    type: signal.type,
    intensite: signal.intensite,
    duree,
    calques,
    particules,
    phrase: phraseApparition(signal.motif),
  };
}

/** Les calques réellement utilisés — lu par la garde de parité table ↔ CSS. */
export const CALQUES_UTILISES: readonly CalqueApparition[] = CALQUES;

/**
 * Le nombre de nœuds animés en même temps par une apparition — sa part du travail par image.
 *
 * Même rôle que `coutVisuel` dans `anim-types.ts`, et même raison d'exister : le plancher de 30
 * images/s sur l'appareil de référence (fenêtre 844×390, processeur bridé ×4) tient *parce que* le
 * nombre d'éléments en mouvement est borné. L'e2e `anim-fluidite.spec.ts` mesure le résultat au
 * navigateur ; cette fonction permet de refuser une dérive **avant** d'en arriver là, en CI, sans
 * dépendre d'une mesure de temps forcément bruitée.
 */
export function coutVisuel(apparition: Apparition): number {
  return apparition.calques.length + apparition.particules.length;
}

/**
 * Le coût de l'apparition la plus lourde qu'on puisse déclencher, toutes intensités confondues.
 *
 * Calculé, jamais recopié : ajouter un calque ou relever `PARTICULES_MAX` le fait bouger tout seul,
 * et le test qui le borne devient rouge. Un chiffre écrit à la main aurait continué d'affirmer
 * l'ancienne valeur.
 */
export const COUT_LE_PLUS_LOURD: number = CALQUES.length + PARTICULES_MAX;
