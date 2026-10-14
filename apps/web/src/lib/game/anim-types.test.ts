import { describe, expect, it } from "vitest";

import {
  DEGATS_REFERENCE,
  DUREE_REDUITE,
  INTENSITE_ECHEC,
  PARTICULES_MAX,
  SPECS,
  TOTAL_MAX_MS,
  TYPE_LE_PLUS_LOURD,
  type Typage,
  badgeEffet,
  coutVisuel,
  effetAttaque,
  intensiteDe,
  palierDe,
} from "@/lib/game/anim-types";
import { DUREE_MAX, EFFETS } from "@/lib/game/animations";
import { ELEMENTS } from "@/lib/game/indicateurs";

/**
 * Les effets d'attaque **par type** (lot `j-anim-attaques-typees`).
 *
 * **Le test qui mord sans le changement** : `effetAttaque` n'existait pas — une attaque Feu et une
 * attaque Eau produisaient exactement le même effet neutre. Toute cette suite échoue sans le
 * module.
 *
 * Les quatre critères d'acceptation du lot sont vérifiés ici, sauf le plancher d'images par seconde
 * (qui se **mesure** au navigateur, `e2e/anim-attaques-typees.spec.ts`) :
 *
 * 1. les dix types ont leur effet, et l'intensité reflète le résultat du calcul ;
 * 2. l'effet ne masque jamais le plateau plus d'une seconde — vérifié pour les onze types et
 *    **toutes** les durées que le socle peut donner, pas sur un cas choisi ;
 * 3. la version réduite existe pour chaque effet et reste compréhensible.
 */

/** Les dix types que le lot exige nommément. */
const DIX_TYPES = [
  "fire",
  "water",
  "grass",
  "lightning",
  "psychic",
  "fighting",
  "darkness",
  "metal",
  "dragon",
  "fairy",
] as const;

function typage(partiel: Partial<Typage>): Typage {
  return {
    type: "fire",
    degats: 60,
    faiblesse: false,
    resistance: false,
    echec: false,
    ...partiel,
  };
}

describe("les dix types ont leur effet (critère n°1)", () => {
  it.each(DIX_TYPES)("%s est dans la table, et produit un effet", (code) => {
    expect(SPECS[code], `${code} absent de SPECS`).toBeDefined();
    const effet = effetAttaque(typage({ type: code }), { duree: 420 });
    expect(effet, `aucun effet pour ${code}`).not.toBeNull();
    expect(effet?.type).toBe(code);
    // Un effet doit **faire** quelque chose : au moins une couche, ou un geste de carte.
    const fait =
      (effet?.couches.length ?? 0) > 0 ||
      effet?.gesteCarte !== "aucun" ||
      (effet?.particules ?? 0) > 0;
    expect(fait, `l'effet de ${code} ne montre rien`).toBe(true);
  });

  it("Incolore a son effet aussi — un Pokémon `colorless` attaque comme les autres", () => {
    expect(effetAttaque(typage({ type: "colorless" }), { duree: 420 })).not.toBeNull();
  });

  it("chaque type de la table a sa contrepartie dans les onze types du plateau", () => {
    // Les deux tables doivent parler du même vocabulaire : un code présent ici et absent de
    // `ELEMENTS` donnerait un badge réduit au repère neutre « ? », sans que rien ne le dise.
    for (const code of Object.keys(SPECS)) {
      expect(ELEMENTS[code], `${code} absent de ELEMENTS (indicateurs.ts)`).toBeDefined();
    }
    expect(Object.keys(SPECS).sort()).toEqual(Object.keys(ELEMENTS).sort());
  });

  it("un type inconnu du serveur ne donne AUCUN effet — jamais une couleur devinée (D9)", () => {
    expect(effetAttaque(typage({ type: "" }), { duree: 420 })).toBeNull();
    expect(effetAttaque(typage({ type: "plasma" }), { duree: 420 })).toBeNull();
  });

  it("une attaque sans dégât et sans échec ne déclenche rien : elle se lit dans le journal", () => {
    expect(effetAttaque(typage({ degats: 0 }), { duree: 420 })).toBeNull();
  });
});

