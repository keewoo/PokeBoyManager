import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  SEUIL_NON_TEXTUEL,
  SEUIL_TEXTE,
  composer,
  contraste,
  luminance,
} from "@/lib/a11y/contraste";
import {
  DECORS,
  DECOR_DEFAUT,
  NUIT_APPOINT,
  NUIT_PART,
  type MomentJour,
  teintesDecor,
} from "@/lib/game/decors";

/**
 * **Contraste des décors d'arène** (lot `j-arene-decors`) — le critère d'acceptation du lot, mesuré.
 *
 * « Chaque décor passe le contrôle de contraste avec tous les indicateurs de plateau. » Ce fichier
 * est ce contrôle : **douze ambiances** (six décors × jour/nuit) croisées avec **chaque repère
 * posé directement sur le fond**, soit un produit complet, pas un échantillon.
 *
 * ## Ce que la mesure couvre, et pourquoi elle suffit
 *
 * Un décor est peint par trois couches de dégradés (`globals.css`, bloc « Décors d'arène »). Les
 * seules couleurs qui **éclaircissent** y sont les quatre teintes du décor ; les fondus sont
 * transparents et le vignettage est noir, donc ils ne peuvent qu'**assombrir**. Comme tous les
 * repères mesurés ici sont clairs, assombrir le fond ne fait qu'augmenter leur contraste :
 * mesurer contre les quatre teintes, c'est donc mesurer le **pire cas** de chaque décor. C'est ce
 * raisonnement qui autorise un test de calcul là où une image aurait exigé un échantillonnage.
 *
 * ## Ce qu'il ne couvre pas, délibérément
 *
 * Les repères posés sur leur **propre** fond opaque — compteur de dégâts, PV restants, pastilles
 * d'énergie, cadre de carte — ne touchent pas le décor : changer de décor ne peut pas les affecter.
 * Leur contraste est mesuré là où il se joue, dans `contraste-jeu.test.ts`.
 */

/** Un repère dessiné **directement sur le décor**, donc dont le contraste dépend de lui. */
type Repere = {
  /** Où il se voit, pour que l'échec nomme l'endroit et pas seulement une couleur. */
  nom: string;
  /** Sa couleur nominale. */
  couleur: string;
  /** Son opacité (1 quand elle est pleine) — la couleur réellement vue est composée sur le fond. */
  alpha: number;
  /** 4,5:1 si ça se lit, 3:1 si ça se repère (WCAG 1.4.3 vs 1.4.11). */
  seuil: number;
  /** Fichier source où la valeur est écrite — vérifié par la garde d'ancrage ci-dessous. */
  source: string;
  /**
   * Ce qu'il faut chercher dans la source pour prouver que ce repère existe encore. Par défaut :
   * la couleur elle-même (`#rrggbb`) pour un repère opaque, sa forme `rgba(r,g,b,a)` sinon.
   * À renseigner quand l'opacité vient d'ailleurs — `opacity-75` est une classe Tailwind, pas une
   * couleur, et la chercher sous forme de `rgba()` ne prouverait rien.
   */
  litteral?: string[];
};

const PLATEAU = "src/components/game";

/**
 * Les repères du plateau posés sur le fond.
 *
 * Cette liste est **ancrée dans le code** par le dernier test du fichier : chaque couleur doit
 * exister dans le fichier cité. Sans cet ancrage, la liste se périmerait en silence au premier
 * changement de teinte d'un composant — et le test continuerait de passer en mesurant des
 * couleurs que plus personne n'affiche.
 */
