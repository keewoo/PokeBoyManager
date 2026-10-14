"use client";

import {
  type CSSProperties,
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";

import { EffetMomentCle } from "@/components/game/effet-moment";
import { EffetTypeAttaque } from "@/components/game/effet-type";
import { useConfort } from "@/lib/confort-provider";
import {
  FILE_MOMENTS_VIDE,
  type EffetMoment,
  effetMoment,
  planifierMoments,
  reduireMoments,
} from "@/lib/game/anim-moments";
import { type EffetAttaque, effetAttaque } from "@/lib/game/anim-types";
import { ANIMATIONS_REDUITES } from "@/lib/game/confort";
import {
  FILE_VIDE,
  type Animation,
  type CoupAnimation,
  type ModeAnimation,
  dureeEffective,
  planifier,
  reduireFile,
} from "@/lib/game/animations";

/**
 * Le branchement du socle d'animation sur l'écran (lot `j-anim-socle`) : le crochet qui fait
 * avancer la file, et la couche qui la dessine.
 *
 * Tout ce qui décide vit dans `lib/game/animations.ts` (pur, testé sans navigateur). Ici il ne
 * reste que trois choses, et chacune répond à une exigence du lot :
 *
 * - **le temps** : une animation se termine par un `setTimeout` de sa durée, jamais par une boucle
 *   `requestAnimationFrame`. C'est ce qui permet de tenir le plancher d'images par seconde — React
 *   ne rend qu'**une fois par animation** (deux ou trois rendus par seconde), l'écran étant animé
 *   par le CSS, sur le compositeur. Une boucle par cadre aurait fait rendre tout le plateau
 *   soixante fois par seconde, et ç'aurait été le socle lui-même qui aurait mangé les images ;
 * - **l'arrière-plan** : à `visibilitychange`, la file se **vide**. Le risque nommé par le lot est
 *   exactement là : si l'état affiché dépendait de la fin d'une animation, un onglet mis de côté
 *   figerait le plateau dans un état faux. Ici il ne dépend de rien — on jette, et le plateau
 *   reste celui du serveur ;
 * - **`prefers-reduced-motion`** : le réglage système passe la file en mode réduit, où les durées
 *   sont nulles et où **aucun** effet n'est rendu. La file se vide quand même, un coup après
 *   l'autre : rien ne disparaît, rien ne bloque.
 *
 * Le lot `j-accessibilite-jeu` y ajoute les deux façons de **couper** une animation, et elles sont
 * complémentaires : *globalement* par le réglage du jeu (`/jeu/confort`, qui s'ajoute au réglage
 * système — l'un des deux suffit), et *individuellement* par le bouton « Passer », qui saute
 * l'animation en cours sans toucher aux suivantes ni à aucun réglage.
 */

/**
 * `true` si les animations doivent être **réduites** — par le système, ou par le réglage du jeu.
 *
 * Les deux s'additionnent, ils ne se contredisent pas : `prefers-reduced-motion` est une demande
 * d'accessibilité du système, `/jeu/confort` (lot `j-accessibilite-jeu`) existe parce que tout le
 * monde ne sait pas où ce réglage se trouve dans un téléphone. L'un des deux suffit à tout arrêter.
 *
 * Extrait en crochet pour que la galerie d'effets (`/jeu/effets`) et le plateau répondent
 * **exactement** la même chose : deux lectures séparées auraient fini par divergir, et la galerie
 * aurait montré à JF des animations que son plateau ne joue pas.
 */
export function useAnimationsReduites(): boolean {
  const [systeme, setSysteme] = useState(false);
  const { confort } = useConfort();

  // Lu au montage et suivi s'il change en cours de partie.
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!mq) return;
    const appliquer = () => setSysteme(mq.matches);
    appliquer();
    mq.addEventListener?.("change", appliquer);
    return () => mq.removeEventListener?.("change", appliquer);
  }, []);

  return systeme || confort.animations === ANIMATIONS_REDUITES;
}

