import { describe, expect, it } from "vitest";

import type { ReplayEtape } from "@/lib/api/games";
import {
  PAS_MS,
  borner,
  coupsJusqua,
  delaiMs,
  dernierRangCharge,
  destinatairesDe,
  estCharge,
  estComplet,
  fusionnerRangs,
  nomDu,
  rangA,
  rangsManquants,
} from "@/lib/game/replay";

/**
 * Navigation d'un replay (lot `j-replay`) — la logique **pure** derrière l'écran.
 *
 * Ce qui est mesuré ici, c'est exactement ce que l'écran délègue : se placer sans jamais sortir de
 * ce qui est chargé, dire ce qui manque plutôt que de le taire, et reconstruire le fil du journal
 * **tel qu'il était** au rang regardé (pas le journal entier d'emblée).
 */

const JID_A = "aaaa-1111";
const JID_B = "bbbb-2222";

/** Un rang de replay minimal : son indice, et un coup sauf au rang 0. */
function etape(rang: number, evts: Record<string, unknown[]> = {}): ReplayEtape {
  return {
    rang,
    coup:
      rang === 0
        ? null
        : {
            numero: rang - 1,
            auteur: JID_A,
            type: "piocher",
            horodatage: "2026-10-14T10:00:00Z",
            empreinte: `e${rang}`,
          },
    vues: { [JID_A]: { pour: JID_A } },
    evenements: evts,
  };
}

describe("delaiMs", () => {
  it("accélère et ralentit autour du pas de base", () => {
    expect(delaiMs(1)).toBe(PAS_MS);
    expect(delaiMs(2)).toBe(PAS_MS / 2);
    expect(delaiMs(0.5)).toBe(PAS_MS * 2);
  });

  it("refuse une vitesse nulle ou négative plutôt que de figer l'écran en silence", () => {
    expect(() => delaiMs(0)).toThrow(/Vitesse de replay invalide/);
    expect(() => delaiMs(-1)).toThrow(/Vitesse de replay invalide/);
  });
});

describe("fusionnerRangs", () => {
  it("met les rangs dans l'ordre et dédoublonne par rang", () => {
    const fusion = fusionnerRangs([etape(0), etape(1)], [etape(3), etape(2)]);
    expect(fusion.map((e) => e.rang)).toEqual([0, 1, 2, 3]);
  });

  it("laisse une page redemandée remplacer les rangs qu'elle recouvre (pas de doublon)", () => {
    const ancien = etape(2, { [JID_A]: ["ancien"] });
    const nouveau = etape(2, { [JID_A]: ["nouveau"] });
    const fusion = fusionnerRangs([etape(0), etape(1), ancien], [nouveau, etape(3)]);
    expect(fusion.map((e) => e.rang)).toEqual([0, 1, 2, 3]);
    expect(rangA(fusion, 2)?.evenements[JID_A]).toEqual(["nouveau"]);
  });
});

describe("borner", () => {
  const rangs = [etape(0), etape(1), etape(2)];

  it("ramène un rang trop grand au dernier rang chargé", () => {
    // Le piège : laisser l'index filer jusqu'au `total` annoncé par le serveur alors que les
    // pages suivantes ne sont pas arrivées — l'écran montrerait du vide.
    expect(borner(99, rangs)).toBe(2);
  });

  it("ramène un rang négatif ou non fini à 0", () => {
    expect(borner(-5, rangs)).toBe(0);
    expect(borner(Number.NaN, rangs)).toBe(0);
  });

  it("tronque un rang fractionnaire et laisse un rang valide intact", () => {
    expect(borner(1.9, rangs)).toBe(1);
    expect(borner(1, rangs)).toBe(1);
  });

  it("rend 0 quand rien n'est encore chargé (aucun index négatif ne circule)", () => {
    expect(borner(3, [])).toBe(0);
    expect(dernierRangCharge([])).toBe(-1);
  });
});

