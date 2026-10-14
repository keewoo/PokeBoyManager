import { describe, expect, it } from "vitest";

import {
  EXPLICATIONS,
  GLOSSAIRE,
  OBJECTIF,
  expliquerRefus,
  motsDuTexte,
  regleDuRefus,
  suggestions,
  type Suggestion,
} from "@/lib/game/aide";
import type { VueActionLegale, VuePartie } from "@/lib/game/plateau";

/** Une vue minimale mais cohérente : deux joueurs, « moi » = `a`. */
function vue(legales: VueActionLegale[] = []): VuePartie {
  const joueur = (id: string) => ({
    id,
    actif: null,
    banc: [],
    defausse: [],
    zone_perdue: [],
    pioche_nombre: 40,
    recompenses_nombre: 6,
  });
  return {
    schema_version: 1,
    pour: "a",
    joueurs: [joueur("a"), joueur("b")],
    tour: {
      joueur_actif: "a",
      numero: 1,
      phase: "principale",
      energie_posee: false,
      supporter_joue: false,
      retraite_faite: false,
    },
    stade: null,
    stade_proprietaire: null,
    terminee: false,
    vainqueur: null,
    raison_fin: null,
    actions_legales: legales,
  };
}

function coup(type: string, etiquette = `faire ${type}`): VueActionLegale {
  return { type, params: {}, etiquette, cibles: [], irreversible: false };
}

describe("explications de règles", () => {
  it("n'emploie que des mots du glossaire", () => {
    // Une aide qui explique une règle avec un mot qu'elle n'explique pas déplace le problème.
    for (const [cle, e] of Object.entries(EXPLICATIONS)) {
      for (const mot of e.mots) {
        expect(GLOSSAIRE[mot], `${cle} cite « ${mot} », absent du glossaire`).toBeTruthy();
      }
    }
  });

  it("chaque explication est indexée sous sa propre règle, et reste courte", () => {
    for (const [cle, e] of Object.entries(EXPLICATIONS)) {
      expect(e.regle).toBe(cle);
      // Une règle (`R-5.4`) ou une section du corpus (`R-5`) — le moteur cite les deux niveaux.
      expect(cle).toMatch(/^R-\d+(\.\d+)?$/);
      expect(e.titre.length).toBeGreaterThan(3);
      // Écrit pour un enfant : deux phrases, pas un paragraphe de corpus.
      expect(e.explication.length, `${cle} : explication trop longue`).toBeLessThan(320);
      expect(e.alternative.length, `${cle} : alternative manquante`).toBeGreaterThan(10);
    }
  });

  it("ne remet jamais un numéro de règle sous les yeux du joueur", () => {
    // Le joueur lit « une seule énergie par tour », pas « R-5.4 » : le code de règle sert aux
    // tests et au support, pas à l'enfant qui joue.
    for (const [cle, e] of Object.entries(EXPLICATIONS)) {
      expect(`${e.titre} ${e.explication} ${e.alternative}`, cle).not.toMatch(/R-\d+\.\d+/);
    }
  });

  it("l'objectif de la partie est rappelé en une phrase", () => {
    expect(OBJECTIF).toContain("6");
    expect(OBJECTIF).toMatch(/récompense/i);
  });
});

describe("regleDuRefus", () => {
  it("retrouve la règle fondue dans le detail d'un 422", () => {
    // Forme réelle produite par l'API : « <message du moteur> (R-x.y) ».
    expect(regleDuRefus("Il faut au moins deux énergies Feu. (R-9.2)")).toBe("R-9.2");
  });

  it("retrouve la règle d'un refus préventif, donnée seule", () => {
    expect(regleDuRefus("R-5.4")).toBe("R-5.4");
  });

  it("rend null plutôt que de deviner", () => {
    expect(regleDuRefus("Coup impossible.")).toBeNull();
    expect(regleDuRefus("")).toBeNull();
    expect(regleDuRefus(null)).toBeNull();
  });
});