/**
 * Un effet d'attaque **typé** en cours, et où le poser (lot `j-anim-attaques-typees`).
 *
 * Il vit sa **propre** durée, indépendante de la file : c'est ce qui permet à la version réduite
 * d'exister. En « animations réduites », la file avance instantanément (toutes les durées valent
 * zéro) — un badge accroché à l'animation courante clignoterait sans être lisible. Celui-ci reste
 * le temps qu'il faut pour être lu, puis disparaît ; et comme l'état affiché ne dépend jamais d'une
 * animation, le faire vivre plus longtemps ne retient rien.
 */
export type EffetTypeeEnCours = {
  /** L'effet à dessiner. */
  effet: EffetAttaque;
  /** La clé de l'animation d'où il vient : elle relance l'animation CSS à chaque nouvel effet. */
  cle: string;
  /** L'`instance_id` de la carte visée, ou `null` (l'attaque n'a touché personne). */
  cible: string | null;
};

/** Ce que {@link useFileAnimations} rend à l'écran de partie. */
export type EtatAnimations = {
  /** L'animation à dessiner, ou `null` (file au repos, ou mode réduit). */
  animation: Animation | null;
  /** Sa durée réelle en millisecondes, mode compris — ce que le CSS doit respecter. */
  duree: number;
  /** Combien d'animations attendent derrière (indicateur, et condition d'affichage du « passer »). */
  enAttente: number;
  /** Le mode courant. */
  mode: ModeAnimation;
  /**
   * `true` si les animations sont réduites — par le **système** (`prefers-reduced-motion`) ou par le
   * réglage du **jeu** (`/jeu/confort`, lot `j-accessibilite-jeu`). L'accélération n'a alors plus de
   * sens : il n'y a plus rien à accélérer.
   */
  reduit: boolean;
  /** Saute l'animation en cours et enchaîne. */
  sauter: () => void;
  /** Jette tout ce qui reste (le joueur agit : l'écran ne doit jamais se mettre en travers). */
  vider: () => void;
  /** Bascule le mode accéléré (sans effet quand le système demande des animations réduites). */
  basculerAccelere: () => void;
  /**
   * L'effet d'attaque **typé** en cours, ou `null` (lot `j-anim-attaques-typees`).
   *
   * Il est présent **aussi en mode réduit**, contrairement à {@link EtatAnimations.animation} : il
   * prend alors sa forme statique, qui dit en texte ce que l'animation aurait montré. Couper les
   * animations ne doit pas vouloir dire ne plus savoir ce qui vient de se passer.
   */
  effetTypee: EffetTypeeEnCours | null;
};

/**
 * Fait vivre la file d'animations d'une partie à partir des coups diffusés par le serveur.
 *
 * Les coups arrivent déjà projetés (`Coup = {numero, evenements}`) : on ne planifie que ceux dont
 * le numéro dépasse le dernier planifié, pour qu'une resynchronisation qui recouvre ne rejoue
 * jamais un film déjà vu. Au premier chargement, la resync livre toute la partie d'un bloc — c'est
 * le cas de reprise, et le rattrapage de la file le résume au lieu de le rejouer.
 *
 * @param coups  les coups diffusés, dans l'ordre (dédupliqués par l'appelant comme ici).
 * @param pour   le destinataire de la vue, pour teinter chaque animation du bon camp.
 * @param cle    identifiant de la partie : il change, la file repart de zéro.
 */
