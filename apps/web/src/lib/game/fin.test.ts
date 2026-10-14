import { describe, expect, it } from "vitest";

import {
  RAISONS_FIN,
  bilanCompte,
  dureeEnFrancais,
  issueDeFin,
  phraseDeFin,
  raisonCourte,
  titreDeFin,
  type ResultatPartie,
} from "@/lib/game/fin";

/**
 * Module de fin de partie (lot `j-partie-fin-ui`) — fonctions pures.
 *
 * La parité « toute raison du moteur a son libellé » est gardée côté moteur
 * (`apps/game/tests/test_parite_raisons_fin_front.py`, qui lit ce fichier) : la faire ici
 * reviendrait à comparer ce fichier à lui-même. Ce qu'on vérifie ici, c'est ce que le moteur ne
 * peut pas voir — le **contenu** des phrases (une par issue, aucune qui humilie), l'issue depuis
 * le vainqueur, et la série calculée depuis l'historique.
 */

describe("libellés des raisons de fin", () => {
  it("donne trois phrases distinctes par raison, et aucune vide", () => {
    for (const [code, libelles] of Object.entries(RAISONS_FIN)) {
      expect(libelles.court.length, code).toBeGreaterThan(0);
      for (const issue of ["victoire", "defaite", "nulle"] as const) {
        expect(libelles[issue].length, `${code}/${issue}`).toBeGreaterThan(0);
      }
      // Victoire et défaite racontent le même fait, mais pas avec les mêmes mots : si elles sont
      // identiques, c'est qu'on a écrit une phrase « neutre » servie aux deux — exactement ce que
      // le lot interdit (« sans humilier le perdant » suppose de distinguer les deux).
      if (code !== "inactivite" && code !== "egalite") {
        expect(libelles.victoire, code).not.toBe(libelles.defaite);
      }
    }
  });

  it("n'emploie aucun mot qui juge le joueur", () => {
    // Liste volontairement courte et explicite : elle ne « détecte pas la méchanceté », elle
    // verrouille le vocabulaire qu'on s'est interdit (critère 1 de la mission du lot).
    const interdits = ["écrasante", "écrasé", "nul", "bête", "bêtement", "honte", "raté"];
    for (const [code, libelles] of Object.entries(RAISONS_FIN)) {
      for (const phrase of [libelles.court, libelles.victoire, libelles.defaite, libelles.nulle]) {
        const minuscule = phrase.toLowerCase();
        for (const mot of interdits) {
          expect(minuscule.includes(mot), `${code} : « ${phrase} »`).toBe(false);
        }
      }
    }
  });

  it("nomme l'égalité au lieu d'afficher son code brut", () => {
    // C'était le trou au moment d'écrire ce lot : `egalite` tombait sur le repli « code brut ».
    expect(raisonCourte("egalite")).toBe("égalité");
    expect(phraseDeFin("egalite", "nulle")).not.toContain("egalite");
  });

  it("montre un code inconnu au lieu de le masquer", () => {
    // Un moteur plus récent que l'écran : on préfère un identifiant visible à une fin muette.
    expect(raisonCourte("raison_du_futur")).toBe("raison_du_futur");
    expect(phraseDeFin("raison_du_futur", "victoire")).toContain("raison_du_futur");
  });

  it("dit « la partie est terminée » quand aucune raison n'est connue", () => {
    expect(phraseDeFin(null, "nulle")).toBe("La partie est terminée.");
    expect(raisonCourte(null)).toBe("?");
  });
});

describe("issue de la partie", () => {
  it("compare des identifiants de compte, pas des identifiants moteur", () => {
    expect(issueDeFin("u1", "u1")).toBe("victoire");
    expect(issueDeFin("u2", "u1")).toBe("defaite");
  });

  it("rend « nulle » sans vainqueur (égalité R-14.4, clôture pour inactivité)", () => {
    expect(issueDeFin(null, "u1")).toBe("nulle");
  });

  it("rend « nulle » plutôt qu'une victoire quand le compte connecté est inconnu", () => {
    // Ne jamais annoncer une victoire par défaut : le doute ne se tranche pas en faveur du joueur.
    expect(issueDeFin("u1", null)).toBe("nulle");
  });
});