describe("complétude", () => {
  it("dit combien de rangs manquent, et ne prétend pas être complet avant de l'être", () => {
    const partiel = [etape(0), etape(1), etape(2)];
    // 10 coups joués = rangs 0..10 ; on en a jusqu'au 2.
    expect(estComplet(partiel, 10)).toBe(false);
    expect(rangsManquants(partiel, 10)).toBe(8);

    const complet = Array.from({ length: 11 }, (_, i) => etape(i));
    expect(estComplet(complet, 10)).toBe(true);
    expect(rangsManquants(complet, 10)).toBe(0);
  });

  it("sait si un rang précis est déjà là (sinon l'écran va chercher sa page)", () => {
    const rangs = [etape(0), etape(1)];
    expect(estCharge(1, rangs)).toBe(true);
    expect(estCharge(2, rangs)).toBe(false);
    expect(rangA(rangs, 2)).toBeNull();
  });
});

describe("coupsJusqua", () => {
  const rangs = [
    etape(0),
    etape(1, { [JID_A]: [{ type: "evt1" }], [JID_B]: [{ type: "evt1b" }] }),
    etape(2, { [JID_A]: [{ type: "evt2" }], [JID_B]: [] }),
    etape(3, { [JID_A]: [{ type: "evt3" }] }),
  ];

  it("ne rend que les coups joués jusqu'au rang regardé (pas le journal entier)", () => {
    // C'est le cœur du replay : au rang 2, on n'a pas encore vu le coup 2.
    expect(coupsJusqua(rangs, 2, JID_A).map((c) => c.numero)).toEqual([0, 1]);
    expect(coupsJusqua(rangs, 3, JID_A).map((c) => c.numero)).toEqual([0, 1, 2]);
  });

  it("au rang 0, le fil est vide (aucun coup ne mène à l'état initial)", () => {
    expect(coupsJusqua(rangs, 0, JID_A)).toEqual([]);
  });

  it("prend les événements du destinataire demandé — le fil de CE joueur", () => {
    expect(coupsJusqua(rangs, 1, JID_A).at(0)?.evenements).toEqual([{ type: "evt1" }]);
    expect(coupsJusqua(rangs, 1, JID_B).at(0)?.evenements).toEqual([{ type: "evt1b" }]);
  });

  it("rend un fil vide plutôt que `undefined` pour un destinataire non servi à ce rang", () => {
    // Le rang 3 n'a pas la vue de B (page en `vue=moi` côté A) : on ne fabrique rien.
    expect(coupsJusqua(rangs, 3, JID_B).at(-1)?.evenements).toEqual([]);
  });
});

describe("destinataires et noms", () => {
  const joueurs = [
    { seat: 0, user_id: "u-a", joueur_id: JID_A, pseudo: "Alice", bot_niveau: null },
    { seat: 1, user_id: "u-b", joueur_id: JID_B, pseudo: null, bot_niveau: "coriace" },
  ];

  it("liste les destinataires réellement servis, dans l'ordre des sièges", () => {
    const complete = {
      joueurs,
      etapes: [{ ...etape(0), vues: { [JID_B]: {}, [JID_A]: {} } }],
    };
    // L'ordre vient des sièges, pas des clés de `vues` : « joueur 1 / joueur 2 » ne doit pas
    // s'inverser d'un chargement à l'autre.
    expect(destinatairesDe(complete)).toEqual([JID_A, JID_B]);

    const moi = { joueurs, etapes: [{ ...etape(0), vues: { [JID_B]: {} } }] };
    expect(destinatairesDe(moi)).toEqual([JID_B]);
  });

  it("nomme un joueur par son pseudo, un bot par son niveau, et jamais par un identifiant nu", () => {
    expect(nomDu({ joueurs }, JID_A)).toBe("Alice");
    expect(nomDu({ joueurs }, JID_B)).toBe("Bot (coriace)");
    expect(nomDu({ joueurs }, "inconnu")).toBe("Joueur inconnu");
  });
});
