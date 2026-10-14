import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  COUCHES_UTILISEES,
  GENRES_MOMENT,
  GESTES_UTILISES,
  MOMENTS,
} from "@/lib/game/anim-moments";

/**
 * Garde des **moments clés** (lot `j-anim-evolution-ko`) : la table et le CSS ne peuvent pas
 * divergir.
 *
 * Pourquoi une garde statique plutôt qu'une relecture attentive : la table `MOMENTS` est faite pour
 * qu'ajouter un moment soit **une ligne**. C'est une qualité, et c'est aussi le piège — une ligne
 * qui nomme une couche sans image-clé produit un moment **muet**. Rien ne plante, rien ne s'affiche,
 * et l'écran continue d'avoir l'air de marcher. Un moment qu'on croit joué et qui ne l'est pas est
 * exactement le genre de panne silencieuse que ce dépôt s'interdit.
 *
 * Le test nomme la ligne fautive, pas seulement l'absence : c'est ce qui en fait une garde utile.
 */

// `process.cwd()` vaut `apps/web` — comme les autres gardes statiques de ce dossier.
const CSS = readFileSync(path.resolve(process.cwd(), "src/app/globals.css"), "utf-8");

describe("globals.css — les moments clés", () => {
  it.each(COUCHES_UTILISEES)("la couche %s a son sélecteur et son image-clé", (couche) => {
    const genres = GENRES_MOMENT.filter((g) =>
      MOMENTS[g].phases.some((p) => p.couches.includes(couche)),
    );
    expect(
      CSS,
      `couche "${couche}" (utilisée par ${genres.join(", ")}) : aucun sélecteur [data-couche="${couche}"] dans le bloc des moments — elle ne dessinerait rien`,
    ).toContain(`.pbm-m-couche[data-couche="${couche}"]`);
    expect(
      CSS,
      `couche "${couche}" (utilisée par ${genres.join(", ")}) : @keyframes pbm-anim-fx-m-${couche} manquante — la couche serait immobile`,
    ).toContain(`@keyframes pbm-anim-fx-m-${couche}`);
  });

  it.each(GESTES_UTILISES)("le geste %s a son image-clé", (geste) => {
    const genres = GENRES_MOMENT.filter((g) => MOMENTS[g].phases.some((p) => p.geste === geste));
    expect(
      CSS,
      `geste "${geste}" (utilisé par ${genres.join(", ")}) : @keyframes pbm-anim-fx-m-${geste} manquante — l'objet ne bougerait pas`,
    ).toContain(`@keyframes pbm-anim-fx-m-${geste}`);
  });

  it("les images-clés des moments portent le préfixe gardé (`pbm-anim-`)", () => {
    // Un autre préfixe les ferait échapper à `anim-css-garde.test.ts`, qui est ce qui garantit
    // qu'elles n'animent que `transform` et `opacity`. Contourner une garde en renommant est
    // précisément ce qu'une garde interdit de faire.
    const noms = Array.from(CSS.matchAll(/@keyframes\s+([\w-]+)/g)).flatMap((m) =>
      m[1] ? [m[1]] : [],
    );
    const moments = noms.filter((n) => n.includes("-m-"));
    expect(moments.length).toBeGreaterThan(0);
    for (const n of moments) expect(n, `${n} hors du préfixe gardé`).toMatch(/^pbm-anim-fx-m-/);
  });

  it("le rythme vient du module, jamais du CSS", () => {
    // `--pbm-m-debut` et `--pbm-m-duree` sont posées par le composant à partir des phases
    // calculées : la compression d'une rafale se fait donc sans toucher à cette feuille.
    expect(CSS).toContain("var(--pbm-m-duree");
    expect(CSS).toContain("var(--pbm-m-debut");
    expect(CSS).toContain("var(--pbm-m-revelation");
  });

  it("la pose finale d'une pièce n'apparaît qu'à la révélation", () => {
    // Le cœur du critère n°3 côté feuille de style : les deux faces sont identiques (opacité
    // nulle) jusqu'à `--pbm-m-revelation`. Si cette animation perdait son retard, le résultat
    // s'afficherait dès la première image de la rotation.
    const bloc = CSS.slice(CSS.indexOf('.pbm-m-objet[data-face]::after'));
    const regle = bloc.slice(0, bloc.indexOf("}"));
    expect(regle).toContain("opacity: 0");
    expect(regle).toContain("var(--pbm-m-revelation");
  });
});
