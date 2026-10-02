import { describe, expect, it } from "vitest";

import {
  BANC_MAX,
  bancAvecVides,
  estMonTour,
  nombreEnMain,
  recompensesRestantes,
  separerCamps,
  type VueJoueur,
  type VuePartie,
  type VuePokemon,
} from "./plateau";

function pokemon(ref: string): VuePokemon {
  return {
    cartes: [{ instance_id: `i-${ref}`, ref }],
    energies: [],
    outil: null,
    compteurs_degats: 0,
    etats_speciaux: [],
    orientation: "normale",
  };
}

function joueur(id: string, over: Partial<VueJoueur> = {}): VueJoueur {
  return {
    id,
    actif: pokemon("actif"),
    banc: [],
    defausse: [],
    zone_perdue: [],
    pioche_nombre: 40,
    recompenses_nombre: 6,
    ...over,
  };
}

function vue(over: Partial<VuePartie> = {}): VuePartie {
  return {
    schema_version: 1,
    pour: "a",
    joueurs: [
      joueur("a", { main: [{ instance_id: "m1", ref: "pika" }] }),
      joueur("b", { main_nombre: 5 }),
    ],
    tour: {
      joueur_actif: "a",
      numero: 3,
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
    ...over,
  };
}

describe("separerCamps", () => {
  it("place le destinataire en « moi » et l'autre en « adversaire »", () => {
    const { moi, adversaire } = separerCamps(vue());
    expect(moi.id).toBe("a");
    expect(adversaire.id).toBe("b");
  });

  it("lève si le destinataire n'est pas un joueur de la partie (pas de camp par défaut)", () => {
    expect(() => separerCamps(vue({ pour: "z" }))).toThrow(/incohérente/);
  });

  it("lève si la partie n'a pas exactement deux joueurs", () => {
    expect(() => separerCamps(vue({ joueurs: [joueur("a")] }))).toThrow();
  });
});

describe("estMonTour", () => {
  it("est vrai quand le joueur actif est le destinataire", () => {
    expect(estMonTour(vue({ tour: { ...vue().tour, joueur_actif: "a" } }))).toBe(true);
  });
  it("est faux quand c'est l'adversaire qui joue", () => {
    expect(estMonTour(vue({ tour: { ...vue().tour, joueur_actif: "b" } }))).toBe(false);
  });
});

describe("nombreEnMain", () => {
  it("compte les identités pour soi", () => {
    expect(nombreEnMain(joueur("a", { main: [{ instance_id: "x", ref: "r" }] }))).toBe(1);
  });
  it("lit le nombre pour l'adversaire, sans identités", () => {
    const adv = joueur("b", { main_nombre: 7 });
    expect(nombreEnMain(adv)).toBe(7);
    expect(adv.main).toBeUndefined();
  });
});

describe("bancAvecVides", () => {
  it("complète toujours à cinq emplacements, les vides à null", () => {
    const cases = bancAvecVides(joueur("a", { banc: [pokemon("p1"), pokemon("p2")] }));
    expect(cases).toHaveLength(BANC_MAX);
    expect(cases[0]?.cartes[0]?.ref).toBe("p1");
    expect(cases[2]).toBeNull();
  });
  it("tronque un banc trop long au maximum", () => {
    const trop = Array.from({ length: 7 }, (_, i) => pokemon(`p${i}`));
    expect(bancAvecVides(joueur("a", { banc: trop }))).toHaveLength(BANC_MAX);
  });
});

describe("recompensesRestantes", () => {
  it("renvoie le nombre de récompenses (zone cachée)", () => {
    expect(recompensesRestantes(joueur("a", { recompenses_nombre: 4 }))).toBe(4);
  });
});
