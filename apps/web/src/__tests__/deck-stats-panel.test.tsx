import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DeckStatsPanel } from "@/app/jeu/decks/[id]/deck-stats-panel";
import * as decksApi from "@/lib/api/decks";
import { ApiError } from "@/lib/api/client";
import type { DeckStats } from "@/lib/api/decks";

vi.mock("@/lib/api/decks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/decks")>();
  return { ...actual, fetchDeckStats: vi.fn() };
});

const api = vi.mocked(decksApi);

function stats(over: Partial<DeckStats> = {}): DeckStats {
  return {
    deck_id: "d1",
    card_count: 60,
    distinct_cards: 12,
    by_supertype: [
      { key: "pokemon", label: "Pokémon", count: 16 },
      { key: "dresseur", label: "Dresseur", count: 24 },
      { key: "energie", label: "Énergie", count: 20 },
    ],
    by_role: [
      { key: "attaquant", label: "Attaquants", count: 12 },
      { key: "mur", label: "Murs", count: 4 },
      { key: "soutien", label: "Soutien", count: 24 },
      { key: "energie", label: "Énergies", count: 20 },
    ],
    type_distribution: [{ key: "fire", label: "Feu", count: 16 }],
    untyped_pokemon: 0,
    attack_cost_curve: [
      { key: "1", label: "1", count: 8 },
      { key: "2", label: "2", count: 8 },
    ],
    attacks_counted: 16,
    average_hp: 145.5,
    pokemon_with_hp: 16,
    stage_distribution: [{ key: "base", label: "De base", count: 16 }],
    has_basic_pokemon: true,
    evolution_copies_without_base: 0,
    special_cards: 6,
    duplicate_copies: 30,
    duplicate_ratio: 0.75,
    value: {
      total_eur: "42.50",
      priced_cards: 10,
      missing_price_cards: 2,
      priced_copies: 34,
      counted_copies: 40,
    },
    ...over,
  };
}

describe("DeckStatsPanel", () => {
  beforeEach(() => {
    api.fetchDeckStats.mockReset();
  });

  it("charge les stats du bon deck et affiche les tuiles chiffrées", async () => {
    api.fetchDeckStats.mockResolvedValue(stats());
    render(<DeckStatsPanel deckId="d1" refreshKey="2026-09-22T10:00:00Z" />);

    expect(await screen.findByText("PV moyens")).toBeInTheDocument();
    expect(api.fetchDeckStats).toHaveBeenCalledWith("d1");
    // La valeur marchande vient du serveur, formatée en euros.
    expect(screen.getByText("42,50 €")).toBeInTheDocument();
    expect(screen.getByText("145.5")).toBeInTheDocument();
    // Part de doublons rendue en pourcentage.
    expect(screen.getByText("75 %")).toBeInTheDocument();
    // Répartition par rôle : chaque rôle est nommé.
    expect(screen.getByText("Attaquants")).toBeInTheDocument();
    expect(screen.getByText("Murs")).toBeInTheDocument();
  });

  it("avertit quand des évolutions n'ont aucun Pokémon de base", async () => {
    api.fetchDeckStats.mockResolvedValue(
      stats({
        has_basic_pokemon: false,
        evolution_copies_without_base: 3,
        stage_distribution: [{ key: "stage1", label: "Niveau 1", count: 3 }],
      })
    );
    render(<DeckStatsPanel deckId="d1" refreshKey="k" />);
    expect(
      await screen.findByText(/sans aucun Pokémon\s+de base/i)
    ).toBeInTheDocument();
  });

  it("montre un message d'erreur sans planter si l'API échoue", async () => {
    api.fetchDeckStats.mockRejectedValue(new ApiError(500, "Statistiques indisponibles."));
    render(<DeckStatsPanel deckId="d1" refreshKey="k" />);
    expect(await screen.findByText("Statistiques indisponibles.")).toBeInTheDocument();
  });
});
