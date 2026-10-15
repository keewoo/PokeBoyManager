"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import {
  CLE_SONS,
  MUSIQUE,
  SONS_DEFAUT,
  type Recette,
  type ReglagesSons,
  normaliserSons,
} from "@/lib/game/sons";
import { type Moteur, creerMoteur, jouerNote, jouerRecette, reglerVolume } from "@/lib/sons-moteur";

/**
 * Fournit le son à tout l'arbre React (lot `j-son`) : les réglages, et le moyen de jouer.
 *
 * Trois choix de conception, et chacun répond à un critère d'acceptation du lot.
 *
 * ## 1. Aucun son avant une interaction du joueur — et même aucun objet audio
 *
 * Les navigateurs refusent de jouer avant un geste de l'utilisateur. On ne se contente pas de
 * respecter ce refus : **on ne crée rien** tant que le geste n'a pas eu lieu. Le moteur
 * ({@link creerMoteur}) naît au premier `pointerdown` / `keydown` / `touchstart`, et seulement si
 * le joueur veut du son. Avant, {@link SonsContexte.jouer} ne fait rien — il n'y a pas de contexte
 * audio à reprendre, donc pas d'avertissement dans la console, et pas de son qui part en retard
 * d'un seul coup au premier clic.
 *
 * ## 2. Le réglage est mémorisé **par appareil** (DJ9)
 *
 * `localStorage`, et pas le serveur — contrairement au confort (`lib/confort-provider.tsx`) ou aux
 * emotes, qui suivent le compte. La décision DJ9 le dit, et la raison tient : le volume supportable
 * dépend de l'endroit et de l'appareil, pas de la personne. Le même enfant veut du son sur la
 * tablette du salon et le silence sur le téléphone emprunté dans le train. Conséquence voulue :
 * **aucune route HTTP**, donc rien à isoler par `user_id`, et rien de ce réglage ne quitte
 * l'appareil.
 *
 * ## 3. Couper est immédiat
 *
 * Le volume général est **un seul nœud** ({@link Moteur.maitre}). Couper le met à zéro dans le
 * même geste, avant même que React ne se re-rende : ce qui était déjà en vol s'éteint. Les sons
 * encore en attente, eux, sont jetés par la file (`reduireSons`, action `couper`).
 */

/** Ce que le contexte offre. */
export type SonsContexte = {
  /** Les réglages courants de cet appareil. */
  reglages: ReglagesSons;
  /** Modifie un ou plusieurs réglages. Immédiat à l'oreille, puis mémorisé. */
  regler: (patch: Partial<ReglagesSons>) => void;
  /**
   * Joue une recette **si** les bruitages sont activés et si le joueur a déjà interagi.
   *
   * Ne lève jamais et ne prévient de rien : un son est un agrément, pas une information. Si le
   * navigateur refuse, le journal de partie porte déjà en texte tout ce que le son racontait.
   */
  jouer: (recette: Recette) => void;
  /** `true` si le moteur audio est ouvert (donc le joueur a interagi au moins une fois). */
  pret: boolean;
};

const DEFAUT: SonsContexte = {
  reglages: SONS_DEFAUT,
  regler: () => {},
  jouer: () => {},
  pret: false,
};

const Contexte = createContext<SonsContexte>(DEFAUT);

/** Lit le réglage mémorisé sur cet appareil, en tolérant son absence et une version précédente. */
function lireCache(): ReglagesSons | null {
  try {
    const brut = window.localStorage.getItem(CLE_SONS);
    return brut ? normaliserSons(JSON.parse(brut)) : null;
  } catch {
    // `localStorage` indisponible (navigation privée stricte) ou JSON illisible : on reste sur les
    // défauts de DJ9. Rien à signaler — il n'y a pas d'autre source de vérité pour ce réglage.
    return null;
  }
}

/** Écrit le réglage. Un échec (quota, mode privé) n'empêche pas de jouer : le son reste appliqué. */
function ecrireCache(r: ReglagesSons): void {
  try {
    window.localStorage.setItem(CLE_SONS, JSON.stringify(r));
  } catch {
    /* le réglage vaut pour cette session ; il ne survivra pas au rechargement, et c'est tout */
  }
}

/** Comment obtenir un `AudioContext` dans ce navigateur, ou `null` s'il n'en a pas. */
function fabriqueContexte(): (() => AudioContext) | null {
  if (typeof window === "undefined") return null;
  const Ctor =
    window.AudioContext ??
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  return Ctor ? () => new Ctor() : null;
}

