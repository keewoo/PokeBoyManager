import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { SPECS, type Couche, type GesteCarte } from "@/lib/game/anim-types";

/**
 * Parité **table ↔ CSS** des effets typés (lot `j-anim-attaques-typees`).
 *
 * `SPECS` est de la donnée : une ligne y dit « ce type se compose de la couche `nappe` et d'un
 * `recul` ». Rien, dans TypeScript, ne garantit que cette couche existe dans `globals.css`. Et le
 * mode de panne est le pire qui soit : **l'effet s'affiche, simplement il ne montre rien** — un
 * `<i>` sans dégradé et sans image-clé est un carré transparent. L'écran a l'air de marcher, le
 * joueur ne voit rien, et aucun test de rendu ne tombe.
 *
 * Cette garde ferme ce trou dans les deux sens : chaque couche, chaque geste et chaque teinte
 * citée par la table doit exister dans le CSS, et le fautif est **nommé**.
 *
 * ⚠️ Elle ne remplace pas `anim-css-garde.test.ts`, qui garde une tout autre chose : que ces
 * images-clés n'animent que `transform` et `opacity`. Les images-clés de ce lot sont nommées
 * `pbm-anim-fx-*` précisément pour tomber sous cette garde-là — un autre préfixe les en aurait
 * sorties, ce qu'un garde-fou interdit de faire.
 */

// `process.cwd()` vaut `apps/web` — comme `anim-css-garde.test.ts`.
const CSS = readFileSync(path.resolve(process.cwd(), "src/app/globals.css"), "utf-8");

/** Toutes les couches citées par la table, sans doublon. */
const COUCHES: Couche[] = [...new Set(Object.values(SPECS).flatMap((s) => s.couches))];

/** Tous les gestes de carte cités par la table, hors « aucun ». */
const GESTES: GesteCarte[] = [
  ...new Set(Object.values(SPECS).map((s) => s.gesteCarte)),
].filter((g): g is GesteCarte => g !== "aucun");

describe("globals.css — les couches et gestes cités par SPECS existent vraiment", () => {
  it("la table n'est pas vide (sinon cette garde ne garderait rien)", () => {
    expect(Object.keys(SPECS).length).toBeGreaterThanOrEqual(10);
    expect(COUCHES.length).toBeGreaterThan(0);
    expect(GESTES.length).toBeGreaterThan(0);
  });

  it.each(COUCHES)("la couche « %s » a son style ET son image-clé", (couche) => {
    // `particules` est rendue par une gerbe de `.pbm-fx-particule`, pas par `.pbm-fx-couche`.
    const selecteur =
      couche === "particules" ? ".pbm-fx-particule" : `[data-couche="${couche}"]`;
    expect(CSS, `aucun style pour la couche « ${couche} »`).toContain(selecteur);
    const imageCle = couche === "particules" ? "pbm-anim-fx-particule" : `pbm-anim-fx-${couche}`;
    expect(CSS, `@keyframes ${imageCle} manquante : la couche serait un carré transparent`).toContain(
      `@keyframes ${imageCle}`,
    );
  });

  it.each(GESTES)("le geste de carte « %s » a son sélecteur ET son image-clé", (geste) => {
    expect(CSS, `aucun sélecteur pour le geste « ${geste} »`).toContain(
      `[data-fx-geste="${geste}"]`,
    );
    expect(CSS, `@keyframes pbm-anim-fx-${geste} manquante`).toContain(
      `@keyframes pbm-anim-fx-${geste}`,
    );
  });

  it("la secousse du plateau est câblée sur l'arène, pour les types qui la demandent", () => {
    expect(Object.values(SPECS).some((s) => s.secousse)).toBe(true);
    expect(CSS).toContain("[data-fx-secousse]");
    expect(CSS).toContain("@keyframes pbm-anim-fx-secousse");
  });

  it("la trace résiduelle a son style et son image-clé", () => {
    expect(Object.values(SPECS).some((s) => s.trace)).toBe(true);
    expect(CSS).toContain(".pbm-fx-trace");
    expect(CSS).toContain("@keyframes pbm-anim-fx-trace");
  });

  it.each(Object.values(SPECS).map((s) => [s.cle, s.libelle] as const))(
    "le type « %s » (%s) a sa teinte — sinon son effet serait invisible",
    (cle) => {
      expect(CSS, `aucune teinte pour [data-fx="${cle}"]`).toContain(`.pbm-fx[data-fx="${cle}"]`);
    },
  );

  it("chaque palier d'intensité a son amplitude : c'est là que l'intensité devient visible", () => {
    for (const palier of ["echec", "faible", "moyen", "fort"]) {
      expect(CSS, `aucune amplitude pour le palier « ${palier} »`).toContain(
        `[data-palier="${palier}"]`,
      );
    }
  });

  it("les durées viennent du module, jamais du CSS", () => {
    // Comme le socle : `--pbm-fx-duree` et `--pbm-fx-trace` sont posées par le composant depuis
    // `effetAttaque`. Le mode accéléré et la borne d'une seconde sont donc respectés sans toucher
    // au CSS — et une valeur en dur ici les contournerait en silence.
    expect(CSS).toContain("var(--pbm-fx-duree");
    expect(CSS).toContain("var(--pbm-fx-trace");
  });
});
