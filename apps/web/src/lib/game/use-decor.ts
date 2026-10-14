/**
 * Le décor à peindre sous une partie (lot `j-arene-decors`) — **choix du joueur d'abord**.
 *
 * Ce fichier est le seul endroit « React » du décor : la règle de choix, les teintes et le moment
 * de la journée vivent dans {@link ./decors}, pur et testé. Ici on ne fait que brancher trois
 * sources sur cette règle — le réglage du compte, les types réellement en jeu, l'heure locale.
 *
 * ## Pourquoi le thème automatique lit *mon camp* et non la fiche du deck
 *
 * La vue d'une partie ne porte pas la composition du deck : le serveur ne l'y expose pas (et il a
 * raison, ce serait annoncer sa pioche). Mais elle porte le type de **mes** cartes — ma main, mon
 * actif, mon banc, ma défausse — et ma main seule, dès le premier tour, c'est sept cartes de mon
 * deck. L'échantillon est donc immédiat, fidèle, et **privé** : rien ici ne regarde l'adversaire.
 *
 * Le décor déduit est ensuite **figé** pour la durée de la partie : sans ça, poser une Énergie Feu
 * ferait basculer l'arène du gymnase au volcan en pleine partie. Un décor qui change tout seul
 * n'est pas un décor, c'est une distraction.
 */

import { useMemo, useRef } from "react";

import { useConfort } from "@/lib/confort-provider";
import {
  DECOR_DEFAUT,
  type MomentJour,
  decorEffectif,
  momentPourHeure,
} from "@/lib/game/decors";
import { type VuePartie, separerCamps } from "@/lib/game/plateau";

/** Ce qu'il faut poser sur l'arène : la clé du décor et son éclairage. */
export type DecorArene = { decor: string; moment: MomentJour };

/**
 * Tous les codes de type visibles dans **mon** camp, main comprise.
 *
 * La main n'est présente dans la vue que pour soi (frontière anti-triche posée côté serveur) :
 * l'adversaire n'entre donc jamais dans ce calcul, même par accident.
 */
export function typesDeMonCamp(vue: VuePartie): string[] {
  let moi;
  try {
    moi = separerCamps(vue).moi;
  } catch {
    // Une vue incohérente ne doit pas empêcher d'afficher le plateau : on retombe sur le défaut
    // par l'absence de types, et `separerCamps` criera là où c'est son rôle (le rendu du camp).
    return [];
  }
  const types: (string | null | undefined)[] = [
    moi.actif?.type,
    ...moi.banc.map((p) => p.type),
    ...(moi.main ?? []).map((c) => c.type),
    ...moi.defausse.map((c) => c.type),
  ];
  return types.filter((t): t is string => typeof t === "string" && t.length > 0);
}

/**
 * Le décor de l'arène pour cette partie.
 *
 * @param vue   la vue autoritaire courante, ou `null` tant qu'elle n'est pas chargée.
 * @param heure heure locale (0-23) — paramétrable pour les tests, l'horloge sinon.
 */
export function useDecorArene(vue: VuePartie | null, heure?: number): DecorArene {
  const { confort } = useConfort();
  // Le décor déduit, figé à sa première valeur utile (voir l'en-tête du fichier).
  const fige = useRef<string | null>(null);

  const types = useMemo(() => (vue ? typesDeMonCamp(vue) : []), [vue]);

  const decor = useMemo(() => {
    // Un choix explicite l'emporte toujours, et il n'a pas à être figé : le joueur qui change de
    // décor dans ses réglages doit le voir changer.
    if (confort.decor) return decorEffectif(confort.decor, types);
    if (fige.current) return fige.current;
    if (types.length === 0) return DECOR_DEFAUT;
    fige.current = decorEffectif(null, types);
    return fige.current;
    // `types` change à chaque coup ; le verrou `fige` est ce qui rend le résultat stable.
  }, [confort.decor, types]);

  const moment = momentPourHeure(heure ?? new Date().getHours());
  return { decor, moment };
}
