import { describe, expect, it } from "vitest";

import {
  agisseurDepuisEvenements,
  ELEMENTS,
  ETATS,
  nombreCompteurs,
  styleElement,
  visuelEtat,
} from "./indicateurs";

describe("styleElement — type d'énergie, jamais la couleur seule", () => {
  it("rend une abréviation ET un nom pour chaque type connu (signe + couleur)", () => {
    for (const code of Object.keys(ELEMENTS)) {
      const s = styleElement(code);
      expect(s.abbr.length).toBeGreaterThan(0); // le signe non coloré existe toujours
      expect(s.label.length).toBeGreaterThan(0);
      expect(s.couleur).toMatch(/^#/);
    }
  });

  it("retombe sur un repère NEUTRE nommé pour un type inconnu ou absent (D9, jamais deviné)", () => {
    for (const entree of [null, undefined, "licorne"]) {
      const s = styleElement(entree as string | null | undefined);
      expect(s.code).toBe("inconnu");
      expect(s.abbr).toBe("?");
      expect(s.label).toBe("Type inconnu");
    }
  });
});

describe("visuelEtat — un état montré par une icône, pas seulement par l'orientation", () => {
  it("donne une icône et un nom aux cinq états spéciaux (R-11.1)", () => {
    for (const cle of Object.keys(ETATS)) {
      const v = visuelEtat(cle);
      expect(v.icone.length).toBeGreaterThan(0);
      expect(v.label.length).toBeGreaterThan(0);
    }
  });

  it("un état inconnu reste visible et nommé (jamais masqué en silence)", () => {
    const v = visuelEtat("maudit");
    expect(v.label).toBe("maudit");
    expect(v.icone).toBe("❔");
  });
});

describe("nombreCompteurs — 1 compteur = 10 dégâts (R-10.4)", () => {
  it("convertit des dégâts en compteurs, plancher à 0", () => {
    expect(nombreCompteurs(0)).toBe(0);
    expect(nombreCompteurs(20)).toBe(2);
    expect(nombreCompteurs(10)).toBe(1);
    expect(nombreCompteurs(-5)).toBe(0);
  });
});


describe("agisseurDepuisEvenements — le Pokémon qui vient d'agir, jamais inventé", () => {
  it("retient le dernier événement qui désigne un Pokémon (pokemon ou base)", () => {
    const evts = [
      { type: "pokemon_pose", donnees: { joueur: "a", pokemon: "p1" } },
      { type: "evolution", donnees: { joueur: "a", base: "p2" } },
    ];
    expect(agisseurDepuisEvenements(evts)).toBe("p2");
  });

  it("rend null quand aucun événement ne désigne de Pokémon (ex. piocher)", () => {
    const evts = [{ type: "cartes_piochees", donnees: { joueur: "a", nombre: 1 } }];
    expect(agisseurDepuisEvenements(evts)).toBeNull();
    expect(agisseurDepuisEvenements([])).toBeNull();
  });
});
