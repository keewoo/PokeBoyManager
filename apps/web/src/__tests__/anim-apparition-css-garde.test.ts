import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { CALQUES_UTILISES } from "@/lib/game/anim-apparition";

/**
 * Parité table ↔ CSS pour l'apparition du Pokémon (lot `j-anim-pokemon-apparition`).
 *
 * Même rôle que `anim-types-css-garde.test.ts` et `anim-moments-css-garde.test.ts` : la table
 * TypeScript et la feuille de style décrivent le même effet à deux endroits, et rien ne les tient
 * ensemble sauf ce test. Ajouter un calque sans son image-clé donnerait un calque **immobile** —
 * invisible en revue de code, invisible en type-check, et visible seulement par le joueur.
 *
 * La garde générale (`anim-css-garde.test.ts`) couvre déjà le reste : nos images-clés s'appellent
 * `pbm-anim-fx-a-*`, donc elles tombent sous sa règle « `transform` et `opacity` uniquement ».
 * C'est la raison du préfixe — un autre nom les en aurait sorties.
 */
const CSS = readFileSync(path.resolve(process.cwd(), "src/app/globals.css"), "utf8");

describe("apparition : chaque calque de la table existe dans le CSS", () => {
  it.each([...CALQUES_UTILISES])("le calque « %s » a son sélecteur et son image-clé", (calque) => {
    expect(CSS).toContain(`[data-calque="${calque}"]`);
    expect(CSS).toContain(`@keyframes pbm-anim-fx-a-${calque}`);
  });
});

describe("apparition : les conventions qui la gardent sous la garde générale", () => {
  it("préfixe toutes ses images-clés par `pbm-anim-fx-a-`", () => {
    const noms = [...CSS.matchAll(/@keyframes\s+([\w-]+)/g)].map((m) => m[1] ?? "");
    const siennes = noms.filter((n) => n.includes("-fx-a-"));
    expect(siennes.length).toBeGreaterThan(0);
    for (const nom of siennes) {
      expect(nom.startsWith("pbm-anim-fx-a-")).toBe(true);
    }
  });

  it("pose la racine, les calques et les particules", () => {
    expect(CSS).toContain(".pbm-a {");
    expect(CSS).toContain(".pbm-a-calque {");
    expect(CSS).toContain(".pbm-a-particule {");
  });

  it("tire sa durée du module, jamais d'une valeur écrite dans la feuille", () => {
    expect(CSS).toContain("var(--pbm-a-duree)");
    expect(CSS).toContain("var(--pbm-a-amplitude");
    expect(CSS).toContain("var(--pbm-a-elevation");
  });

  it("n'anime ni `filter` ni `mask` — ils sont posés en statique, hors image-clé", () => {
    // `mask-image` sert au halo pour épouser la silhouette : c'est du CSS statique, il ne coûte
    // rien par image. L'animer remettrait le fil principal au travail à chaque cadre et ferait
    // tomber le plancher de 30 images/s que `e2e/anim-fluidite.spec.ts` mesure.
    const blocs = [...CSS.matchAll(/@keyframes\s+pbm-anim-fx-a-[\w-]+\s*\{([\s\S]*?)\n\}/g)];
    expect(blocs.length).toBeGreaterThan(0);
    for (const bloc of blocs) {
      const corps = bloc[1] ?? "";
      expect(corps).not.toMatch(/\bfilter\s*:/);
      expect(corps).not.toMatch(/\bmask[\w-]*\s*:/);
      expect(corps).not.toMatch(/\bwidth\s*:|\bheight\s*:|\btop\s*:|\bleft\s*:/);
    }
  });
});