describe("expliquerRefus", () => {
  it("explique un refus préventif (regle et message séparés)", () => {
    const r = expliquerRefus({ regle: "R-5.4", message: "Énergie déjà attachée ce tour." });
    expect(r.regle).toBe("R-5.4");
    expect(r.message).toBe("Énergie déjà attachée ce tour.");
    expect(r.explication?.titre).toBe("Une seule énergie par tour");
    expect(r.explication?.alternative).toBeTruthy();
  });

  it("explique un refus soumis (chaîne detail du 422)", () => {
    const r = expliquerRefus("Le coût de l'attaque n'est pas payé. (R-9.2)");
    expect(r.regle).toBe("R-9.2");
    expect(r.explication?.titre).toBe("Il faut assez d'énergie pour attaquer");
  });

  it("garde le message du serveur même sans explication connue", () => {
    // Le serveur fait autorité : on n'invente pas une explication pour une règle inconnue, et on
    // ne masque pas pour autant sa raison (pas de repli silencieux).
    const r = expliquerRefus("Coup truqué refusé. (R-99.9)");
    expect(r.regle).toBe("R-99.9");
    expect(r.explication).toBeNull();
    expect(r.message).toContain("Coup truqué refusé.");
  });
});

describe("suggestions", () => {
  it("ne porte aucun params : l'aide ne peut pas soumettre un coup", () => {
    // Garantie de STRUCTURE du troisième critère d'acceptation : même un futur appelant bien
    // intentionné n'a pas de quoi jouer à la place du joueur depuis une suggestion.
    const sugg = suggestions(vue([coup("attacher_energie")]));
    expect(sugg).toHaveLength(1);
    for (const s of sugg as Suggestion[]) {
      expect(Object.keys(s).sort()).toEqual(["etiquette", "pourquoi", "type"]);
    }
  });

  it("ordonne par urgence pédagogique, pas par ordre du serveur", () => {
    const sugg = suggestions(
      vue([coup("declarer_attaque"), coup("piocher"), coup("attacher_energie")]),
    );
    expect(sugg.map((s) => s.type)).toEqual(["piocher", "attacher_energie", "declarer_attaque"]);
  });

  it("ne suggère jamais d'abandonner, même quand c'est le seul coup légal", () => {
    // `abandonner` est légal à tout instant (R-14.3) : sans cette garde il serait la première
    // suggestion de toutes les parties difficiles.
    expect(suggestions(vue([coup("abandonner")]))).toEqual([]);
    const sugg = suggestions(vue([coup("abandonner"), coup("poser")]));
    expect(sugg.map((s) => s.type)).toEqual(["poser"]);
  });

  it("se borne à trois coups, et dit pourquoi chacun", () => {
    const sugg = suggestions(
      vue([coup("poser"), coup("attacher_energie"), coup("evoluer"), coup("jouer_objet")]),
    );
    expect(sugg).toHaveLength(3);
    for (const s of sugg) expect(s.pourquoi.length).toBeGreaterThan(10);
  });

  it("ne modifie pas la liste du serveur", () => {
    const legales = [coup("declarer_attaque"), coup("piocher")];
    const avant = legales.map((a) => a.type);
    suggestions(vue(legales));
    expect(legales.map((a) => a.type)).toEqual(avant);
  });

  it("rend une liste vide sur une vue sans actions légales (plateau en lecture seule)", () => {
    const v = vue();
    delete v.actions_legales;
    expect(suggestions(v)).toEqual([]);
  });

  it("garde l'étiquette du serveur telle quelle", () => {
    const sugg = suggestions(vue([coup("declarer_attaque", "Éclair — 30 dégâts")]));
    expect(sugg[0]?.etiquette).toBe("Éclair — 30 dégâts");
  });
});

describe("glossaire", () => {
  it("explique chaque mot en une phrase utile", () => {
    for (const [mot, def] of Object.entries(GLOSSAIRE)) {
      expect(def.length, `« ${mot} » : définition trop courte`).toBeGreaterThan(20);
      expect(def.length, `« ${mot} » : définition trop longue`).toBeLessThan(260);
    }
  });

  it("couvre les mots du plateau qu'un débutant rencontre d'emblée", () => {
    for (const mot of ["Actif", "Banc", "Récompense", "Énergie", "K.O.", "Retraite"]) {
      expect(GLOSSAIRE[mot], `« ${mot} » manque au glossaire`).toBeTruthy();
    }
  });

  it("repère les mots d'un texte sur le mot entier, jamais sur un morceau", () => {
    expect(motsDuTexte("Attache une énergie à ton Actif.")).toEqual(
      expect.arrayContaining(["Actif", "Énergie"]),
    );
    // « Objet » ne doit pas se déclencher sur « objectif ».
    expect(motsDuTexte("Quel est ton objectif ?")).not.toContain("Objet");
  });
});
