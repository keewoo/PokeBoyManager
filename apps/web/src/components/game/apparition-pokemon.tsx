"use client";

import type { CSSProperties } from "react";

import type { Apparition } from "@/lib/game/anim-apparition";

/**
 * Le Pokémon qui surgit au-dessus de sa carte (lot `j-anim-pokemon-apparition`, décision DJ3).
 *
 * Ce composant ne décide de rien : tout — quels calques, quelle amplitude, combien de particules —
 * est déjà calculé par `anim-apparition.ts`, qui est pur. Ici on ne fait que poser des variables
 * CSS et des attributs de données, et laisser le compositeur travailler.
 *
 * ## Les trois règles qu'il respecte, et qui sont celles du socle
 *
 * 1. **`pointer-events-none` et `absolute`.** La page de partie ne tolère aucun défilement
 *    (`e2e/plateau-responsive.spec.ts`) et aucune animation ne peut empêcher un coup légal : la
 *    couche est hors flux et ne capture aucun clic.
 * 2. **`aria-hidden`.** C'est le journal de partie qui porte le texte ; annoncer l'apparition
 *    ferait entendre deux fois le même coup.
 * 3. **Rien d'autre que `transform` et `opacity`** n'est animé. La teinte et le détourage des
 *    calques arrière sont du CSS statique (`mask-image`, `opacity` fixe) — animer un `filter`
 *    remettrait le fil principal au travail à chaque image et ferait tomber le plancher de 30
 *    images/s sur l'appareil de référence.
 *
 * Rend `null` quand il n'y a pas d'apparition — c'est le cas **courant** (onze cartes du catalogue
 * en ont une), et ce `null` ne laisse aucun trou : l'effet de type générique joue comme avant.
 */
export function ApparitionPokemon({ apparition }: { apparition: Apparition | null }) {
  if (!apparition) return null;

  // L'image ne passe pas par une balise `img` : les quatre calques la partagent, les uns en
  // fond, les autres en masque de découpe. Une seule URL, donc un seul téléchargement.
  const style = {
    "--pbm-a-image": `url(${apparition.url})`,
    "--pbm-a-duree": `${apparition.duree}ms`,
    "--pbm-a-intensite": apparition.intensite,
  } as CSSProperties;

  return (
    <div
      key={apparition.cle}
      className="pbm-a"
      data-testid="apparition-pokemon"
      data-motif={apparition.motif}
      data-type={apparition.type ?? "aucun"}
      aria-hidden
      style={style}
    >
      {apparition.calques.map((calque) => (
        <span
          key={calque.calque}
          className="pbm-a-calque"
          data-calque={calque.calque}
          style={
            {
              "--pbm-a-amplitude": `${calque.amplitude}%`,
              "--pbm-a-elevation": `${-calque.elevation}%`,
              "--pbm-a-profondeur": calque.profondeur,
              "--pbm-a-retard": `${calque.retard}ms`,
            } as CSSProperties
          }
        />
      ))}
      {apparition.particules.map((particule) => (
        <span
          key={particule.index}
          className="pbm-a-particule"
          style={
            {
              "--pbm-a-angle": `${particule.angle}deg`,
              "--pbm-a-retard": `${particule.retard}ms`,
            } as CSSProperties
          }
        />
      ))}
    </div>
  );
}