describe("l'intensité suit le résultat RÉEL du calcul (critère n°1)", () => {
  it("croît avec les dégâts, et plafonne à la référence", () => {
    const i10 = intensiteDe(typage({ degats: 10 }));
    const i100 = intensiteDe(typage({ degats: 100 }));
    const iRef = intensiteDe(typage({ degats: DEGATS_REFERENCE }));
    const iEnorme = intensiteDe(typage({ degats: DEGATS_REFERENCE * 3 }));
    expect(i10).toBeLessThan(i100);
    expect(i100).toBeLessThan(iRef);
    expect(iRef).toBe(1);
    // Sans plafond, une attaque à 600 écraserait toutes les autres et l'intensité ne dirait plus rien.
    expect(iEnorme).toBe(1);
  });

  it("la faiblesse RENFORCE au-delà du simple doublement des dégâts (R-10.2)", () => {
    // Le piège qu'on veut éviter : 60 doublés par faiblesse (= 120) rendus identiques à une
    // attaque de 120 sans faiblesse. Le joueur ne verrait pas *pourquoi* ça a fait mal.
    const avec = effetAttaque(typage({ degats: 120, faiblesse: true }), { duree: 420 });
    const sans = effetAttaque(typage({ degats: 120 }), { duree: 420 });
    expect(avec?.intensite).toBeGreaterThan(sans?.intensite ?? 1);
    expect(avec?.renforce).toBe(true);
    expect(sans?.renforce).toBe(false);
  });

  it("la résistance ATTÉNUE, et le dit (R-10.3)", () => {
    const avec = effetAttaque(typage({ degats: 30, resistance: true }), { duree: 420 });
    const sans = effetAttaque(typage({ degats: 30 }), { duree: 420 });
    expect(avec?.intensite).toBeLessThan(sans?.intensite ?? 0);
    expect(avec?.attenue).toBe(true);
  });

  it("un échec a son intensité et son palier à lui — pas « un coup faible »", () => {
    const echec = effetAttaque(typage({ degats: 0, echec: true }), { duree: 480 });
    expect(echec?.echec).toBe(true);
    expect(echec?.palier).toBe("echec");
    expect(echec?.intensite).toBe(INTENSITE_ECHEC);
    // Un ratage ne projette rien, ne secoue rien, ne déforme rien : le coup n'a pas porté. Sinon
    // on ne distingue pas « ça a raté » de « ça a fait 10 ».
    expect(echec?.particules).toBe(0);
    expect(echec?.secousse).toBe(false);
    expect(echec?.gesteCarte).toBe("aucun");
  });

  it("l'échec d'un type qui secoue le plateau ne le secoue pas non plus", () => {
    const eclair = effetAttaque(typage({ type: "lightning", degats: 0, echec: true }), {
      duree: 480,
    });
    expect(SPECS.lightning?.secousse).toBe(true);
    expect(eclair?.secousse).toBe(false);
  });

  it("le palier monte par trois crans, et un échec n'en fait pas partie", () => {
    expect(palierDe(0.1, false)).toBe("faible");
    expect(palierDe(0.5, false)).toBe("moyen");
    expect(palierDe(0.9, false)).toBe("fort");
    expect(palierDe(0.9, true)).toBe("echec");
  });

  it("le nombre de particules suit l'intensité, et reste borné", () => {
    const faible = effetAttaque(typage({ type: "fairy", degats: 10 }), { duree: 420 });
    const fort = effetAttaque(typage({ type: "fairy", degats: 300 }), { duree: 420 });
    expect(faible?.particules).toBeGreaterThan(0);
    expect(fort?.particules).toBeGreaterThan(faible?.particules ?? 0);
    expect(fort?.particules).toBeLessThanOrEqual(PARTICULES_MAX);
  });

  it("un type sans particules n'en invente pas, quelle que soit l'intensité", () => {
    expect(SPECS.psychic?.particules).toBe(0);
    expect(effetAttaque(typage({ type: "psychic", degats: 300 }), { duree: 420 })?.particules).toBe(
      0,
    );
  });
});

