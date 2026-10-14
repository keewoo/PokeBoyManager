import { describe, expect, it } from "vitest";

import { ELEMENTS } from "@/lib/game/indicateurs";
import {
  DECORS,
  DECORS_REGLABLES,
  DECOR_AUTO,
  DECOR_DEFAUT,
  NUIT_DEBUT_H,
  NUIT_FIN_H,
  decorEffectif,
  decorPourType,
  libelleDecor,
  momentPourHeure,
  typeDominant,
} from "@/lib/game/decors";

/**
 * Le **choix** du décor (lot `j-arene-decors`) : qui décide, dans quel ordre, et ce qui arrive
 * quand personne n'a rien dit.
 *
 * Le contraste et les teintes sont mesurés ailleurs (`src/__tests__/contraste-decors.test.ts`) ;
 * ici on ne teste que la règle de résolution — c'est elle qui décide ce qu'un joueur voit.
 */
describe("décors d'arène — la table", () => {
  it("couvre les onze types d'énergie du jeu, chacun exactement une fois", () => {
    // Un type oublié retomberait sur le décor par défaut **sans qu'on sache** que c'est un oubli :
    // le joueur verrait un thème « automatique » qui ne suit pas son deck. Un type présent deux
    // fois rendrait le thème indécidable (le résultat dépendrait de l'ordre d'itération).
    const couverts = Object.values(DECORS).flatMap((d) => d.types);
    const attendus = Object.keys(ELEMENTS).sort();
    expect([...couverts].sort()).toEqual(attendus);
    expect(new Set(couverts).size, `un type est servi par deux décors : ${couverts}`).toBe(
      couverts.length,
    );
  });

  it("chaque décor a une clé cohérente, un libellé et une phrase", () => {
    for (const [cle, decor] of Object.entries(DECORS)) {
      expect(decor.cle, `la clé de ${cle} ne correspond pas à son entrée`).toBe(cle);
      expect(decor.libelle.length).toBeGreaterThan(2);
      // La phrase sert l'écran de choix ET les lecteurs d'écran : une clé technique n'y suffit pas.
      expect(decor.phrase.length).toBeGreaterThan(20);
    }
  });

  it("propose entre quatre et six décors, comme le demande la mission du lot", () => {
    expect(DECORS_REGLABLES.length).toBeGreaterThanOrEqual(4);
    expect(DECORS_REGLABLES.length).toBeLessThanOrEqual(6);
  });

  it("nomme un décor inconnu au lieu de le taire", () => {
    expect(libelleDecor("arene")).toBe("Arène municipale");
    expect(libelleDecor("atlantide")).toContain("atlantide");
  });
});

describe("décors d'arène — le thème automatique", () => {
  it("associe un type à son décor, et rend null pour un type inconnu (D9)", () => {
    expect(decorPourType("fire")).toBe("caldeira");
    expect(decorPourType("water")).toBe("lagon");
    expect(decorPourType("darkness")).toBe("faille");
    expect(decorPourType("psychic")).toBe("temple");
    // Insensible à la casse : les codes viennent du serveur, on ne parie pas sur leur forme.
    expect(decorPourType("FIRE")).toBe("caldeira");
    expect(decorPourType("pierre")).toBeNull();
    expect(decorPourType(null)).toBeNull();
    expect(decorPourType(undefined)).toBeNull();
  });

  it("trouve le type le plus fréquent d'un ensemble de cartes", () => {
    expect(typeDominant(["fire", "water", "fire"])).toBe("fire");
    expect(typeDominant([])).toBeNull();
    expect(typeDominant([null, undefined])).toBeNull();
    // Les cartes sans type (Dresseurs, Objets) ne votent pas, et n'empêchent pas de trancher.
    expect(typeDominant([null, "grass", undefined])).toBe("grass");
  });

  it("tranche une égalité par le code, jamais par l'ordre d'arrivée", () => {
    // Sinon le décor dépendrait de la pioche : le même deck donnerait un décor différent à chaque
    // partie, ce qui est exactement l'effet qu'on ne veut pas.
    expect(typeDominant(["water", "fire"])).toBe(typeDominant(["fire", "water"]));
    expect(typeDominant(["water", "fire"])).toBe("fire");
  });
});

describe("décors d'arène — la résolution", () => {
  it("fait passer le choix du joueur avant le thème de son deck", () => {
    // Un joueur qui a choisi « Lagon » le garde même en jouant un deck Feu. Le thème automatique
    // n'est là que pour qui n'a rien choisi — il ne corrige jamais une décision prise.
    expect(decorEffectif("lagon", ["fire", "fire", "fire"])).toBe("lagon");
  });

  it("suit le deck quand le joueur n'a rien choisi", () => {
    expect(decorEffectif(null, ["fire", "fire", "water"])).toBe("caldeira");
    expect(decorEffectif(DECOR_AUTO, ["lightning"])).toBe("orage");
  });

  it("retombe sur le décor d'origine quand il n'y a rien pour décider", () => {
    expect(decorEffectif(null, [])).toBe(DECOR_DEFAUT);
    expect(decorEffectif(undefined, [null, undefined])).toBe(DECOR_DEFAUT);
    // Une clé inconnue (réglage d'une version précédente, décor retiré depuis) ne doit pas
    // produire un fond nu : elle vaut « pas de choix ».
    expect(decorEffectif("atlantide", [])).toBe(DECOR_DEFAUT);
    expect(decorEffectif("atlantide", ["water"])).toBe("lagon");
  });
});

describe("décors d'arène — jour et nuit", () => {
  it("passe en nuit le soir et revient au jour le matin", () => {
    expect(momentPourHeure(14)).toBe("jour");
    expect(momentPourHeure(NUIT_DEBUT_H)).toBe("nuit");
    expect(momentPourHeure(NUIT_DEBUT_H - 1)).toBe("jour");
    expect(momentPourHeure(23)).toBe("nuit");
    expect(momentPourHeure(0)).toBe("nuit");
    expect(momentPourHeure(NUIT_FIN_H - 1)).toBe("nuit");
    expect(momentPourHeure(NUIT_FIN_H)).toBe("jour");
  });

  it("couvre les 24 heures sans trou ni chevauchement", () => {
    // La fenêtre de nuit traverse minuit : c'est le genre d'intervalle où un `&&` à la place d'un
    // `||` laisse passer un trou de plusieurs heures sans que rien ne le signale.
    const heures = Array.from({ length: 24 }, (_, h) => momentPourHeure(h));
    expect(heures.filter((m) => m === "nuit")).toHaveLength(11); // 20h→6h inclus
    expect(heures.filter((m) => m === "jour")).toHaveLength(13); // 7h→19h inclus
  });
});
