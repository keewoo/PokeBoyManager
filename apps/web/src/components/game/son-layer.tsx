"use client";

import { useCallback, useEffect, useRef } from "react";

import { useSons } from "@/lib/sons-provider";
import {
  ECART_MIN,
  FILE_SONS_VIDE,
  SEUIL_MINUTERIE_MS,
  SONS,
  type CoupSons,
  type FileSons,
  planifierSons,
  reduireSons,
  tirerSon,
} from "@/lib/game/sons";

/**
 * Le branchement des sons sur l'écran de partie (lot `j-son`).
 *
 * Même doctrine que le socle d'animation, et pour les mêmes raisons : les sons suivent les
 * **événements** diffusés par le serveur, jamais l'état affiché. Un son ne retient rien, ne
 * conditionne rien, et son absence ne bloque aucune action légale.
 *
 * ## Pourquoi la file vit dans une `ref` et non dans un `useReducer`
 *
 * Parce que **rien à l'écran n'en dépend**. Le socle d'animation doit se rendre (il y a une
 * pastille à dessiner) ; un son, non. Le mettre dans un état React ferait re-rendre tout le plateau
 * à chaque bruitage — plusieurs fois par seconde pendant un échange — et c'est exactement le coût
 * que le plancher d'images par seconde ne peut pas payer (`PLANCHER_FPS`, mesuré en CI par
 * `e2e/anim-fluidite.spec.ts`). Ici, la couche sonore provoque **zéro re-rendu** : elle ne peut pas
 * coûter une image.
 *
 * Tout ce qui décide reste pur et testé sans navigateur (`lib/game/sons.ts`) : l'ordre, l'écart
 * minimum, le rattrapage, l'anti-doublon. Il ne reste ici que le temps et les écouteurs.
 */

/** Ce que {@link useFileSons} rend à l'écran de partie. */
export type EtatSons = {
  /**
   * Jette ce qui reste à jouer — le joueur agit, ou l'onglet passe en arrière-plan.
   *
   * Comme pour les animations : l'écran ne se met jamais en travers. Et comme pour les animations,
   * ce qui est jeté est **mémorisé**, pour qu'une resynchronisation ultérieure ne le déverse pas.
   */
  couper: () => void;
  /**
   * Combien de sons ont été volontairement passés par rattrapage, depuis le début de la partie.
   *
   * Exposé — et non simplement compté — parce que ce dépôt interdit le repli silencieux : un son
   * sauté est un choix de conception (on ne joue pas vingt bruitages d'affilée après une
   * reconnexion), et un choix se montre. La phrase de chacun de ces événements est de toute façon
   * dans le journal de partie.
   */
  ignores: () => number;
};

/**
 * Fait sonner une partie à partir des coups diffusés par le serveur.
 *
 * @param coups les coups diffusés, dans l'ordre (dédupliqués par l'appelant).
 * @param pour  le destinataire de la vue : c'est lui qui décide victoire ou défaite.
 * @param cle   identifiant de la partie — il change, la file repart de zéro.
 */