describe("titre de l'écran", () => {
  it("tient en trois mots au plus (contrainte de la police pixel .pbm-titre)", () => {
    for (const issue of ["victoire", "defaite", "nulle"] as const) {
      expect(titreDeFin(issue).split(/\s+/).length, issue).toBeLessThanOrEqual(3);
    }
  });

  it("ne commente pas la défaite", () => {
    expect(titreDeFin("defaite")).toBe("C'est passé près");
  });
});

describe("bilan du compte", () => {
  function partie(over: Partial<ResultatPartie> = {}): ResultatPartie {
    return {
      status: "terminee",
      vainqueur_user_id: "moi",
      raison_fin: "derniere_recompense",
      updated_at: "2026-10-14T10:00:00+00:00",
      entrainement: false,
      ...over,
    };
  }

  it("compte la série de victoires en partant de la partie la plus récente", () => {
    const bilan = bilanCompte(
      [
        partie({ updated_at: "2026-10-14T09:00:00+00:00" }),
        partie({ updated_at: "2026-10-14T11:00:00+00:00" }),
        partie({ updated_at: "2026-10-14T10:00:00+00:00" }),
      ],
      "moi",
    );
    expect(bilan.parties).toBe(3);
    expect(bilan.victoires).toBe(3);
    expect(bilan.serie).toBe(3);
  });

  it("remet la série à zéro quand la dernière partie n'est pas une victoire", () => {
    const bilan = bilanCompte(
      [
        partie({ updated_at: "2026-10-14T09:00:00+00:00" }),
        partie({ updated_at: "2026-10-14T10:00:00+00:00", vainqueur_user_id: "autre" }),
      ],
      "moi",
    );
    expect(bilan.victoires).toBe(1);
    expect(bilan.serie).toBe(0);
  });

  it("exclut les parties d'entraînement : elles ne comptent pas (DJ7)", () => {
    // Sinon la série se fabrique contre un bot, et le chiffre ne veut plus rien dire.
    const bilan = bilanCompte(
      [
        partie({ updated_at: "2026-10-14T10:00:00+00:00", entrainement: true }),
        partie({ updated_at: "2026-10-14T09:00:00+00:00", vainqueur_user_id: "autre" }),
      ],
      "moi",
    );
    expect(bilan.parties).toBe(1);
    expect(bilan.victoires).toBe(0);
    expect(bilan.serie).toBe(0);
  });

  it("exclut les parties en cours : une partie non finie n'a pas de résultat", () => {
    const bilan = bilanCompte(
      [partie({ status: "en_cours", vainqueur_user_id: null })],
      "moi",
    );
    expect(bilan.parties).toBe(0);
  });

  it("compte les parties nulles à part, sans les prendre pour des victoires", () => {
    const bilan = bilanCompte([partie({ vainqueur_user_id: null })], "moi");
    expect(bilan.nulles).toBe(1);
    expect(bilan.victoires).toBe(0);
    expect(bilan.serie).toBe(0);
  });

  it("ne modifie pas la liste qu'on lui passe", () => {
    const parties = [
      partie({ updated_at: "2026-10-14T09:00:00+00:00" }),
      partie({ updated_at: "2026-10-14T11:00:00+00:00" }),
    ];
    const copie = parties.map((p) => p.updated_at);
    bilanCompte(parties, "moi");
    expect(parties.map((p) => p.updated_at)).toEqual(copie);
  });
});

describe("durée en français", () => {
  it("dit « inconnue » quand la durée ne se calcule pas, jamais « 0 s »", () => {
    expect(dureeEnFrancais(null)).toBe("inconnue");
    expect(dureeEnFrancais(undefined)).toBe("inconnue");
  });

  it("formate secondes, minutes et heures", () => {
    expect(dureeEnFrancais(0)).toBe("0 s");
    expect(dureeEnFrancais(42)).toBe("42 s");
    expect(dureeEnFrancais(60)).toBe("1 min");
    expect(dureeEnFrancais(432)).toBe("7 min 12 s");
    expect(dureeEnFrancais(3600)).toBe("1 h");
    expect(dureeEnFrancais(3900)).toBe("1 h 5 min");
  });
});