export function useFileAnimations({
  coups,
  pour,
  cle,
}: {
  coups: CoupAnimation[];
  pour: string;
  cle?: string;
}): EtatAnimations {
  const [file, dispatch] = useReducer(reduireFile, FILE_VIDE);
  // Réglage système (`prefers-reduced-motion`) **et** réglage du jeu (`/jeu/confort`) : l'un des
  // deux suffit. Le détail est dans {@link useAnimationsReduites}, partagé avec `/jeu/effets`.
  const reduit = useAnimationsReduites();
  const [accelere, setAccelere] = useState(false);
  const mode: ModeAnimation = reduit ? "reduit" : accelere ? "accelere" : "normal";
  // L'effet d'attaque TYPÉ (lot `j-anim-attaques-typees`), tenu à part de la file parce qu'il vit
  // sa propre durée — voir le commentaire de sa minuterie, plus bas.
  const [effetTypee, setEffetTypee] = useState<EffetTypeeEnCours | null>(null);
  // Dernier numéro de coup déjà planifié : la borne qui évite de replanifier tout l'historique à
  // chaque coup reçu (et de le rejouer quand la mémoire bornée de la file a oublié ses clés).
  const dernierPlanifie = useRef(-1);

  useEffect(() => {
    dispatch({ type: "mode", mode });
  }, [mode]);

  // Changement de partie : file neuve, mémoire comprise.
  useEffect(() => {
    dernierPlanifie.current = -1;
    dispatch({ type: "reinitialiser" });
    setEffetTypee(null);
  }, [cle]);

  // Les coups neufs deviennent des animations. `pour` manquant (vue pas encore chargée) : on
  // attend plutôt que de deviner un camp.
  useEffect(() => {
    if (!pour) return;
    const neufs = coups.filter((c) => c.numero > dernierPlanifie.current);
    if (neufs.length === 0) return;
    dernierPlanifie.current = neufs.reduce((m, c) => Math.max(m, c.numero), dernierPlanifie.current);
    dispatch({ type: "empiler", animations: planifier(neufs, pour) });
  }, [coups, pour]);

  // Le temps : une minuterie par animation, de sa durée exacte. Elle s'annule si l'animation
  // change (saut, vidange, changement de mode) — jamais de minuterie orpheline.
  const courante = file.courante;
  const duree = courante ? dureeEffective(courante, file.mode) : 0;
  useEffect(() => {
    if (!courante) return;
    const minuterie = setTimeout(() => dispatch({ type: "avancer", dt: duree }), duree);
    return () => clearTimeout(minuterie);
  }, [courante, duree]);

  // Une animation typée passe → on pose son effet. Il doit exister **aussi** en mode réduit, où la
  // file avance en zéro milliseconde : un badge accroché à l'animation courante clignoterait sans
  // jamais être lisible.
  useEffect(() => {
    if (!courante?.typage) return;
    const effet = effetAttaque(courante.typage, { duree, reduit });
    // `null` = type inconnu du serveur, ou rien à montrer : on laisse le socle à son effet neutre
    // plutôt que d'inventer une couleur (D9). On ne touche pas non plus à l'effet précédent — il
    // finit de vivre sa durée.
    if (!effet) return;
    setEffetTypee({ effet, cle: courante.cle, cible: courante.cible });
  }, [courante, duree, reduit]);

  // La minuterie de l'effet typé est accrochée à l'EFFET, pas à l'animation : si elle avait vécu
  // dans l'effet ci-dessus, passer à une animation non typée en aurait annulé le nettoyage, et
  // l'effet serait resté collé au plateau pour de bon.
  useEffect(() => {
    if (!effetTypee) return;
    const minuterie = setTimeout(() => setEffetTypee(null), effetTypee.effet.dureeTotale);
    return () => clearTimeout(minuterie);
  }, [effetTypee]);

  const viderTout = useCallback(() => {
    dispatch({ type: "vider" });
    // L'effet typé part avec la file : le joueur agit, ou l'onglet passe en arrière-plan — dans les
    // deux cas l'écran ne doit rien garder d'une attaque qui n'est plus à l'ordre du jour.
    setEffetTypee(null);
  }, []);

  // Onglet mis de côté : on jette la file. L'état affiché ne dépend pas d'elle, il ne bouge pas.
  useEffect(() => {
    const surVisibilite = () => {
      if (document.visibilityState === "hidden") viderTout();
    };
    document.addEventListener("visibilitychange", surVisibilite);
    return () => document.removeEventListener("visibilitychange", surVisibilite);
  }, [viderTout]);

  const sauter = useCallback(() => dispatch({ type: "sauter" }), []);
  const basculerAccelere = useCallback(() => setAccelere((v) => !v), []);

  return {
    // En mode réduit, rien n'est dessiné : la file se vide en silence.
    animation: mode === "reduit" ? null : courante,
    duree,
    enAttente: file.attente.length,
    mode,
    reduit,
    sauter,
    vider: viderTout,
    basculerAccelere,
    effetTypee,
  };
}

