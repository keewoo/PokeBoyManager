"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { getConfort, updateConfort, type PatchConfort } from "@/lib/api/confort";
import {
  CLE_CONFORT,
  CONFORT_DEFAUT,
  attributsConfort,
  normaliserConfort,
  type ReglagesConfort,
} from "@/lib/game/confort";

/**
 * Fournit les réglages de **confort et d'accessibilité** à tout l'arbre React (lot
 * `j-accessibilite-jeu`), et les applique au document.
 *
 * Trois sources, dans cet ordre de confiance, et c'est le cœur du fichier :
 *
 * 1. le **cache local** (`localStorage`), lu avant le premier rendu par le script du `layout` : il
 *    n'existe que pour ne pas afficher une animation ou un texte minuscule pendant la demi-seconde
 *    où le serveur répond. Ce n'est pas la vérité, c'est un souvenir ;
 * 2. le **serveur**, qui fait autorité dès qu'il a répondu (les réglages suivent le compte, pas
 *    l'appareil) ;
 * 3. les **défauts** du code, quand il n'y a ni l'un ni l'autre.
 *
 * Deux choix explicites :
 *
 * - **aucun appel réseau pour un visiteur** (`avecSession={false}`) : les routes du jeu répondent
 *   404 sans accès (D11), et tenter l'appel ne ferait qu'ajouter une erreur dans la console de
 *   quelqu'un qui n'est même pas connecté. Le cache local suffit à le servir ;
 * - un échec de lecture **ne retombe pas en silence sur les défauts** : on garde ce qu'on affichait
 *   (le cache) et on expose l'erreur dans {@link useConfort}. Écraser « ne pas animer » par
 *   « animer » parce qu'une requête a échoué, c'est rallumer les animations de quelqu'un qui a
 *   demandé qu'elles s'arrêtent.
 */

type ConfortContexte = {
  confort: ReglagesConfort;
  /** Modifie un ou plusieurs réglages : optimiste à l'écran, confirmé par le serveur. */
  regler: (patch: PatchConfort) => Promise<void>;
  /** `true` tant que le serveur n'a pas répondu (le cache local est affiché pendant ce temps). */
  chargement: boolean;
  /** Le message d'un échec de lecture ou d'écriture, ou `null`. Jamais masqué. */
  erreur: string | null;
};

const DEFAUT: ConfortContexte = {
  confort: CONFORT_DEFAUT,
  regler: async () => {},
  chargement: false,
  erreur: null,
};

const Contexte = createContext<ConfortContexte>(DEFAUT);

/** Lit le cache local, en tolérant son absence et un contenu d'une version précédente. */
function lireCache(): ReglagesConfort | null {
  try {
    const brut = window.localStorage.getItem(CLE_CONFORT);
    return brut ? normaliserConfort(JSON.parse(brut)) : null;
  } catch {
    // `localStorage` indisponible (navigation privée stricte) ou JSON corrompu : on repart des
    // défauts. Pas de repli masqué : il n'y a rien à signaler, le serveur reste la vérité.
    return null;
  }
}

/** Écrit le cache local. Un échec (quota, mode privé) n'empêche pas de jouer : on l'ignore. */
function ecrireCache(r: ReglagesConfort): void {
  try {
    window.localStorage.setItem(CLE_CONFORT, JSON.stringify(r));
  } catch {
    /* le réglage reste appliqué à l'écran et persisté côté serveur : rien de perdu */
  }
}

export function ConfortProvider({
  children,
  avecSession = false,
}: {
  children: React.ReactNode;
  /** Vrai si un cookie de session existe (lu côté serveur par le `layout`). */
  avecSession?: boolean;
}) {
  const [confort, setConfort] = useState<ReglagesConfort>(CONFORT_DEFAUT);
  const [chargement, setChargement] = useState(avecSession);
  const [erreur, setErreur] = useState<string | null>(null);

  // Le souvenir d'abord : il évite le clignotement, et il sert les visiteurs non connectés.
  useEffect(() => {
    const cache = lireCache();
    if (cache) setConfort(cache);
  }, []);

  // Puis la vérité, si le compte en a une. Un 404 (compte sans accès au jeu, D11) n'est pas une
  // panne : ces réglages n'ont alors simplement pas de version serveur.
  useEffect(() => {
    if (!avecSession) return;
    let actif = true;
    getConfort()
      .then((serveur) => {
        if (!actif) return;
        const reglages = normaliserConfort(serveur);
        setConfort(reglages);
        ecrireCache(reglages);
        setErreur(null);
      })
      .catch((cause: unknown) => {
        if (!actif) return;
        const statut = (cause as { status?: number } | null)?.status;
        if (statut !== 404 && statut !== 401) {
          setErreur("Tes réglages de confort n'ont pas pu être relus.");
        }
      })
      .finally(() => {
        if (actif) setChargement(false);
      });
    return () => {
      actif = false;
    };
  }, [avecSession]);

  // Application au document : les attributs que `globals.css` interprète. Même logique que le
  // script anti-clignotement du `layout` — une seule définition de ce que « réduites » veut dire.
  useEffect(() => {
    for (const [cle, valeur] of Object.entries(attributsConfort(confort))) {
      document.documentElement.setAttribute(cle, valeur);
    }
  }, [confort]);

  const regler = useCallback(
    async (patch: PatchConfort) => {
      // Optimiste : l'écran suit tout de suite (couper les animations doit être immédiat), puis le
      // serveur confirme. S'il refuse, on remet ce qu'il dit — jamais ce qu'on espérait.
      const avant = confort;
      const vise = normaliserConfort({ ...confort, ...patch });
      setConfort(vise);
      ecrireCache(vise);
      try {
        const serveur = normaliserConfort(await updateConfort(patch));
        setConfort(serveur);
        ecrireCache(serveur);
        setErreur(null);
      } catch {
        setConfort(avant);
        ecrireCache(avant);
        setErreur("Ce réglage n'a pas pu être enregistré. Réessaie dans un instant.");
      }
    },
    [confort],
  );

  const valeur = useMemo<ConfortContexte>(
    () => ({ confort, regler, chargement, erreur }),
    [confort, regler, chargement, erreur],
  );

  return <Contexte.Provider value={valeur}>{children}</Contexte.Provider>;
}

/**
 * Les réglages de confort courants.
 *
 * Ne **lève pas** hors d'un {@link ConfortProvider}, contrairement à `useTheme` : il renvoie les
 * défauts. C'est volontaire — un composant de jeu doit pouvoir se rendre dans un test, un replay ou
 * une capture sans qu'on ait à monter un fournisseur de préférences pour qu'il s'affiche.
 */
export function useConfort(): ConfortContexte {
  return useContext(Contexte);
}
