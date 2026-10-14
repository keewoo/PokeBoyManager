import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { SEUIL_TEXTE, contraste } from "@/lib/a11y/contraste";
import { ELEMENTS, styleElement } from "@/lib/game/indicateurs";

/**
 * **Contraste** des repères du jeu (lot `j-accessibilite-jeu`) — vérifié par le calcul, pas à l'œil.
 *
 * Pourquoi un test et non un audit de navigateur : l'audit `axe` en jsdom ne sait **pas** calculer
 * un contraste (il n'y a pas de rendu), et l'audit du navigateur ne voit que les pastilles
 * réellement présentes à l'écran au moment du test — jamais les onze types d'énergie. Ici on les
 * mesure tous, à la source, en une seconde. Les couleurs vivent en dur dans
 * `lib/game/indicateurs.ts` (abréviation sur fond coloré) : c'est donc là qu'il faut mesurer.
 *
 * Le seuil est **4,5:1** (WCAG 2.2, 1.4.3 « Contraste minimum », niveau AA) pour du petit texte :
 * une abréviation de type sur sa pastille est exactement ça. On ne retient pas 3:1 (réservé au
 * grand texte), parce que ces abréviations sont minuscules sur le plateau.
 */

// Le calcul vit dans `@/lib/a11y/contraste` depuis le lot `j-arene-decors`, qui en a besoin pour
// mesurer les décors : deux copies d'une formule WCAG, c'est deux occasions de la corriger à
// moitié. Le seuil garde son nom local, utilisé dans les messages d'échec ci-dessous.
const SEUIL_AA = SEUIL_TEXTE;

describe("contraste des repères du jeu", () => {
  it("vérifie son propre calcul sur les deux extrêmes connus", () => {
    // Sans cette garde, une erreur dans `luminance` rendrait tous les tests suivants complaisants.
    expect(contraste("#000000", "#FFFFFF")).toBeCloseTo(21, 1);
    expect(contraste("#777777", "#777777")).toBeCloseTo(1, 2);
  });

  it("chaque type d'énergie a son abréviation lisible sur sa pastille (AA)", () => {
    const fautifs = Object.values(ELEMENTS)
      .map((e) => ({ code: e.code, ratio: contraste(e.couleur, e.texte) }))
      .filter((m) => m.ratio < SEUIL_AA);
    expect(
      fautifs,
      `contraste insuffisant (< ${SEUIL_AA}:1) : ` +
        fautifs.map((f) => `${f.code} à ${f.ratio.toFixed(2)}:1`).join(", "),
    ).toEqual([]);
  });

  it("le repère neutre d'un type inconnu est lisible lui aussi", () => {
    // D9 : un type inconnu se montre comme tel — encore faut-il qu'on puisse le lire.
    const neutre = styleElement(null);
    expect(contraste(neutre.couleur, neutre.texte)).toBeGreaterThanOrEqual(SEUIL_AA);
  });

  it("les jetons de couleur de type du CSS existent pour les onze types", () => {
    // `globals.css` porte une seconde palette (`--type-*`, utilisée par les cartes de
    // remplacement). Elle n'a pas à être identique à celle des pastilles — les usages diffèrent —
    // mais elle doit couvrir les mêmes types : un type sans jeton se dessinerait transparent.
    const css = readFileSync(
      path.resolve(__dirname, "../app/globals.css"),
      "utf-8",
    );
    for (const code of Object.keys(ELEMENTS)) {
      expect(css, `jeton --type-${code} absent de globals.css`).toContain(`--type-${code}:`);
    }
  });
});
