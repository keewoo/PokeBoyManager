import { type CSSProperties } from "react";

import { type EffetMoment, type PhaseCalculee } from "@/lib/game/anim-moments";

/**
 * Le rendu d'un **moment clé** (lot `j-anim-evolution-ko`).
 *
 * Tout ce qui décide vit dans `lib/game/anim-moments.ts` (pur, testé sans navigateur) : quel genre,
 * quels temps, combien d'objets, combien de temps, et ce que dit la version réduite. Il ne reste ici
 * que du balisage — autant de couches que de temps, autant d'objets que de cartes ou de pièces, et
 * les variables CSS qui portent la teinte et le rythme. Aucun calcul, donc aucune règle réécrite
 * côté écran.
 *
 * ## Pourquoi la scène est petite, et au centre
 *
 * Elle est rendue **à la place de la pastille du socle**, dans la même case centrale de l'arène
 * (`CoucheAnimation`). Ce n'est pas un détail d'esthétique : c'est ce qui garantit qu'un moment
 * n'ajoute **aucune** occlusion au plateau. Un tableau plein écran aurait été plus spectaculaire et
 * aurait masqué les compteurs de dégâts pendant une seconde et demie — exactement le reproche que
 * le lot précédent s'était fait interdire. Un moment remplace donc un mot ; il n'ajoute rien.
 *
 * ## Le rythme vient du module, pas du CSS
 *
 * Chaque temps ({@link PhaseCalculee}) connaît son `debut` et sa `duree` : les couches reçoivent
 * donc un `animation-delay` et un `animation-duration` calculés, et les gestes de l'objet sont
 * **enchaînés** en une liste d'animations CSS. Le premier geste est en `both` (il tient la pose
 * avant et après), les suivants en `forwards` — sans ça, un geste encore en attente appliquerait sa
 * pose de départ *par-dessus* le geste en cours (les animations plus tardives de la liste gagnent
 * sur la même propriété), et la carte sauterait à sa position finale dès la première image.
 *
 * ## Le pile ou face, et ce qui est honnête
 *
 * L'animation ne laisse **rien** fuir du résultat avant {@link EffetMoment.revelationA} : la pose
 * finale de chaque pièce n'est posée qu'à partir de là (`data-revelation`), et la rotation elle-même
 * est identique quel que soit le tirage (prouvé dans `anim-moments.test.ts`).
 *
 * Ce qui n'est **pas** prétendu, et qu'il vaut mieux écrire que laisser croire : le résultat est
 * déjà dans la charge utile reçue du serveur, puisque c'est le serveur qui a tranché (il fait
 * autorité — c'est le principe du jeu). Un joueur qui ouvrirait l'inspecteur le verrait. Ce que le
 * lot garantit, c'est qu'**aucun tirage n'a lieu côté client** et qu'aucune impression visuelle ne
 * devance le résultat : c'est la seule chose qu'une animation puisse garantir, et c'est celle que
 * le critère demande.
 */

/** Ce que le composant reçoit : un effet déjà calculé, et rien d'autre. */
export type EffetMomentProps = {
  /** Le moment à dessiner, ou `null` : le composant ne rend alors rien du tout. */
  effet: EffetMoment | null;
};

/** Les variables CSS d'une couche : son temps de départ, sa durée, son rang d'empilement. */
function varsCouche(phase: PhaseCalculee, rang: number): CSSProperties {
  return {
    "--pbm-m-debut": `${phase.debut}ms`,
    "--pbm-m-duree": `${phase.duree}ms`,
    "--pbm-m-rang": rang,
  } as CSSProperties;
}

/**
 * La liste d'animations CSS qui enchaîne les **gestes** d'un objet, temps après temps.
 *
 * Renvoie `undefined` quand aucun temps ne fait bouger l'objet : on laisse alors le CSS tranquille
 * plutôt que de poser une animation vide, qui empêcherait une feuille de style de reprendre la main.
 */
