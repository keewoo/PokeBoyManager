import { describe, expect, it } from "vitest";

import { categoryLabel, scriptBlockedCardIds } from "@/lib/game/legality";

describe("categoryLabel", () => {
  it("nomme chaque catégorie de blocage", () => {
    expect(categoryLabel("possession")).toBe("Possession");
    expect(categoryLabel("legalite")).toBe("Légalité");
    expect(categoryLabel("script")).toBe("Effet non géré");
  });

  it("retombe prudemment sur « Légalité » pour une catégorie inconnue", () => {
    expect(categoryLabel("autre")).toBe("Légalité");
  });
});

describe("scriptBlockedCardIds", () => {
  it("ne retient que les cartes bloquées par un effet non scripté", () => {
    const issues = [
      { code: "unsupported_effect", card_id: "c1" },
      { code: "not_owned", card_id: "c2" },
      { code: "unsupported_effect", card_id: "c3" },
      { code: "unsupported_effect", card_id: null }, // constat sans carte : ignoré
    ];
    const blocked = scriptBlockedCardIds(issues);
    expect(blocked.has("c1")).toBe(true);
    expect(blocked.has("c3")).toBe(true);
    expect(blocked.has("c2")).toBe(false);
    expect(blocked.size).toBe(2);
  });

  it("rend un ensemble vide sans constat de script", () => {
    expect(scriptBlockedCardIds([{ code: "deck_size", card_id: null }]).size).toBe(0);
  });
});