export function SonsProvider({ children }: { children: React.ReactNode }) {
  const [reglages, setReglages] = useState<ReglagesSons>(SONS_DEFAUT);
  const [pret, setPret] = useState(false);
  const moteur = useRef<Moteur | null>(null);
  // Les réglages lus par les écouteurs d'événements et par la boucle de musique, sans les recréer
  // à chaque changement (un écouteur recréé perdrait le « premier geste »).
  const courants = useRef<ReglagesSons>(SONS_DEFAUT);
  courants.current = reglages;

  // Le souvenir de cet appareil, lu après le montage (`localStorage` n'existe pas au rendu serveur).
  useEffect(() => {
    const cache = lireCache();
    if (cache) setReglages(cache);
  }, []);

  /**
   * Ouvre le moteur, une seule fois. Appelé par le premier geste du joueur — jamais au montage.
   *
   * Renvoie le moteur pour que l'appelant puisse jouer dans le même geste : un bouton « rétablir le
   * son » doit s'entendre tout de suite, et attendre un re-rendu de React l'aurait rendu muet.
   */
  const eveiller = useCallback((): Moteur | null => {
    if (moteur.current) return moteur.current;
    const fabrique = fabriqueContexte();
    // Navigateur sans Web Audio : le jeu reste entièrement jouable, simplement muet.
    if (!fabrique) return null;
    try {
      moteur.current = creerMoteur(fabrique, courants.current.volume);
    } catch {
      // Création refusée (politique du navigateur, trop de contextes ouverts) : on reste muet
      // plutôt que de réessayer à chaque clic, ce qui empilerait les contextes.
      return null;
    }
    setPret(true);
    return moteur.current;
  }, []);

  // Le premier geste du joueur, et lui seul, ouvre le moteur. Les trois événements couvrent la
  // souris, le clavier et le tactile ; `once` fait qu'on ne les écoute pas une seconde de plus.
  useEffect(() => {
    const surGeste = () => {
      if (courants.current.bruitages || courants.current.musique) eveiller();
    };
    const options = { once: true, passive: true } as const;
    window.addEventListener("pointerdown", surGeste, options);
    window.addEventListener("keydown", surGeste, options);
    window.addEventListener("touchstart", surGeste, options);
    return () => {
      window.removeEventListener("pointerdown", surGeste);
      window.removeEventListener("keydown", surGeste);
      window.removeEventListener("touchstart", surGeste);
    };
  }, [eveiller]);

  const regler = useCallback(
    (patch: Partial<ReglagesSons>) => {
      const vise = normaliserSons({ ...courants.current, ...patch });
      courants.current = vise;
      setReglages(vise);
      ecrireCache(vise);
      // Immédiat, et dans le même geste : couper doit s'entendre avant le prochain rendu.
      // Un réglage changé EST une interaction du joueur — donc le moment légitime d'ouvrir le
      // moteur si on vient de rallumer le son.
      const m = vise.bruitages || vise.musique ? eveiller() : moteur.current;
      if (m) reglerVolume(m, vise.bruitages || vise.musique ? vise.volume : 0);
    },
    [eveiller],
  );

  const jouer = useCallback((recette: Recette) => {
    const m = moteur.current;
    // Pas de moteur = le joueur n'a pas encore interagi (ou le navigateur n'a pas Web Audio).
    // On ne l'ouvre PAS ici : `jouer` est appelé par un coup du serveur, pas par un geste, et
    // ouvrir un contexte audio hors geste est précisément ce que le critère n°3 interdit.
    if (!m || !courants.current.bruitages) return;
    jouerRecette(m, recette);
  }, []);

  // La musique d'ambiance : une phrase pentatonique, relancée à chaque tour de boucle. Coupée par
  // défaut (DJ9), donc cette minuterie n'existe pas tant que personne ne l'a demandée.
  useEffect(() => {
    if (!reglages.musique || !pret) return;
    const jouerPhrase = () => {
      const m = moteur.current;
      if (!m) return;
      MUSIQUE.notes.forEach((frequence, i) => {
        jouerNote(m, frequence, MUSIQUE.duree, MUSIQUE.gain, MUSIQUE.passeBas, i * MUSIQUE.ecart);
      });
    };
    jouerPhrase();
    const boucle = setInterval(jouerPhrase, MUSIQUE.notes.length * MUSIQUE.ecart + MUSIQUE.duree);
    return () => clearInterval(boucle);
  }, [reglages.musique, pret]);

  const valeur = useMemo<SonsContexte>(() => ({ reglages, regler, jouer, pret }), [
    reglages,
    regler,
    jouer,
    pret,
  ]);

  return <Contexte.Provider value={valeur}>{children}</Contexte.Provider>;
}

/**
 * Le son courant.
 *
 * Ne **lève pas** hors d'un {@link SonsProvider} : il renvoie des réglages par défaut et un
 * {@link SonsContexte.jouer} qui ne fait rien. C'est volontaire, et c'est la même règle que
 * `useConfort` — un composant de jeu doit pouvoir se rendre dans un test, un replay ou une capture
 * sans qu'on monte un fournisseur de son pour qu'il s'affiche.
 */
export function useSons(): SonsContexte {
  return useContext(Contexte);
}
