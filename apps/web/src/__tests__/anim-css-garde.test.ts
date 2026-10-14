import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Garde du socle d'animation (lot `j-anim-socle`) : **les images-clés n'animent que `transform` et
 * `opacity`**.
 *
 * Pourquoi une garde statique plutôt qu'une consigne dans la documentation : c'est cette seule
 * propriété qui fait tenir le plancher d'images par seconde (`PLANCHER_FPS`) sur un téléphone
 * d'entrée de gamme. `transform` et `opacity` se composent sans refaire la mise en page ni
 * repeindre ; animer `width`, `height`, `top`, `box-shadow` ou `filter` remet le fil principal au
 * travail à chaque image, et le plancher tombe — sur l'appareil de référence, pas sur la machine de
 * celui qui écrit le CSS, où ça ne se voit pas.
 *
 * Le test de fluidité (`e2e/anim-fluidite.spec.ts`) **mesure** le résultat ; celui-ci garde la
 * **cause**. Les deux sont nécessaires : un e2e ne tourne qu'en CI, et une mesure au navigateur ne
 * dit jamais *pourquoi* elle vient de tomber.
 */

// `process.cwd()` vaut `apps/web` — vitest y est lancé par `pnpm --filter @pbm/web test`, comme
// les specs Playwright résolvent déjà leurs chemins (`e2e/plateau-responsive.spec.ts`).
const CSS = readFileSync(path.resolve(process.cwd(), "src/app/globals.css"), "utf-8");

/** Les propriétés qu'un navigateur peut animer sur le compositeur, sans mise en page ni peinture. */
const COMPOSABLES = new Set(["transform", "opacity", "translate", "scale", "rotate"]);

/** Extrait les blocs `@keyframes <nom> { … }` du CSS, par comptage d'accolades. */
function imagesCles(css: string): { nom: string; corps: string }[] {
  const blocs: { nom: string; corps: string }[] = [];
  const debut = /@keyframes\s+([\w-]+)\s*\{/g;
  let m: RegExpExecArray | null;
  while ((m = debut.exec(css)) !== null) {
    let profondeur = 1;
    let i = debut.lastIndex;
    while (i < css.length && profondeur > 0) {
      if (css[i] === "{") profondeur += 1;
      else if (css[i] === "}") profondeur -= 1;
      i += 1;
    }
    blocs.push({ nom: m[1] ?? "", corps: css.slice(debut.lastIndex, i - 1) });
  }
  return blocs;
}

describe("globals.css — images-clés d'animation du plateau", () => {
  const blocs = imagesCles(CSS).filter((b) => b.nom.startsWith("pbm-anim"));

  it("le socle déclare bien ses images-clés (sinon cette garde ne garderait rien)", () => {
    expect(blocs.length).toBeGreaterThan(0);
    expect(blocs.map((b) => b.nom)).toContain("pbm-anim-pulse");
  });

  it.each(blocs.map((b) => [b.nom, b.corps] as const))(
    "@keyframes %s n'anime que des propriétés composables",
    (nom, corps) => {
      const proprietes = Array.from(corps.matchAll(/([a-z-]+)\s*:/g)).flatMap((m) =>
        m[1] ? [m[1]] : [],
      );
      expect(proprietes.length, `${nom} : aucune propriété animée ?`).toBeGreaterThan(0);
      const interdites = proprietes.filter((p) => !COMPOSABLES.has(p));
      expect(
        interdites,
        `@keyframes ${nom} anime ${interdites.join(", ")} : hors du compositeur, le plancher d'images par seconde tombe sur un téléphone d'entrée de gamme`,
      ).toEqual([]);
    },
  );

  it("la durée de l'animation vient du socle, bornée, et jamais du CSS", () => {
    // `--pbm-anim-duree` est posée par le composant à partir de `dureeEffective` : le mode
    // accéléré et le mode réduit sont donc respectés sans toucher au CSS.
    expect(CSS).toContain("var(--pbm-anim-duree");
  });
});