/** Ce que {@link useFileMoments} rend à l'écran de partie. */
export type EtatMoments = {
  /** Le moment clé à dessiner, ou `null` (file au repos). */
  moment: EffetMoment | null;
  /** Combien de moments attendent derrière (indicateur, et bouton « passer »). */
  enAttente: number;
  /** Passe le moment en cours et enchaîne sur le suivant. */
  sauter: () => void;
  /** Jette tout ce qui reste (le joueur agit : l'écran ne se met jamais en travers). */
  vider: () => void;
};

/**
 * Fait vivre la file des **moments clés** d'une partie (lot `j-anim-evolution-ko`).
 *
 * Le motif est celui de {@link useFileAnimations}, et les deux files tournent côte à côte sur les
 * mêmes coups. Trois différences, et chacune a sa raison :
 *
 * - elle est alimentée par les **événements**, pas par la file du socle. C'est ce qui évite une
 *   perte silencieuse : le socle enchaîne plusieurs entrées de durée nulle en un seul `avancer`,
 *   donc un événement non animé n'est jamais exposé comme `courante` — un moment accroché à
 *   `courante` aurait disparu sans un mot. Ici, un moment naît de l'événement lui-même ;
 * - elle ne **résume** jamais : un double K.O. joue ses quatre moments, comprimés si besoin
 *   (critère d'acceptation n°1) ;
 * - elle vit **aussi en mode réduit**, où elle prend sa forme immobile. Comme l'effet typé : couper
 *   les animations ne doit pas vouloir dire ne plus savoir ce qui vient de se passer.
 *
 * @param coups  les coups diffusés, dans l'ordre.
 * @param pour   le destinataire de la vue, pour teinter chaque moment du bon camp.
 * @param cle    identifiant de la partie : il change, la file repart de zéro.
 */
export function useFileMoments({
  coups,
  pour,
  cle,
}: {
  coups: CoupAnimation[];
  pour: string;
  cle?: string;
}): EtatMoments {
  const [file, dispatch] = useReducer(reduireMoments, FILE_MOMENTS_VIDE);
  const reduit = useAnimationsReduites();
  // Même borne que le socle : on ne replanifie pas tout l'historique à chaque coup reçu.
  const dernierPlanifie = useRef(-1);

  // Changement de partie : file neuve, mémoire comprise.
  useEffect(() => {
    dernierPlanifie.current = -1;
    dispatch({ type: "reinitialiser" });
  }, [cle]);

  useEffect(() => {
    if (!pour) return;
    const neufs = coups.filter((c) => c.numero > dernierPlanifie.current);
    if (neufs.length === 0) return;
    dernierPlanifie.current = neufs.reduce((m, c) => Math.max(m, c.numero), dernierPlanifie.current);
    dispatch({ type: "empiler", moments: planifierMoments(neufs, pour) });
  }, [coups, pour]);

  const courant = file.courant;
  // `file.retard` est figé à la prise du moment (voir `FileMoments.retard`) : l'effet — donc la
  // minuterie ci-dessous — ne se recalcule qu'au changement de moment, jamais en cours de route.
  const moment = useMemo(
    () => (courant ? effetMoment(courant, { reduit, enAttente: file.retard }) : null),
    [courant, reduit, file.retard],
  );

  // Le temps : une minuterie par moment, de sa durée exacte. Elle s'annule si le moment change —
  // jamais de minuterie orpheline.
  useEffect(() => {
    if (!moment) return;
    const minuterie = setTimeout(() => dispatch({ type: "avancer" }), moment.duree);
    return () => clearTimeout(minuterie);
  }, [moment]);

  const vider = useCallback(() => dispatch({ type: "vider" }), []);

  // Onglet mis de côté : on jette la file. L'état affiché ne dépend pas d'elle, il ne bouge pas.
  useEffect(() => {
    const surVisibilite = () => {
      if (document.visibilityState === "hidden") vider();
    };
    document.addEventListener("visibilitychange", surVisibilite);
    return () => document.removeEventListener("visibilitychange", surVisibilite);
  }, [vider]);

  const sauter = useCallback(() => dispatch({ type: "avancer" }), []);

  return { moment, enAttente: file.attente.length, sauter, vider };
}