export function useFileSons({
  coups,
  pour,
  cle,
}: {
  coups: CoupSons[];
  pour: string;
  cle?: string;
}): EtatSons {
  const { jouer, reglages, pret } = useSons();
  const file = useRef<FileSons>(FILE_SONS_VIDE);
  const minuterie = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Même borne que le socle d'animation : on ne replanifie pas tout l'historique à chaque coup.
  const dernierPlanifie = useRef(-1);
  // `jouer` change à chaque réglage ; la boucle d'écoulement, non. La ref évite de la recréer (et
  // donc d'annuler une minuterie en cours) juste parce que le volume a bougé d'un cran.
  const jouerRef = useRef(jouer);
  jouerRef.current = jouer;
  const bruitagesRef = useRef(reglages.bruitages);
  bruitagesRef.current = reglages.bruitages;

  // L'écoulement de la file, en une minuterie par son. Récursive par une ref : `setTimeout` doit
  // pouvoir rappeler la dernière version de la fonction sans que celle-ci se recrée à chaque tour.
  const ecoulerRef = useRef<() => void>(() => {});
  ecoulerRef.current = () => {
    minuterie.current = null;
    const maintenant = Date.now();
    const { file: suite, son } = tirerSon(file.current, maintenant);
    file.current = suite;
    if (son) jouerRef.current(son.recette);
    if (suite.attente.length === 0) return;
    // Rien n'est sorti (l'écart minimum n'était pas tenu) : on repasse quand il le sera.
    const depuis = suite.dernierDepart === null ? ECART_MIN : maintenant - suite.dernierDepart;
    minuterie.current = setTimeout(() => ecoulerRef.current(), Math.max(1, ECART_MIN - depuis));
  };

  const relancer = useCallback(() => {
    if (minuterie.current === null) ecoulerRef.current();
  }, []);

  const couper = useCallback(() => {
    if (minuterie.current !== null) {
      clearTimeout(minuterie.current);
      minuterie.current = null;
    }
    file.current = reduireSons(file.current, { type: "couper" });
  }, []);

  // Changement de partie : file neuve, mémoire comprise.
  useEffect(() => {
    dernierPlanifie.current = -1;
    file.current = reduireSons(file.current, { type: "reinitialiser" });
  }, [cle]);

  // Les coups neufs deviennent des sons. `pour` manquant (vue pas encore chargée) : on attend
  // plutôt que d'annoncer une victoire au mauvais joueur.
  useEffect(() => {
    if (!pour) return;
    const neufs = coups.filter((c) => c.numero > dernierPlanifie.current);
    if (neufs.length === 0) return;
    dernierPlanifie.current = neufs.reduce((m, c) => Math.max(m, c.numero), dernierPlanifie.current);
    const sons = planifierSons(neufs, pour);

    // Deux raisons de ne PAS jouer ces sons, et dans les deux cas on les **passe** : mémorisés,
    // comptés, jamais rejoués plus tard.
    //
    // - **le moteur n'est pas ouvert** (le joueur n'a pas encore interagi) : le navigateur
    //   l'interdit de toute façon, et les garder en réserve ferait entendre au premier clic un
    //   K.O. d'il y a dix minutes. Un F5 au quatre-vingtième tour livre toute la partie d'un bloc ;
    // - **les bruitages sont coupés** : c'est ce que couper veut dire. Les mettre en attente
    //   ferait qu'un rétablissement en pleine partie déverserait tout ce qu'on n'a pas voulu
    //   entendre.
    if (!pret || !bruitagesRef.current) {
      file.current = reduireSons(file.current, { type: "passer", sons });
      return;
    }

    file.current = reduireSons(file.current, { type: "empiler", sons });
    relancer();
  }, [coups, pour, pret, relancer]);

  // Les bruitages viennent d'être coupés : ce qui attendait ne sonnera pas.
  useEffect(() => {
    if (!reglages.bruitages) couper();
  }, [reglages.bruitages, couper]);

  // Onglet mis de côté : on jette la file. Un onglet en arrière-plan qui continue de bruiter est
  // la façon la plus sûre de faire couper le son pour de bon — et l'état affiché ne dépend de rien.
  useEffect(() => {
    const surVisibilite = () => {
      if (document.visibilityState === "hidden") couper();
    };
    document.addEventListener("visibilitychange", surVisibilite);
    return () => document.removeEventListener("visibilitychange", surVisibilite);
  }, [couper]);

  // Démontage : aucune minuterie ne survit au départ du joueur.
  useEffect(() => {
    return () => {
      if (minuterie.current !== null) clearTimeout(minuterie.current);
      minuterie.current = null;
    };
  }, []);

  const ignores = useCallback(() => file.current.ignores, []);
  return { couper, ignores };
}

/**
 * Fait sonner la **minuterie** quand le temps presse — **une seule fois** par décision.
 *
 * Trois décisions de conception, et chacune vient du même principe : *« on n'attend jamais devant
 * un écran muet »*, mais on ne met pas la pression à un enfant de onze ans.
 *
 * - **une fois**, au passage du seuil ({@link SEUIL_MINUTERIE_MS}), et pas à chaque seconde. Un tic
 *   répété sur quelqu'un qui cherche son coup n'est pas de l'information, c'est de la pression ;
 * - **le son le plus discret de la banque**, et c'est un invariant testé (`sons.test.ts`) : le lot
 *   l'exige nommément — *« qu'aucun son ne surprenne, la minuterie surtout »* ;
 * - **seulement quand c'est à moi de décider** : prévenir quelqu'un de l'expiration d'un délai
 *   qu'il ne peut pas tenir n'a aucun sens.
 *
 * Le serveur reste maître du temps : il décompte, il expire, il applique la réponse par défaut
 * (DJ4). Ce crochet ne fait que donner à entendre une estimation déjà affichée à l'écran.
 *
 * @param cle      identité de la décision en cours — elle change, le seuil se réarme.
 * @param restantMs temps restant estimé, ou `null` si la décision n'est pas chronométrée.
 * @param actif    `false` quand ce n'est pas à moi de décider : rien ne sonne.
 */
