import { describe, expect, it } from "vitest";

import {
  estimerHorloges,
  formatSecondes,
  type HorlogeJoueur,
  type HorlogesServeur,
} from "@/lib/game/horloges";

// Un instantané serveur de référence : c'est le tour d'alice (horloge « tour »), bob ne décompte pas.
function instantane(partiel: Partial<HorlogesServeur> = {}): HorlogesServeur {
  return {
    maintenant: 1_000_000,
    en_pause: false,
    pause_joueur: null,
    pause_restant_s: null,
    joueurs: {
      alice: { budget_s: 1500, genre: "tour", horloge_s: 90 },
      bob: { budget_s: 1500, genre: null, horloge_s: null },
    },
    ...partiel,
  };
}

/** Lit un joueur de l'instantané en le typant (le `Record` indexé serait `… | undefined`). */
function j(h: HorlogesServeur, id: string): HorlogeJoueur {
  const v = h.joueurs[id];
  if (!v) throw new Error(`joueur ${id} absent de l'instantané`);
  return v;
}

describe("estimerHorloges", () => {
  it("retranche le temps écoulé localement, pour le seul joueur qui décompte", () => {
    const e = estimerHorloges(instantane(), 10_000, 11_500); // 1,5 s plus tard
    expect(j(e, "alice").horloge_s).toBeCloseTo(88.5);
    expect(j(e, "alice").budget_s).toBeCloseTo(1498.5);
    // bob ne décompte pas : rien ne bouge.
    expect(j(e, "bob").horloge_s).toBeNull();
    expect(j(e, "bob").budget_s).toBe(1500);
  });

  it("recale sur la vérité serveur à chaque instantané (aucune dérive accumulée)", () => {
    // Après 1,9 s, le client afficherait ~88,1. Le serveur renvoie alors un NOUVEL instantané à 88 :
    // l'estimation repart de 88, pas de 88,1 — l'écart ne s'accumule jamais (garde les ≤ 2 s).
    const premier = estimerHorloges(instantane(), 0, 1_900);
    expect(j(premier, "alice").horloge_s).toBeCloseTo(88.1);
    const recale = estimerHorloges(
      instantane({
        joueurs: {
          alice: { budget_s: 1498, genre: "tour", horloge_s: 88 },
          bob: { budget_s: 1500, genre: null, horloge_s: null },
        },
      }),
      2_000,
      2_000,
    );
    expect(j(recale, "alice").horloge_s).toBe(88);
  });

  it("reste à moins de 2 s de la vérité serveur tant qu'on se recale au moins toutes les ~2 s", () => {
    // La vérité serveur à t = +1,8 s serait 90 - 1,8 = 88,2. L'estimation locale depuis la réception
    // donne exactement cela (mêmes horodatages) : l'écart est nul, bien en deçà de 2 s.
    const e = estimerHorloges(instantane(), 5_000, 6_800);
    const veriteServeur = 90 - 1.8;
    expect(Math.abs((j(e, "alice").horloge_s ?? 0) - veriteServeur)).toBeLessThan(2);
  });

  it("gèle les horloges de jeu en pause, mais la grâce de pause s'écoule", () => {
    const enPause = instantane({ en_pause: true, pause_joueur: "bob", pause_restant_s: 120 });
    const e = estimerHorloges(enPause, 0, 30_000); // 30 s de déconnexion
    // Les horloges de jeu n'ont pas bougé (gelées) ...
    expect(j(e, "alice").horloge_s).toBe(90);
    expect(j(e, "alice").budget_s).toBe(1500);
    // ... mais la grâce de pause a bien décompté.
    expect(e.pause_restant_s).toBeCloseTo(90);
  });

  it("ne borne pas l'horloge courte sous zéro (tolérance réseau), mais garde le budget ≥ 0", () => {
    const e = estimerHorloges(
      instantane({
        joueurs: {
          alice: { budget_s: 3, genre: "tour", horloge_s: 1 },
          bob: { budget_s: 1500, genre: null, horloge_s: null },
        },
      }),
      0,
      5_000,
    );
    expect(j(e, "alice").horloge_s).toBeCloseTo(-4); // 1 - 5, affichage honnête du dépassement
    expect(j(e, "alice").budget_s).toBe(0); // borné à 0
  });
});

describe("formatSecondes", () => {
  it("formate en m:ss, sans négatif à l'écran", () => {
    expect(formatSecondes(90)).toBe("1:30");
    expect(formatSecondes(5)).toBe("0:05");
    expect(formatSecondes(0)).toBe("0:00");
    expect(formatSecondes(-3)).toBe("0:00");
  });
});
