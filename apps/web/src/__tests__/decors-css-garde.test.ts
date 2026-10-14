import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { DECORS } from "@/lib/game/decors";

/**
 * Garde du **CSS des décors** (lot `j-arene-decors`) : le fond réellement peint doit être celui
 * que la table décrit, et il doit rester gratuit.
 *
 * Deux choses que seul un test peut tenir :
 *
 * 1. **La table et la feuille de style ne peuvent pas diverger.** Les teintes vivent en double —
 *    en TypeScript (pour les mesurer) et en CSS (pour les peindre). Sans cette garde, corriger une
 *    teinte d'un seul côté laisserait le test de contraste mesurer une couleur qui ne s'affiche
 *    nulle part : un test vert sur un décor faux.
 * 2. **Aucun décor ne charge d'image.** C'est le critère « le poids des décors entre dans le
 *    budget de la partie », et c'est la seule forme vérifiable qu'il puisse prendre : un `url()`
 *    ajouté un jour « juste pour une texture » coûterait des centaines de kilooctets par décor.
 */

const CSS = readFileSync(path.resolve(__dirname, "../app/globals.css"), "utf-8");

/** Le bloc d'un sélecteur, accolades comprises — `null` si le sélecteur est absent. */
function bloc(selecteur: string): string | null {
  const i = CSS.indexOf(selecteur + " {");
  if (i === -1) return null;
  const fin = CSS.indexOf("}", i);
  return fin === -1 ? null : CSS.slice(i, fin);
}

describe("garde du CSS des décors", () => {
  it("chaque décor de la table a son bloc de teintes dans globals.css", () => {
    for (const cle of Object.keys(DECORS)) {
      expect(bloc(`[data-decor="${cle}"]`), `aucun bloc CSS pour le décor « ${cle} »`).not.toBeNull();
    }
  });

  it("les quatre teintes de chaque décor sont exactement celles de la table", () => {
    const ecarts: string[] = [];
    for (const [cle, decor] of Object.entries(DECORS)) {
      const corps = bloc(`[data-decor="${cle}"]`) ?? "";
      for (const [role, hex] of Object.entries(decor.teintes)) {
        // Le CSS est écrit en minuscules (prettier), la table en majuscules : on compare la valeur,
        // pas sa casse.
        const attendu = `--pbm-decor-${role}-base: ${hex.toLowerCase()};`;
        if (!corps.toLowerCase().includes(attendu)) {
          ecarts.push(`${cle}/${role} : « ${attendu} » absent du bloc CSS`);
        }
      }
    }
    expect(ecarts, `la table et le CSS divergent :\n  ${ecarts.join("\n  ")}`).toEqual([]);
  });

  it("le CSS ne déclare aucun décor que la table ignore", () => {
    // L'inverse du test précédent : un décor peint mais absent de la table échapperait à toute
    // mesure de contraste, et serait pourtant atteignable par un réglage enregistré.
    const peints = [...CSS.matchAll(/\[data-decor="([a-z0-9_-]+)"\]/g)].map((m) => m[1]!);
    const inconnus = [...new Set(peints)].filter((cle) => !(cle in DECORS));
    expect(inconnus, `décors peints mais absents de la table : ${inconnus.join(", ")}`).toEqual([]);
  });

  it("aucun décor ne charge d'image : le poids réseau des décors est nul", () => {
    const fautifs: string[] = [];
    for (const cle of Object.keys(DECORS)) {
      const corps = bloc(`[data-decor="${cle}"]`) ?? "";
      if (/url\(/i.test(corps)) fautifs.push(cle);
    }
    // Le bloc commun qui compose les dégradés, et la vignette de l'écran de choix.
    for (const selecteur of ["[data-decor]", ".pbm-decor-vignette"]) {
      const corps = bloc(selecteur) ?? "";
      if (/url\(/i.test(corps)) fautifs.push(selecteur);
    }
    expect(
      fautifs,
      `ces décors chargent une image, donc pèsent dans le budget de la partie : ${fautifs.join(", ")}`,
    ).toEqual([]);
  });

  it("le fond de l'arène n'est plus écrit en dur dans le composant", () => {
    // Le plateau portait son dégradé dans une classe Tailwind arbitraire. S'il y revenait, le
    // décor n'aurait plus aucun effet visible — et aucun autre test ne s'en apercevrait, puisque
    // `data-decor` serait toujours posé.
    const board = readFileSync(
      path.resolve(__dirname, "../components/game/game-board.tsx"),
      "utf-8",
    );
    expect(board).not.toContain("bg-[radial-gradient");
    expect(board).toContain("data-decor={decor}");
  });

  it("la vignette de l'écran de choix est peinte par le même code que l'arène", () => {
    // Si la vignette avait ses propres dégradés, elle pourrait montrer un décor que la partie ne
    // jouera pas — le pire défaut possible pour un écran de choix.
    const commun = bloc("[data-decor]") ?? "";
    expect(commun).toContain("background-image:");
    const vignette = bloc(".pbm-decor-vignette") ?? "";
    expect(vignette, "la vignette redéfinit son fond au lieu de l'hériter").not.toContain(
      "background-image:",
    );
  });
});
