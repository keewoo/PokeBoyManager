import { describe, expect, it } from "vitest";

import { ETAPES_GUIDE, avancerGuide } from "@/lib/game/guide";
import { RECOMPENSES_MAX, type VuePartie, type VuePokemon } from "@/lib/game/plateau";

function pokemon(energies = 0, degats = 0): VuePokemon {
  return {
    cartes: [{ instance_id: "c1", ref: "base1-1" }],
    energies: Array.from({ length: energies }, (_, i) => ({
      instance_id: `e${i}`,
      ref: "energie-feu",
    })),
    outil: null,
    compteurs_degats: degats,
    etats_speciaux: [],
    orientation: "debout",
  };
}

type Etat = {
  monActif?: VuePokemon | null;
  monBanc?: VuePokemon[];
  actifAdverse?: VuePokemon | null;
  mesRecompenses?: number;
};

/** Une vue cohérente décrivant un moment précis de la partie. */
function vue(etat: Etat = {}): VuePartie {
  return {
    schema_version: 1,
    pour: "a",
    joueurs: [
      {
        id: "a",
        actif: etat.monActif ?? null,
        banc: etat.monBanc ?? [],
        defausse: [],
        zone_perdue: [],
        pioche_nombre: 40,
        recompenses_nombre: etat.mesRecompenses ?? RECOMPENSES_MAX,
      },
      {
        id: "b",
        actif: etat.actifAdverse ?? null,
        banc: [],
        defausse: [],
        zone_perdue: [],
        pioche_nombre: 40,
        recompenses_nombre: RECOMPENSES_MAX,
      },
    ],
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
    actions_legales: [],
  };
}

describe("parcours guidé — forme des étapes", () => {
  it("couvre la boucle du jeu demandée : poser, attacher, attaquer, prendre", () => {
    expect(ETAPES_GUIDE.map((e) => e.cle)).toEqual([
      "actif",
      "banc",
      "energie",
      "attaque",
      "recompense",
    ]);
  });

  it("chaque étape dit quoi faire, cite une règle, et ne porte aucune action", () => {
    for (const e of ETAPES_GUIDE) {
      expect(e.regle, e.cle).toMatch(/^R-\d+\.\d+$/);
      expect(e.consigne.length, e.cle).toBeGreaterThan(40);
      // Une consigne s'adresse au joueur : elle le tutoie, elle ne lui récite pas un numéro.
      expect(e.consigne, e.cle).not.toMatch(/R-\d+\.\d+/);
      // Le guide CONSTATE : aucune étape ne transporte de quoi soumettre un coup (3ᵉ critère).
      expect(Object.keys(e).sort(), e.cle).toEqual([
        "accompli",
        "cle",
        "consigne",
        "regle",
        "titre",
      ]);
    }
  });
});

describe("parcours guidé — une première partie se termine", () => {
  it("va de la première étape à la fin au fil des coups du joueur, sans aide extérieure", () => {
    // Le critère d'acceptation « la première partie guidée se termine » se prouve ici : on rejoue
    // la suite des états qu'un débutant produit en suivant les consignes, et on vérifie qu'à chaque
    // fois le guide reconnaît l'étape franchie et désigne la suivante — jamais un cul-de-sac.
    let p = avancerGuide(vue(), 0);
    expect(p.etape?.cle).toBe("actif");

    // Il pose son Actif (consigne 1).
    p = avancerGuide(vue({ monActif: pokemon() }), p.index);
    expect(p.etape?.cle).toBe("banc");

    // Il remplit son banc (consigne 2).
    p = avancerGuide(vue({ monActif: pokemon(), monBanc: [pokemon()] }), p.index);
    expect(p.etape?.cle).toBe("energie");

    // Il attache une énergie (consigne 3).
    p = avancerGuide(vue({ monActif: pokemon(1), monBanc: [pokemon()] }), p.index);
    expect(p.etape?.cle).toBe("attaque");

    // Il attaque : des dégâts apparaissent en face (consigne 4).
    p = avancerGuide(
      vue({ monActif: pokemon(1), monBanc: [pokemon()], actifAdverse: pokemon(0, 3) }),
      p.index,
    );
    expect(p.etape?.cle).toBe("recompense");

    // Le Pokémon d'en face tombe, il prend sa récompense (consigne 5) : le parcours est fini.
    p = avancerGuide(
      vue({ monActif: pokemon(1), monBanc: [pokemon()], mesRecompenses: RECOMPENSES_MAX - 1 }),
      p.index,
    );
    expect(p.termine).toBe(true);
    expect(p.etape).toBeNull();
    expect(p.index).toBe(ETAPES_GUIDE.length);
  });

  it("ne recule jamais quand l'état du plateau change après coup", () => {
    // Le piège réel : l'Actif adverse blessé est remplacé (ou évolue), ses dégâts disparaissent de
    // la vue. Sans mémoire, le guide renverrait le joueur à « attaque » alors qu'il a déjà attaqué.
    const apresAttaque = avancerGuide(
      vue({ monActif: pokemon(1), monBanc: [pokemon()], actifAdverse: pokemon(0, 3) }),
      0,
    );
    expect(apresAttaque.etape?.cle).toBe("recompense");

    const adversaireRemplace = avancerGuide(
      vue({ monActif: pokemon(1), monBanc: [pokemon()], actifAdverse: pokemon(0, 0) }),
      apresAttaque.index,
    );
    expect(adversaireRemplace.etape?.cle).toBe("recompense");
  });

  it("franchit d'un coup plusieurs étapes déjà faites (reprise après un F5)", () => {
    // Au rechargement, l'écran n'a plus l'index mémorisé : le guide doit retrouver sa place en
    // lisant le seul plateau, sans redemander ce qui est fait.
    const p = avancerGuide(vue({ monActif: pokemon(2), monBanc: [pokemon(), pokemon()] }), 0);
    expect(p.etape?.cle).toBe("attaque");
  });

  it("ne tombe pas sur une vue illisible : il se tait au lieu de casser l'écran", () => {
    // Le guide est un décor posé sur le jeu. Une vue incohérente doit se signaler ailleurs (le
    // plateau lève), pas faire disparaître la partie derrière une erreur d'aide.
    const cassee = { ...vue(), pour: "inconnu" } as VuePartie;
    const p = avancerGuide(cassee, 0);
    expect(p.etape?.cle).toBe("actif");
    expect(p.termine).toBe(false);
  });

  it("reste terminé une fois terminé", () => {
    const p = avancerGuide(vue(), ETAPES_GUIDE.length);
    expect(p.termine).toBe(true);
    expect(p.etape).toBeNull();
  });
});