export function useMinuterieSonore({
  cle,
  restantMs,
  actif,
}: {
  cle: string | null;
  restantMs: number | null;
  actif: boolean;
}): void {
  const { jouer } = useSons();
  const jouerRef = useRef(jouer);
  jouerRef.current = jouer;
  // Déjà sonné pour CETTE décision ? La ref porte la clé, pas un booléen : une décision qui
  // s'enchaîne à une autre réarme le seuil sans qu'on ait à penser à le remettre à zéro.
  const sonnee = useRef<string | null>(null);

  useEffect(() => {
    if (!actif || cle === null || restantMs === null) return;
    if (sonnee.current === cle) return;
    if (restantMs > SEUIL_MINUTERIE_MS) return;
    sonnee.current = cle;
    jouerRef.current(SONS.minuterie);
  }, [cle, restantMs, actif]);
}

/**
 * L'interrupteur de son : **couper est à un clic, rétablir aussi**.
 *
 * Il ne touche qu'aux **bruitages** — la musique d'ambiance se règle dans `/jeu/sons`, parce
 * qu'elle est coupée par défaut (DJ9) et qu'un bouton qui couperait les deux laisserait croire
 * qu'on a rallumé une musique qu'on n'a jamais demandée.
 *
 * Rendu seul (sans positionnement) pour qu'il soit testable et réutilisable ; c'est
 * {@link BarreSon} qui le place sur le plateau.
 */
export function BoutonSon({ className }: { className?: string }) {
  const { reglages, regler } = useSons();
  const actif = reglages.bruitages;
  return (
    <button
      type="button"
      data-testid="son-bascule"
      aria-pressed={actif}
      aria-label={actif ? "Couper les sons" : "Rétablir les sons"}
      onClick={() => regler({ bruitages: !actif })}
      // Cible tactile d'au moins 24×24 px (WCAG 2.2, 2.5.8 — niveau AA), comme les boutons de la
      // couche d'animation. Voir `docs/jeu/ACCESSIBILITE.md` pour pourquoi l'arène n'atteint pas
      // les 44 px du niveau AAA.
      className={`min-h-6 min-w-6 rounded-full border border-white/25 bg-black/50 px-2 py-1 text-[11px] uppercase tracking-wider text-white/90 hover:bg-black/70 ${className ?? ""}`}
    >
      {actif ? "🔊 son" : "🔇 coupé"}
    </button>
  );
}

/**
 * Place l'interrupteur de son sur le plateau — **hors du flux**, au coin haut droit.
 *
 * Trois contraintes se croisent ici, et la convention du dépôt les résout déjà :
 *
 * - la page `/jeu/parties/{id}` **n'admet aucun défilement** (lot `j-plateau-layout`, mesuré par
 *   `e2e/plateau-responsive.spec.ts`). Un bouton en flux normal l'aurait fait défiler — ce qui ne
 *   se voit ni en `vitest` ni au `type-check`. D'où `fixed`, comme le tiroir d'aide, la palette
 *   d'emotes, le journal et le bandeau de pré-chargement ;
 * - l'enveloppe est `pointer-events-none` et le bouton `pointer-events-auto` : la barre couvre
 *   toute la largeur pour se positionner, mais elle ne peut **jamais** intercepter un clic sur une
 *   carte ;
 * - le coin **haut droit** parce que c'est le seul libre : l'aide est en haut à gauche, les emotes
 *   à droite au milieu, le journal et le pré-chargement en bas. Et surtout, il n'est **pas** dans
 *   l'arène : un bouton posé dans un coin de l'arène aurait recouvré en permanence le compteur de
 *   récompenses d'un des deux joueurs (le bandeau `VsBar` occupe les deux coins hauts).
 *
 * Toujours visible, contrairement aux boutons « Passer » et « Accélérer » qui n'existent que
 * pendant une animation : on coupe le son justement quand il gêne, pas quand quelque chose bouge.
 */
export function BarreSon() {
  return (
    <div className="pointer-events-none fixed inset-x-0 top-0 z-30 flex justify-end px-2 pt-2">
      <BoutonSon className="pointer-events-auto" />
    </div>
  );
}
