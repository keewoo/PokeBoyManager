"use client";

import { type CSSProperties, useCallback, useEffect, useReducer, useRef, useState } from "react";

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
 */

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
  /** `true` si le système demande des animations réduites : l'accélération n'a alors plus de sens. */
  reduit: boolean;
  /** Saute l'animation en cours et enchaîne. */
  sauter: () => void;
  /** Jette tout ce qui reste (le joueur agit : l'écran ne doit jamais se mettre en travers). */
  vider: () => void;
  /** Bascule le mode accéléré (sans effet quand le système demande des animations réduites). */
  basculerAccelere: () => void;
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
  // Réglage système : il gagne toujours sur le choix du joueur (c'est une demande d'accessibilité,
  // pas une préférence de confort).
  const [reduit, setReduit] = useState(false);
  const [accelere, setAccelere] = useState(false);
  const mode: ModeAnimation = reduit ? "reduit" : accelere ? "accelere" : "normal";
  // Dernier numéro de coup déjà planifié : la borne qui évite de replanifier tout l'historique à
  // chaque coup reçu (et de le rejouer quand la mémoire bornée de la file a oublié ses clés).
  const dernierPlanifie = useRef(-1);

  // `prefers-reduced-motion` : lu au montage et suivi s'il change en cours de partie.
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!mq) return;
    const appliquer = () => setReduit(mq.matches);
    appliquer();
    mq.addEventListener?.("change", appliquer);
    return () => mq.removeEventListener?.("change", appliquer);
  }, []);

  useEffect(() => {
    dispatch({ type: "mode", mode });
  }, [mode]);

  // Changement de partie : file neuve, mémoire comprise.
  useEffect(() => {
    dernierPlanifie.current = -1;
    dispatch({ type: "reinitialiser" });
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

  // Onglet mis de côté : on jette la file. L'état affiché ne dépend pas d'elle, il ne bouge pas.
  useEffect(() => {
    const surVisibilite = () => {
      if (document.visibilityState === "hidden") dispatch({ type: "vider" });
    };
    document.addEventListener("visibilitychange", surVisibilite);
    return () => document.removeEventListener("visibilitychange", surVisibilite);
  }, []);

  const sauter = useCallback(() => dispatch({ type: "sauter" }), []);
  const vider = useCallback(() => dispatch({ type: "vider" }), []);
  const basculerAccelere = useCallback(() => setAccelere((v) => !v), []);

  return {
    // En mode réduit, rien n'est dessiné : la file se vide en silence.
    animation: mode === "reduit" ? null : courante,
    duree,
    enAttente: file.attente.length,
    mode,
    reduit,
    sauter,
    vider,
    basculerAccelere,
  };
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
}: CoucheAnimationProps) {
  if (!animation || !animation.effet) return null;
  const libelle = animation.resume
    ? `${animation.nombre} coups rejoués`
    : (LIBELLES[animation.effet] ?? animation.type);

  return (
    <>
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

      {(onSauter || onBasculerAccelere) && (
        <div className="absolute right-2 top-2 z-30 flex items-center gap-1">
          {onBasculerAccelere && (
            <button
              type="button"
              data-testid="anim-accelere"
              aria-pressed={accelere}
              onClick={onBasculerAccelere}
              className="rounded-full border border-white/25 bg-black/50 px-2 py-0.5 text-[10px] uppercase tracking-wider text-white/80 hover:bg-black/70"
            >
              {accelere ? "Vitesse normale" : "Accélérer"}
            </button>
          )}
          {onSauter && (
            <button
              type="button"
              data-testid="anim-sauter"
              onClick={onSauter}
              className="rounded-full border border-white/25 bg-black/50 px-2 py-0.5 text-[10px] uppercase tracking-wider text-white/80 hover:bg-black/70"
            >
              {enAttente > 0 ? `Passer (${enAttente})` : "Passer"}
            </button>
          )}
        </div>
      )}
    </>
  );
}