const REPERES: Repere[] = [
  // --- Ce qui se lit (4,5:1) -------------------------------------------------------------
  {
    nom: "texte général de l'arène",
    couleur: "#EAF3EE",
    alpha: 1,
    seuil: SEUIL_TEXTE,
    source: `${PLATEAU}/game-board.tsx`,
  },
  {
    nom: "étiquette d'une zone (banc, pioche, défausse…)",
    couleur: "#9FD9BC",
    alpha: 1,
    seuil: SEUIL_TEXTE,
    source: `${PLATEAU}/game-board.tsx`,
  },
  {
    nom: "ligne centrale « Stade »",
    couleur: "#9FD9BC",
    // `opacity-75` sur la ligne du Stade : mesurer sa couleur pleine surestimerait le contraste.
    alpha: 0.75,
    seuil: SEUIL_TEXTE,
    source: `${PLATEAU}/game-board.tsx`,
    litteral: ["#9FD9BC", "opacity-75"],
  },
  {
    nom: "« VS » et nom de carte (or)",
    couleur: "#FFD700",
    alpha: 1,
    seuil: SEUIL_TEXTE,
    source: "src/app/globals.css",
    litteral: ["--gold:#FFD700"],
  },
  {
    nom: "étiquette d'un emplacement vide",
    couleur: "#9BA3C7",
    alpha: 1,
    seuil: SEUIL_TEXTE,
    source: "src/app/globals.css",
    litteral: ["--muted-foreground:#9BA3C7"],
  },
  // --- Ce qui se repère (3:1) ------------------------------------------------------------
  {
    nom: "pastille de récompense restante (bord sombre du dégradé)",
    couleur: "#C98A12",
    alpha: 1,
    seuil: SEUIL_NON_TEXTUEL,
    source: `${PLATEAU}/game-board.tsx`,
  },
  {
    nom: "pastille de récompense déjà prise (liseré pointillé)",
    couleur: "#FFFFFF",
    alpha: 0.45,
    seuil: SEUIL_NON_TEXTUEL,
    source: `${PLATEAU}/game-board.tsx`,
  },
  {
    nom: "liseré d'un emplacement vide",
    couleur: "#FFFFFF",
    alpha: 0.45,
    seuil: SEUIL_NON_TEXTUEL,
    source: `${PLATEAU}/board-card.tsx`,
  },
  {
    nom: "filet de la ligne centrale",
    couleur: "#FFFFFF",
    alpha: 0.45,
    seuil: SEUIL_NON_TEXTUEL,
    source: `${PLATEAU}/game-board.tsx`,
  },
  {
    nom: "liseré d'une pile consultable",
    couleur: "#FFD700",
    alpha: 0.5,
    seuil: SEUIL_NON_TEXTUEL,
    source: `${PLATEAU}/zone-consultation.tsx`,
  },
  {
    nom: "liseré d'une pile cachée",
    couleur: "#FFFFFF",
    alpha: 0.45,
    seuil: SEUIL_NON_TEXTUEL,
    source: `${PLATEAU}/zone-consultation.tsx`,
  },
  {
    nom: "liseré de la pastille du socle d'animation",
    couleur: "#FFD700",
    alpha: 0.55,
    seuil: SEUIL_NON_TEXTUEL,
    source: `${PLATEAU}/animation-layer.tsx`,
  },
  {
    nom: "anneau de focus clavier",
    couleur: "#FFD700",
    alpha: 1,
    seuil: SEUIL_NON_TEXTUEL,
    source: "src/app/globals.css",
    litteral: ["outline:3pxsolidvar(--gold)"],
  },
];

/** Les douze ambiances : chaque décor, de jour et de nuit. */
const AMBIANCES: { cle: string; moment: MomentJour }[] = Object.keys(DECORS).flatMap((cle) =>
  (["jour", "nuit"] as MomentJour[]).map((moment) => ({ cle, moment })),
);

function lire(relatif: string): string {
  return readFileSync(path.resolve(__dirname, "../..", relatif), "utf-8");
}