/** Le mot qui accompagne chaque effet. Purement décoratif : le journal porte la phrase complète. */
const LIBELLES: Record<string, string> = {
  attaque: "Attaque !",
  impact: "Dégâts",
  ko: "K.O. !",
  pioche: "Pioche",
  pose: "En jeu",
  evolution: "Évolution !",
  energie: "Énergie",
  "carte-jouee": "Carte jouée",
  outil: "Outil",
  talent: "Talent",
  retraite: "Retraite",
  promotion: "Nouvel Actif",
  etat: "État",
  tour: "À toi",
  piece: "Pile ou face",
  fin: "Fin de partie",
  rattrapage: "Rattrapage",
};

export type CoucheAnimationProps = {
  /** L'animation à dessiner, ou `null` : la couche ne rend alors rien du tout. */
  animation: Animation | null;
  /** Sa durée réelle, injectée au CSS (`--pbm-anim-duree`). */
  duree: number;
  /** Nombre d'animations en attente, affiché quand la file rattrape son retard. */
  enAttente?: number;
  /** Saute l'animation en cours. Absent → aucun bouton (plateau en lecture seule). */
  onSauter?: () => void;
  /** Bascule le mode accéléré. Absent → pas de bouton d'accélération. */
  onBasculerAccelere?: () => void;
  /** `true` si le mode accéléré est actif (pour l'état du bouton). */
  accelere?: boolean;
  /**
   * L'effet typé à jouer **dans l'arène** plutôt que sur une carte (lot
   * `j-anim-attaques-typees`) : c'est le cas d'une attaque qui n'a touché personne (ratée au pile
   * ou face, annulée par la Confusion). Il n'y a alors pas de victime, donc pas de carte à brûler
   * — on ne va pas en désigner une au hasard.
   */
  effetTypee?: EffetTypeeEnCours | null;
  /**
   * Le **moment clé** en cours, ou `null` (lot `j-anim-evolution-ko`).
   *
   * Quand il y en a un, il **remplace** la pastille dans la même case centrale : un moment en dit
   * plus que le mot « K.O. ! », et les empiler aurait ajouté une occlusion au plateau sans rien
   * apporter. Les boutons « Passer » et « Accélérer », eux, restent là.
   */
  moment?: EffetMoment | null;
};

/**
 * Dessine l'animation en cours **au-dessus** du plateau, et donne le moyen de s'en passer.
 *
 * Deux propriétés non négociables, et c'est le critère d'acceptation n°1 du lot : la couche visuelle
 * est en `pointer-events-none` (elle ne peut **jamais** intercepter un clic sur une carte ou sur la
 * barre d'actions) et elle est en `absolute` dans l'arène (elle n'allonge donc pas la page — le
 * plateau ne tolère aucun défilement, lot `j-plateau-layout`). Le seul élément cliquable est le
 * bouton « passer », volontairement petit et dans un coin.
 *
 * La couche est `aria-hidden` : elle n'apporte aucune information que le journal de partie ne porte
 * déjà en texte (lot `j-plateau-journal`). Les boutons, eux, restent accessibles et nommés.
 */
