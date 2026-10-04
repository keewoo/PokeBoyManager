import { describe, expect, it } from "vitest";

import {
  choixParDefaut,
  deplacer,
  filtrerOptions,
  normaliser,
  reponseValide,
  typesPresents,
} from "./decision";
import type { VueDemande, VueOptionCarte } from "@/lib/game/plateau";

function demande(over: Partial<VueDemande> = {}): VueDemande {
  return {
    id: "d0",
    destinataire: "moi",
    categorie: "cartes",
    libelle: "Choisis des cartes",
    regle: "R-9.3",
    obligatoire: true,
    minimum: 1,
    maximum: 1,
    source: { libelle: "Professeur" },
    delai_ms: 30000,
    temps_restant_ms: 30000,
    options: ["c1", "c2", "c3"],
    ...over,
  };
}

function carte(id: string, nom: string, type: string | null): VueOptionCarte {
  return { id, ref: `ref-${id}`, nom, type };
}

describe("normaliser", () => {
  it("ignore la casse et les accents (recherche indulgente)", () => {
    expect(normaliser("Dracaufeu")).toBe("dracaufeu");
    expect(normaliser("Poké Ball")).toBe("poke ball");
    expect(normaliser("ÉÈÊ")).toBe("eee");
  });
});

describe("filtrerOptions", () => {
  const options = [
    carte("c1", "Dracaufeu", "fire"),
    carte("c2", "Bulbizarre", "grass"),
    carte("c3", "Salamèche", "fire"),
  ];

  it("filtre par nom sans accent ni casse", () => {
    expect(filtrerOptions(options, "salameche", null).map((o) => o.id)).toEqual(["c3"]);
  });

  it("filtre par type", () => {
    expect(filtrerOptions(options, "", "fire").map((o) => o.id)).toEqual(["c1", "c3"]);
  });

  it("combine texte et type, et garde l'ordre d'origine", () => {
    expect(filtrerOptions(options, "a", "fire").map((o) => o.id)).toEqual(["c1", "c3"]);
  });

  it("recherche aussi par référence", () => {
    expect(filtrerOptions(options, "ref-c2", null).map((o) => o.id)).toEqual(["c2"]);
  });
});

describe("typesPresents", () => {
  it("rend les types distincts dans l'ordre d'apparition, sans les inconnus", () => {
    const options = [
      carte("c1", "A", "fire"),
      carte("c2", "B", null),
      carte("c3", "C", "grass"),
      carte("c4", "D", "fire"),
    ];
    expect(typesPresents(options)).toEqual(["fire", "grass"]);
  });
});

describe("deplacer", () => {
  it("déplace un élément vers une nouvelle position (copie)", () => {
    const liste = ["a", "b", "c"];
    expect(deplacer(liste, 0, 2)).toEqual(["b", "c", "a"]);
    expect(liste).toEqual(["a", "b", "c"]); // l'original n'est pas muté
  });

  it("rend la liste inchangée pour un index hors bornes ou identique", () => {
    expect(deplacer(["a", "b"], 0, 0)).toEqual(["a", "b"]);
    expect(deplacer(["a", "b"], -1, 1)).toEqual(["a", "b"]);
    expect(deplacer(["a", "b"], 0, 5)).toEqual(["a", "b"]);
  });
});

describe("choixParDefaut (miroir de reponse_par_defaut)", () => {
  it("facultatif → abandon, quelle que soit la catégorie", () => {
    expect(choixParDefaut(demande({ obligatoire: false }))).toEqual([]);
  });

  it("carte → première option", () => {
    expect(choixParDefaut(demande({ categorie: "carte", maximum: 1 }))).toEqual(["c1"]);
  });

  it("cartes → les `minimum` premières", () => {
    expect(choixParDefaut(demande({ categorie: "cartes", minimum: 2, maximum: 3 }))).toEqual([
      "c1",
      "c2",
    ]);
  });

  it("ordre → l'ordre identité", () => {
    expect(choixParDefaut(demande({ categorie: "ordre" }))).toEqual(["c1", "c2", "c3"]);
  });

  it("oui_non → première option, sinon « non »", () => {
    expect(choixParDefaut(demande({ categorie: "oui_non", options: ["oui", "non"] }))).toEqual([
      "oui",
    ]);
    expect(choixParDefaut(demande({ categorie: "oui_non", options: [] }))).toEqual(["non"]);
  });

  it("nombre → la borne minimum", () => {
    expect(choixParDefaut(demande({ categorie: "nombre", minimum: 2, maximum: 5, options: [] }))).toEqual([
      "2",
    ]);
  });
});

describe("reponseValide (miroir de valider_reponse)", () => {
  it("abandon : permis si facultatif, refusé si obligatoire", () => {
    expect(reponseValide(demande({ obligatoire: false }), [])).toBe(true);
    expect(reponseValide(demande({ obligatoire: true }), [])).toBe(false);
  });

  it("refuse les doublons", () => {
    expect(reponseValide(demande({ categorie: "cartes", maximum: 2 }), ["c1", "c1"])).toBe(false);
  });

  it("carte : exactement une option de l'ensemble", () => {
    const d = demande({ categorie: "carte", maximum: 1 });
    expect(reponseValide(d, ["c2"])).toBe(true);
    expect(reponseValide(d, ["inconnu"])).toBe(false);
    expect(reponseValide(d, ["c1", "c2"])).toBe(false);
  });

  it("cartes : cardinalité dans [minimum, maximum] et ids de l'ensemble", () => {
    const d = demande({ categorie: "cartes", minimum: 1, maximum: 2 });
    expect(reponseValide(d, ["c1"])).toBe(true);
    expect(reponseValide(d, ["c1", "c2"])).toBe(true);
    expect(reponseValide(d, ["c1", "c2", "c3"])).toBe(false); // au-delà du maximum
    expect(reponseValide(d, ["c1", "x"])).toBe(false); // hors ensemble
  });

  it("ordre : une permutation complète de l'ensemble", () => {
    const d = demande({ categorie: "ordre" });
    expect(reponseValide(d, ["c3", "c1", "c2"])).toBe(true);
    expect(reponseValide(d, ["c1", "c2"])).toBe(false); // incomplet
  });

  it("oui_non : « oui » ou « non »", () => {
    const d = demande({ categorie: "oui_non", options: ["oui", "non"] });
    expect(reponseValide(d, ["oui"])).toBe(true);
    expect(reponseValide(d, ["peut-etre"])).toBe(false);
  });

  it("nombre : un entier dans [minimum, maximum]", () => {
    const d = demande({ categorie: "nombre", minimum: 1, maximum: 3, options: [] });
    expect(reponseValide(d, ["2"])).toBe(true);
    expect(reponseValide(d, ["4"])).toBe(false);
    expect(reponseValide(d, ["1.5"])).toBe(false);
  });
});
