import { type CSSProperties } from "react";

import { styleElement } from "@/lib/game/indicateurs";
import {
  type Couche,
  type EffetAttaque,
  PARTICULES_MAX,
} from "@/lib/game/anim-types";

/**
 * Le rendu d'un effet d'attaque **typé** (lot `j-anim-attaques-typees`).
 *
 * Tout ce qui décide vit dans `lib/game/anim-types.ts` (pur, testé sans navigateur) : quel type,
 * quelles couches, quelle intensité, combien de temps. Il ne reste ici que du balisage — autant de
 * `<i>` que de couches, autant que de particules, et les variables CSS qui portent la teinte et
 * l'amplitude. Aucun calcul, donc aucune règle réécrite côté écran.
 *
 * Deux propriétés non négociables, et ce sont les critères d'acceptation 2 et 3 du lot :
 *
 * - **ça ne capture jamais un clic** (`pointer-events-none`) : une animation ne peut pas empêcher
 *   de jouer un coup légal ;
 * - **ça ne couvre jamais les compteurs de dégâts** : le composant est rendu **avant** les
 *   indicateurs dans `BoardCard`, donc en dessous d'eux. L'ordre est gardé par un test — c'est
 *   précisément le risque que le lot nomme (« l'une d'elles finira par cacher un compteur de dégâts
 *   au moment décisif »), et un ordre de DOM se vérifie, contrairement à une intention.
 *
 * ## La version réduite
 *
 * En « animations réduites » (réglage système `prefers-reduced-motion` **ou** réglage du jeu,
 * `/jeu/confort`), `effet.anime` vaut `false` : on ne rend **aucune** couche, et à la place un
 * **badge immobile** qui dit en texte ce que l'animation aurait montré. Ce n'est pas la même chose
 * en plus court — c'est le même fait, par un autre canal. Couper les animations ne doit jamais
 * vouloir dire « tu ne sauras pas ce qui vient de se passer ».
 */

/** Ce que le composant reçoit : un effet déjà calculé, et rien d'autre. */
export type EffetTypeProps = {
  /** L'effet à dessiner, ou `null` : le composant ne rend alors rien du tout. */
  effet: EffetAttaque | null;
  /**
   * Clé de rendu : elle change à chaque nouvel effet pour **relancer** les images-clés CSS. Sans
   * elle, deux attaques Feu d'affilée sur la même carte ne rejoueraient pas l'animation (React
   * réutiliserait les mêmes nœuds, et le navigateur ne redémarre pas une animation déjà finie).
   */
  cle: string;
};

/** Les variables CSS d'une couche : son rang (pour l'étager) et son décalage de départ. */
function varsCouche(index: number): CSSProperties {
  return { "--pbm-fx-rang": index } as CSSProperties;
}

/**
 * Les variables d'une particule : son angle de départ et son retard.
 *
 * Réparties en **éventail** sur un demi-tour, avec un retard croissant : c'est ce qui donne
 * l'impression d'une gerbe plutôt que d'un bloc. Les deux valeurs sont déterministes (dérivées de
 * l'indice) — rien de tiré au hasard, pour qu'une capture de recette soit reproductible.
 */
function varsParticule(index: number, total: number): CSSProperties {
  const angle = total <= 1 ? 0 : -60 + (120 * index) / (total - 1);
  return {
    "--pbm-fx-angle": `${Math.round(angle)}deg`,
    "--pbm-fx-retard": `${index * 24}ms`,
  } as CSSProperties;
}

/**
 * Dessine un effet typé, posé sur la carte visée (ou dans l'arène quand l'attaque n'a pas touché).
 *
 * Le composant est `aria-hidden` en mode animé — le journal de partie porte déjà la phrase complète
 * en texte (lot `j-plateau-journal`), et doubler l'information ferait bégayer les lecteurs d'écran.
 * En mode **réduit**, au contraire, le badge est annoncé (`role="img"` + `aria-label`) : il devient
 * le seul canal visuel de l'information.
 */
export function EffetTypeAttaque({ effet, cle }: EffetTypeProps) {
  if (!effet) return null;

  if (!effet.anime) {
    const style = styleElement(effet.type);
    return (
      <span
        key={cle}
        data-testid="fx-reduit"
        data-fx={effet.cle}
        data-palier={effet.palier}
        role="img"
        aria-label={effet.phrase}
        title={effet.phrase}
        className="pointer-events-none absolute inset-x-0 top-1/2 z-10 mx-auto w-fit -translate-y-1/2 rounded-[0.3em] px-[0.4em] py-[0.1em] font-mono text-[0.5em] font-bold leading-none"
        style={{ backgroundColor: style.couleur, color: style.texte }}
      >
        {effet.badge}
      </span>
    );
  }

  return (
    <span
      key={cle}
      data-testid="fx-typee"
      data-fx={effet.cle}
      data-palier={effet.palier}
      data-renforce={effet.renforce ? "" : undefined}
      data-attenue={effet.attenue ? "" : undefined}
      data-echec={effet.echec ? "" : undefined}
      aria-hidden
      className="pbm-fx pointer-events-none absolute inset-0 z-10 overflow-hidden rounded-[inherit]"
      style={
        {
          "--pbm-fx-duree": `${effet.duree}ms`,
          "--pbm-fx-trace": `${effet.trace}ms`,
          "--pbm-fx-intensite": effet.intensite,
        } as CSSProperties
      }
    >
      {effet.couches.map((couche, i) =>
        couche === "particules" ? (
          <span key={couche} className="pbm-fx-gerbe" data-couche="particules">
            {Array.from({ length: Math.min(effet.particules, PARTICULES_MAX) }, (_, p) => (
              <i key={p} className="pbm-fx-particule" style={varsParticule(p, effet.particules)} />
            ))}
          </span>
        ) : (
          <i
            key={couche}
            className="pbm-fx-couche"
            data-couche={couche satisfies Couche}
            style={varsCouche(i)}
          />
        ),
      )}
      {/* La trace résiduelle : ce qui reste de l'attaque une fraction de seconde après (bords
          noircis, carte trempée). Elle est volontairement la DERNIÈRE couche de cette pile, mais
          la pile entière passe sous les indicateurs — elle ne peut donc pas cacher un chiffre. */}
      {effet.trace > 0 && <i className="pbm-fx-trace" data-couche="trace" />}
    </span>
  );
}