describe("contraste des décors d'arène", () => {
  it("mesure bien ce qu'elle prétend mesurer (garde du calcul)", () => {
    // Même garde que dans `contraste-jeu.test.ts` : sans elle, une erreur dans le calcul rendrait
    // tout le reste du fichier complaisant — et un test de contraste complaisant est pire que pas
    // de test, puisqu'il rassure.
    expect(contraste("#000000", "#FFFFFF")).toBeCloseTo(21, 1);
    // Composer à alpha 1 rend la couleur du dessus ; à alpha 0, celle du dessous.
    expect(composer("#000000", "#FFFFFF", 1)).toBe("#ffffff");
    expect(composer("#061208", "#FFFFFF", 0)).toBe("#061208");
    // Un blanc à 30 % sur un fond quasi noir est gris foncé, pas blanc : c'est tout l'intérêt de
    // composer avant de mesurer. Et ce chiffre-là est la raison d'un correctif de ce lot : les
    // liserés du plateau étaient à 0,28-0,35 d'opacité, donc **sous 3:1 sur le fond d'origine
    // déjà** — ils sont passés à 0,45. Mesurer leur couleur nominale (du blanc pur, 19:1) aurait
    // caché le défaut au lieu de le trouver.
    expect(contraste(composer("#06120B", "#FFFFFF", 0.3), "#06120B")).toBeCloseTo(2.64, 1);
    expect(contraste(composer("#06120B", "#FFFFFF", 0.45), "#06120B")).toBeGreaterThan(
      SEUIL_NON_TEXTUEL,
    );
  });

  it("chaque repère du plateau reste lisible sur chacune des douze ambiances", () => {
    const fautifs: string[] = [];
    for (const { cle, moment } of AMBIANCES) {
      const teintes = teintesDecor(cle, moment);
      // La teinte la plus CLAIRE du décor est son pire cas (voir l'en-tête du fichier) : un
      // repère clair s'y détache le moins. Les trois autres ne peuvent qu'améliorer la mesure,
      // mais on les croise quand même — un décor peut un jour être recomposé.
      for (const [role, fond] of Object.entries(teintes)) {
        for (const repere of REPERES) {
          const vue = composer(fond, repere.couleur, repere.alpha);
          const ratio = contraste(vue, fond);
          if (ratio < repere.seuil) {
            fautifs.push(
              `${cle}/${moment} sur « ${role} » (${fond}) : ${repere.nom} à ` +
                `${ratio.toFixed(2)}:1 (exigé ${repere.seuil}:1)`,
            );
          }
        }
      }
    }
    expect(fautifs, `contraste insuffisant :\n  ${fautifs.join("\n  ")}`).toEqual([]);
  });

  it("aucun décor n'est assez clair pour que le plateau devienne le second plan", () => {
    // Le risque nommé du lot : « des décors trop présents ». Un plafond de luminance le borne
    // par le calcul, et pas au jugé. 0,06 est très bas (gris ~#3A3A3A) : à ce niveau, un décor
    // reste un fond. C'est la contrainte qui rend le test de contraste ci-dessus satisfaisable
    // pour les treize repères à la fois — elle ne peut pas être relevée sans le casser.
    const PLAFOND = 0.06;
    const trop = Object.values(DECORS)
      .flatMap((d) =>
        (["jour", "nuit"] as MomentJour[]).flatMap((moment) =>
          Object.entries(teintesDecor(d.cle, moment)).map(([role, hex]) => ({
            quoi: `${d.cle}/${moment}/${role}`,
            hex,
            l: luminance(hex),
          })),
        ),
      )
      .filter((t) => t.l > PLAFOND);
    expect(
      trop,
      `teintes trop claires : ${trop.map((t) => `${t.quoi} ${t.hex} à ${t.l.toFixed(3)}`).join(", ")}`,
    ).toEqual([]);
  });

  it("la nuit est plus sombre que le jour, pour les six décors", () => {
    // Une variation jour/nuit qui éclaircirait la nuit serait un bug visible mais silencieux :
    // le contraste resterait bon, l'ambiance serait fausse.
    for (const cle of Object.keys(DECORS)) {
      const jour = teintesDecor(cle, "jour");
      const nuit = teintesDecor(cle, "nuit");
      for (const role of ["tapis", "fond", "bord", "lueur"] as const) {
        expect(
          luminance(nuit[role]),
          `${cle}/${role} : la nuit (${nuit[role]}) n'est pas plus sombre que le jour (${jour[role]})`,
        ).toBeLessThanOrEqual(luminance(jour[role]));
      }
    }
  });

  it("les couleurs mesurées sont bien celles que le plateau affiche (ancrage)", () => {
    // La liste ci-dessus est de la donnée de test : sans cet ancrage, elle survivrait à un
    // changement de teinte dans un composant et mesurerait un plateau imaginaire.
    const sansEspace = (s: string) => s.replace(/\s+/g, "");
    for (const repere of REPERES) {
      const source = sansEspace(lire(repere.source)).toLowerCase();
      const attendus = repere.litteral ?? [
        repere.alpha === 1
          ? repere.couleur
          : // Les valeurs semi-transparentes sont écrites en `rgba()` dans les composants.
            `rgba(${[0, 2, 4]
              .map((i) => parseInt(repere.couleur.slice(1 + i, 3 + i), 16))
              .join(",")},${repere.alpha})`,
      ];
      for (const attendu of attendus) {
        expect(
          source.includes(sansEspace(attendu).toLowerCase()),
          `${repere.nom} : « ${attendu} » introuvable dans ${repere.source}`,
        ).toBe(true);
      }
    }
  });

  it("le décor par défaut est celui du plateau d'origine, teintes comprises", () => {
    // `j-plateau-layout` avait livré `radial-gradient(…, #0E2A1E, #06120B)`. Le défaut doit
    // reprendre ces deux teintes : sinon ce lot, qui ne devait qu'ajouter des décors, changerait
    // l'apparence du jeu pour tout le monde sans que personne l'ait demandé.
    expect(DECOR_DEFAUT).toBe("arene");
    expect(DECORS[DECOR_DEFAUT]!.teintes.tapis).toBe("#0E2A1E");
    expect(DECORS[DECOR_DEFAUT]!.teintes.fond).toBe("#06120B");
  });

  it("les constantes de la nuit sont celles qu'applique le CSS", () => {
    // `teintesNuit()` est le miroir d'un `color-mix` écrit dans `globals.css`. Si l'un des deux
    // bouge sans l'autre, les douze mesures ci-dessus portent sur des couleurs qui ne s'affichent
    // nulle part.
    const css = lire("src/app/globals.css");
    const part = `${Math.round(NUIT_PART * 100)}%`;
    expect(css, `la part de nuit (${part}) est absente du color-mix de globals.css`).toContain(
      `${part}, ${NUIT_APPOINT.toLowerCase()}`,
    );
  });
});