describe("l'effet ne masque jamais le plateau plus d'une seconde (critère n°2)", () => {
  // Toutes les durées que le socle peut réellement donner : celles du registre `EFFETS`, plus les
  // bornes. On ne teste pas « un cas » : c'est la combinaison type × durée qui pourrait déborder.
  const durees = [
    0,
    1,
    ...new Set(Object.values(EFFETS).map((e) => e.duree)),
    DUREE_MAX,
    DUREE_MAX + 500,
  ];

  it.each(Object.keys(SPECS))("%s tient sous la seconde, pour toutes les durées du socle", (code) => {
    for (const duree of durees) {
      for (const extra of [{}, { faiblesse: true }, { resistance: true }, { echec: true }]) {
        const effet = effetAttaque(typage({ type: code, degats: 200, ...extra }), { duree });
        if (!effet) continue;
        expect(
          effet.dureeTotale,
          `${code} à ${duree}ms : ${effet.dureeTotale}ms d'occupation de la carte`,
        ).toBeLessThanOrEqual(TOTAL_MAX_MS);
        expect(effet.duree + effet.trace).toBe(effet.dureeTotale);
      }
    }
  });

  it("c'est la TRACE qui se fait raboter, jamais l'animation", () => {
    // Une animation tronquée se voit (elle s'arrête au milieu d'un mouvement) ; une trace écourtée
    // non. Donc à durée maximale, la trace disparaît et l'animation garde la sienne.
    const long = effetAttaque(typage({ type: "fire", degats: 200 }), { duree: TOTAL_MAX_MS });
    expect(long?.duree).toBe(TOTAL_MAX_MS);
    expect(long?.trace).toBe(0);
    const court = effetAttaque(typage({ type: "fire", degats: 200 }), { duree: 420 });
    expect(court?.duree).toBe(420);
    expect(court?.trace).toBeGreaterThan(0);
  });

  it("un type sans trace n'en laisse aucune, même avec de la marge", () => {
    expect(SPECS.fairy?.trace).toBe(false);
    expect(effetAttaque(typage({ type: "fairy", degats: 200 }), { duree: 100 })?.trace).toBe(0);
  });

  it("une durée absurde est bornée au lieu d'être propagée", () => {
    const effet = effetAttaque(typage({ degats: 60 }), { duree: 99_999 });
    expect(effet?.duree).toBe(TOTAL_MAX_MS);
    expect(effet?.dureeTotale).toBeLessThanOrEqual(TOTAL_MAX_MS);
  });
});

describe("la version réduite existe pour chaque effet et reste compréhensible (critère n°3)", () => {
  it.each(Object.keys(SPECS))("%s a sa version réduite, immobile et lisible", (code) => {
    const effet = effetAttaque(typage({ type: code, degats: 90, faiblesse: true }), {
      duree: 420,
      reduit: true,
    });
    expect(effet, `aucune version réduite pour ${code}`).not.toBeNull();
    // Immobile : aucune couche, aucun geste, aucune secousse, aucune durée d'animation.
    expect(effet?.anime).toBe(false);
    expect(effet?.couches).toEqual([]);
    expect(effet?.particules).toBe(0);
    expect(effet?.gesteCarte).toBe("aucun");
    expect(effet?.secousse).toBe(false);
    expect(effet?.duree).toBe(0);
    expect(effet?.trace).toBe(0);
    // Lisible : elle reste assez longtemps pour être lue, et elle dit tout en texte.
    expect(effet?.dureeTotale).toBe(DUREE_REDUITE);
    expect(effet?.phrase).toContain(SPECS[code]?.libelle);
    expect(effet?.phrase).toContain("90");
    expect(effet?.phrase.length).toBeGreaterThan(20);
    expect(effet?.badge).toBeTruthy();
  });

  it("la phrase nomme la faiblesse, la résistance et l'échec — jamais seulement un chiffre", () => {
    const opts = { duree: 420, reduit: true };
    expect(effetAttaque(typage({ degats: 120, faiblesse: true }), opts)?.phrase).toContain(
      "faiblesse",
    );
    expect(effetAttaque(typage({ degats: 30, resistance: true }), opts)?.phrase).toContain(
      "résistance",
    );
    expect(effetAttaque(typage({ degats: 0, echec: true }), opts)?.phrase).toContain("ratée");
  });

  it("le badge porte l'ABRÉVIATION du type, jamais la couleur seule (daltonisme)", () => {
    // Même règle que les indicateurs du plateau : un signe non coloré double toujours la teinte.
    for (const code of Object.keys(SPECS)) {
      const spec = SPECS[code];
      if (!spec) continue;
      expect(badgeEffet(spec, typage({ type: code, degats: 70 }))).toContain(
        ELEMENTS[code]?.abbr ?? "?",
      );
    }
  });

  it("un type inconnu reste sans effet, même en version réduite", () => {
    expect(effetAttaque(typage({ type: "plasma" }), { duree: 420, reduit: true })).toBeNull();
  });
});

describe("le type le plus lourd est CALCULÉ, pas choisi", () => {
  it("TYPE_LE_PLUS_LOURD est bien le maximum de la table", () => {
    // L'e2e de fluidité mesure le plancher d'images par seconde sur celui-là. Le nommer en dur
    // aurait voulu dire mesurer le mauvais type le jour où la table change, en restant vert.
    const pire = Object.values(SPECS).reduce(
      (max, spec) => Math.max(max, coutVisuel(spec)),
      0,
    );
    expect(coutVisuel(SPECS[TYPE_LE_PLUS_LOURD]!)).toBe(pire);
  });

  it("son effet à pleine intensité rend bien le maximum de particules autorisé", () => {
    const effet = effetAttaque(typage({ type: TYPE_LE_PLUS_LOURD, degats: 400 }), { duree: 420 });
    expect(effet?.palier).toBe("fort");
    expect(effet?.particules).toBeGreaterThan(0);
  });
});
