import { describe, expect, it } from "vitest";

import {
  ANIMATIONS,
  ANIMATIONS_COMPLETES,
  ANIMATIONS_REDUITES,
  CONFORT_DEFAUT,
  ECHELLE_TEXTE,
  TAILLES_TEXTE,
  attributsConfort,
  libelleAnimations,
  libelleTailleTexte,
  normaliserConfort,
} from "@/lib/game/confort";

/**
 * Les réglages de confort, côté données pures (lot `j-accessibilite-jeu`).
 *
 * Ce qui est éprouvé ici est exactement ce qui casse en silence autrement : un cache local écrit par
 * une version précédente, un champ absent, une valeur hors vocabulaire. Dans chacun de ces cas, le
 * réglage doit retomber **champ par champ** sur son défaut — jamais annuler les deux autres.
 */
describe("réglages de confort (pur)", () => {
  it("part des défauts du produit : animé, texte normal, temps DJ4", () => {
    expect(CONFORT_DEFAUT).toEqual({
      animations: ANIMATIONS_COMPLETES,
      taille_texte: "normale",
      temps_rallonge: false,
    });
  });

  it("normalise l'absence totale de réglages", () => {
    expect(normaliserConfort(null)).toEqual(CONFORT_DEFAUT);
    expect(normaliserConfort(undefined)).toEqual(CONFORT_DEFAUT);
    expect(normaliserConfort({})).toEqual(CONFORT_DEFAUT);
  });

  it("garde les champs valides et ne corrige que l'invalide", () => {
    // Le cas réel : un cache écrit avant qu'un vocabulaire change. « reduites » est bon, la taille
    // ne l'est pas — couper les animations ne doit pas être annulé pour autant.
    expect(
      normaliserConfort({ animations: "reduites", taille_texte: "gigantesque", temps_rallonge: 1 }),
    ).toEqual({
      animations: ANIMATIONS_REDUITES,
      taille_texte: "normale",
      // `1` n'est pas un booléen : on ne devine pas une intention à partir d'un entier.
      temps_rallonge: false,
    });
  });

  it("publie les attributs que le CSS interprète", () => {
    expect(attributsConfort({ ...CONFORT_DEFAUT, animations: ANIMATIONS_REDUITES })).toEqual({
      "data-anim": "reduites",
      "data-texte": "normale",
    });
  });

  it("donne une échelle croissante et jamais réductrice", () => {
    // Un réglage d'accessibilité ne doit pas pouvoir RÉDUIRE le texte sous sa taille normale.
    expect(ECHELLE_TEXTE.normale).toBe(1);
    expect(ECHELLE_TEXTE.grande).toBeGreaterThan(ECHELLE_TEXTE.normale);
    expect(ECHELLE_TEXTE.tres_grande).toBeGreaterThan(ECHELLE_TEXTE.grande);
    for (const taille of TAILLES_TEXTE) expect(ECHELLE_TEXTE[taille]).toBeGreaterThanOrEqual(1);
  });

  it("nomme chaque valeur en français, sans laisser passer un code brut", () => {
    for (const valeur of ANIMATIONS) {
      expect(libelleAnimations(valeur)).not.toBe(valeur);
      expect(libelleAnimations(valeur)).toMatch(/[a-zéèà]/);
    }
    for (const taille of TAILLES_TEXTE) {
      // « tres_grande » ne doit jamais s'afficher tel quel : un souligné n'est pas du français.
      expect(libelleTailleTexte(taille)).not.toContain("_");
    }
  });
});