export function CoucheAnimation({
  animation,
  duree,
  enAttente = 0,
  onSauter,
  onBasculerAccelere,
  accelere = false,
  effetTypee = null,
  moment = null,
}: CoucheAnimationProps) {
  // Un effet typé **sans cible** se joue au centre de l'arène, et il peut se jouer alors qu'aucune
  // animation n'est dessinée (mode réduit, où `animation` vaut toujours `null`). Il est donc rendu
  // à part, avant le test de sortie ci-dessous.
  const sansCible = effetTypee && !effetTypee.cible ? effetTypee : null;
  const arene = sansCible && (
    <div
      data-testid="anim-arene-fx"
      className="pointer-events-none absolute inset-0 z-20 grid place-items-center text-[2.5em]"
    >
      <span className="relative block h-[3em] w-[2.2em]">
        <EffetTypeAttaque effet={sansCible.effet} cle={sansCible.cle} />
      </span>
    </div>
  );

  // Le moment clé, dans la case centrale. Comme l'effet typé, il existe **aussi** quand le socle ne
  // dessine rien : en mode réduit, ou quand l'événement qui l'a produit n'a pas d'effet au registre
  // du socle (`main_revelee`, `mise_en_place_revelee` n'y sont pas). Il est donc rendu avant le test
  // de sortie, et pas à l'intérieur du bloc de la pastille.
  const scene = moment && (
    <div
      data-testid="anim-moment"
      data-genre={moment.genre}
      className="pointer-events-none absolute inset-0 z-20 grid place-items-center text-[1.2em]"
    >
      <EffetMomentCle effet={moment} />
    </div>
  );

  // Le moyen de s'en passer reste offert dès qu'il y a **quoi que ce soit** à l'écran — y compris un
  // moment qui se joue seul. Sans ça, les seules animations qui durent une seconde et demie auraient
  // été les seules qu'on ne pouvait pas couper.
  const boutons = (onSauter || onBasculerAccelere) && (
    // Cibles tactiles : au moins 24×24 px (WCAG 2.2, 2.5.8 — niveau AA), alors que ces deux
    // boutons faisaient 16 px de haut. Ils sont `absolute`, donc les agrandir n'allonge pas la
    // page — le plateau ne tolère aucun défilement (lot `j-plateau-layout`). C'est aussi pour
    // ça que l'arène n'atteint pas les 44 px du niveau AAA : voir `docs/jeu/ACCESSIBILITE.md`.
    <div className="absolute right-2 top-2 z-30 flex items-center gap-1">
      {onBasculerAccelere && (
        <button
          type="button"
          data-testid="anim-accelere"
          aria-pressed={accelere}
          onClick={onBasculerAccelere}
          className="min-h-6 min-w-6 rounded-full border border-white/25 bg-black/50 px-2 py-1 text-[11px] uppercase tracking-wider text-white/90 hover:bg-black/70"
        >
          {accelere ? "Vitesse normale" : "Accélérer"}
        </button>
      )}
      {onSauter && (
        <button
          type="button"
          data-testid="anim-sauter"
          onClick={onSauter}
          className="min-h-6 min-w-6 rounded-full border border-white/25 bg-black/50 px-2 py-1 text-[11px] uppercase tracking-wider text-white/90 hover:bg-black/70"
        >
          {enAttente > 0 ? `Passer (${enAttente})` : "Passer"}
        </button>
      )}
    </div>
  );

  if (!animation || !animation.effet) {
    if (!arene && !scene) return null;
    return (
      <>
        {arene}
        {scene}
        {boutons}
      </>
    );
  }

  const libelle = animation.resume
    ? `${animation.nombre} coups rejoués`
    : (LIBELLES[animation.effet] ?? animation.type);

  return (
    <>
      {arene}
      {scene}
      {/* La pastille, et seulement s'il n'y a pas de moment clé : un moment la REMPLACE dans la
          même case centrale. Les superposer aurait affiché « K.O. ! » par-dessus l'animation de
          K.O. — deux fois la même information, et une occlusion de plus sur le plateau. */}
      {!moment && (
        <div
          data-testid="anim-couche"
          data-effet={animation.effet}
          data-cible={animation.cible ?? ""}
          data-resume={animation.resume ? "" : undefined}
          aria-hidden
          className="pbm-anim pointer-events-none absolute inset-0 z-20 grid place-items-center"
          style={{ "--pbm-anim-duree": `${duree}ms` } as CSSProperties}
        >
          <span
            key={animation.cle}
            data-testid="anim-pastille"
            data-camp={animation.camp}
            className="pbm-anim-pastille rounded-full border border-[rgba(255,215,0,0.55)] bg-[rgba(6,18,11,0.72)] px-[1em] py-[0.35em] text-[1.1em] font-bold uppercase tracking-[0.1em] text-gold"
          >
            {libelle}
          </span>
        </div>
      )}

      {boutons}
    </>
  );
}