function animationGestes(phases: PhaseCalculee[]): string | undefined {
  const gestes = phases.filter((p) => p.geste !== "aucun");
  if (gestes.length === 0) return undefined;
  return gestes
    .map(
      (p, i) =>
        `pbm-anim-fx-m-${p.geste} ${p.duree}ms ease-out ${p.debut}ms ${i === 0 ? "both" : "forwards"}`,
    )
    .join(", ");
}

/**
 * Dessine un moment clé, ou son équivalent immobile quand les animations sont réduites.
 *
 * En mode animé, le composant est `aria-hidden` : le journal de partie porte déjà la phrase complète
 * en texte (lot `j-plateau-journal`), et la doubler ferait bégayer les lecteurs d'écran. En mode
 * **réduit**, au contraire, la phrase est annoncée (`role="img"` + `aria-label`) — elle devient le
 * seul canal de l'information.
 */
export function EffetMomentCle({ effet }: EffetMomentProps) {
  if (!effet) return null;

  if (!effet.anime) {
    return (
      <span
        key={effet.cle}
        data-testid="fx-moment-reduit"
        data-genre={effet.genre}
        data-camp={effet.camp}
        role="img"
        aria-label={effet.phrase}
        title={effet.phrase}
        className="pointer-events-none flex max-w-[14em] flex-col items-center gap-[0.2em] rounded-[0.4em] border border-[rgba(255,215,0,0.55)] bg-[rgba(6,18,11,0.86)] px-[0.8em] py-[0.4em] text-center"
      >
        <span className="text-[1em] font-bold uppercase tracking-[0.08em] text-gold">
          {effet.libelle}
        </span>
        <span className="text-[0.7em] font-semibold leading-tight text-white/90">
          {effet.badge}
        </span>
      </span>
    );
  }

  const gestes = animationGestes(effet.phases);

  return (
    <span
      key={effet.cle}
      data-testid="fx-moment"
      data-genre={effet.genre}
      data-camp={effet.camp}
      aria-hidden
      className="pbm-m pointer-events-none relative grid place-items-center"
      style={
        {
          "--pbm-m-total": `${effet.duree}ms`,
          "--pbm-m-revelation": `${effet.revelationA}ms`,
        } as CSSProperties
      }
    >
      {/* Les objets qui voyagent : les cartes d'une pile d'évolution, les récompenses prises, les
          pièces lancées. Leur nombre vient du serveur — c'est lui qui fait voir DEUX récompenses
          plutôt qu'un vol groupé (critère d'acceptation n°2). */}
      <span className="pbm-m-scene" data-objets={effet.objets.length}>
        {effet.objets.map((o) => (
          <i
            key={o.index}
            className="pbm-m-objet"
            data-objet={effet.genre === "piece" ? "piece" : "carte"}
            data-rang={o.index}
            /* La pose finale d'une pièce. Le CSS ne l'applique qu'à partir de
               `--pbm-m-revelation` : avant, les deux faces sont rigoureusement identiques. */
            data-face={o.face === null ? undefined : o.face ? "face" : "pile"}
            style={
              {
                "--pbm-m-index": o.index,
                "--pbm-m-retard": `${o.retard}ms`,
                ...(gestes ? { animation: gestes } : {}),
              } as CSSProperties
            }
          />
        ))}
      </span>

      {/* Les couches : une par couche de chaque temps, avec le départ et la durée de ce temps. */}
      {effet.phases.map((phase, rang) =>
        phase.couches.map((couche) => (
          <i
            key={`${phase.nom}-${couche}`}
            className="pbm-m-couche"
            data-couche={couche}
            data-phase={phase.nom}
            style={varsCouche(phase, rang)}
          />
        )),
      )}

      {/* Le mot du moment. Il remplace la pastille du socle — il ne s'y ajoute pas. */}
      <span
        data-testid="fx-moment-libelle"
        className="pbm-m-libelle rounded-full border border-[rgba(255,215,0,0.55)] bg-[rgba(6,18,11,0.72)] px-[0.9em] py-[0.3em] text-[1em] font-bold uppercase tracking-[0.1em] text-gold"
      >
        {effet.libelle}
      </span>
    </span>
  );
}
