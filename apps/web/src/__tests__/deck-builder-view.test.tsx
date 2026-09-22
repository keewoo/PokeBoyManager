import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DeckBuilderView } from "@/app/jeu/decks/[id]/deck-builder-view";
import * as decksApi from "@/lib/api/decks";
import { ApiError } from "@/lib/api/client";
import type { DeckCard, DeckDetail } from "@/lib/api/decks";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/api/decks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/decks")>();
  return {
    ...actual,
    getDeck: vi.fn(),
    getDeckCardFacets: vi.fn(),
    searchDeckCards: vi.fn(),
    setDeckCard: vi.fn(),
    removeDeckCard: vi.fn(),
    updateDeck: vi.fn(),
    duplicateDeck: vi.fn(),
    deleteDeck: vi.fn(),
  };
});

const api = vi.mocked(decksApi);

function card(over: Partial<DeckCard> = {}): DeckCard {
  return {
    card_id: "c",
    card_name: "Carte",
    card_number: "1",
    set_id: "s",
    set_name: "SV",
    set_code: "sv01",
    image_url: null,
    supertype: "Pokémon",
    rarity: null,
    quantity: 1,
    is_basic_energy: false,
    is_special_energy: false,
    is_basic_pokemon: true,
    owned: 1,
    missing: 0,
    in_collection: true,
    in_format: true,
    counterfeit_excluded: 0,
    ...over,
  };
}

function deck(): DeckDetail {
  return {
    id: "d1",
    name: "Mon deck",
    format: "standard",
    created_at: "2026-09-22T10:00:00Z",
    updated_at: "2026-09-22T10:00:00Z",
    cards: [
      card({ card_id: "pika", card_name: "Pikachu", quantity: 4, owned: 4 }),
      card({ card_id: "roucool", card_name: "Roucool", quantity: 2, owned: 1, missing: 1 }),
      card({
        card_id: "feu",
        card_name: "Énergie Feu",
        quantity: 1,
        is_basic_energy: true,
        is_basic_pokemon: false,
        supertype: "Énergie",
      }),
    ],
    legality: {
      legal: false,
      card_count: 7,
      size_ok: false,
      format: "standard",
      format_label: "Standard",
      issues: [
        {
          code: "deck_size",
          message: "Il manque 53 carte(s) : un deck compte exactement 60 cartes.",
          severity: "bloquant",
          card_id: null,
          card_name: null,
          detail: null,
        },
        {
          code: "not_owned",
          message: "Il manque 1 exemplaire(s) de « Roucool ».",
          severity: "bloquant",
          card_id: "roucool",
          card_name: "Roucool",
          detail: null,
        },
      ],
    },
  };
}

describe("DeckBuilderView", () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => {
      if (typeof fn === "function" && "mockReset" in fn) (fn as ReturnType<typeof vi.fn>).mockReset();
    });
    api.getDeckCardFacets.mockResolvedValue({
      sets: [],
      rarities: [],
      card_types: [],
      hp_min: null,
      hp_max: null,
      owned_card_count: 3,
      duplicate_card_count: 0,
    });
    api.searchDeckCards.mockResolvedValue({ items: [], next_cursor: null });
  });

  it("affiche le deck, son décompte et l'état de légalité", async () => {
    api.getDeck.mockResolvedValue(deck());
    render(<DeckBuilderView deckId="d1" />);
    expect(await screen.findByText(/Deck · 7 \/ 60/)).toBeInTheDocument();
    expect(screen.getByText("Illégal")).toBeInTheDocument();
    // Le constat global (taille) est visible ; le constat par carte est porté par l'alerte.
    expect(screen.getByText(/un deck compte exactement 60 cartes/i)).toBeInTheDocument();
  });

  it("affiche l'alerte « à compléter » avec ses trois issues pour une carte manquante", async () => {
    api.getDeck.mockResolvedValue(deck());
    render(<DeckBuilderView deckId="d1" />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/Roucool/);
    expect(alert).toHaveTextContent(/Remplacer par une possédée/);
    expect(alert).toHaveTextContent(/Retirer du deck/);
    expect(alert).toHaveTextContent(/Voir la carte/);
  });

  it("« retirer un exemplaire » décrémente quand il en reste plusieurs", async () => {
    const user = userEvent.setup();
    api.getDeck.mockResolvedValue(deck());
    api.setDeckCard.mockResolvedValue(deck());
    render(<DeckBuilderView deckId="d1" />);
    await screen.findByText("Pikachu");
    await user.click(
      screen.getByRole("button", { name: "Retirer un exemplaire de Pikachu" })
    );
    await waitFor(() => expect(api.setDeckCard).toHaveBeenCalledWith("d1", "pika", 3));
    expect(api.removeDeckCard).not.toHaveBeenCalled();
  });

  it("« retirer un exemplaire » du dernier retire la carte", async () => {
    const user = userEvent.setup();
    api.getDeck.mockResolvedValue(deck());
    api.removeDeckCard.mockResolvedValue(deck());
    render(<DeckBuilderView deckId="d1" />);
    await screen.findByText("Énergie Feu");
    await user.click(
      screen.getByRole("button", { name: "Retirer un exemplaire de Énergie Feu" })
    );
    await waitFor(() => expect(api.removeDeckCard).toHaveBeenCalledWith("d1", "feu"));
  });

  it("« Retirer » supprime la carte entière d'un coup", async () => {
    const user = userEvent.setup();
    api.getDeck.mockResolvedValue(deck());
    api.removeDeckCard.mockResolvedValue(deck());
    render(<DeckBuilderView deckId="d1" />);
    await screen.findByText("Pikachu");
    await user.click(screen.getByRole("button", { name: "Retirer Pikachu du deck" }));
    await waitFor(() => expect(api.removeDeckCard).toHaveBeenCalledWith("d1", "pika"));
    expect(api.setDeckCard).not.toHaveBeenCalled();
  });

  it("un deck qui ne t'appartient pas donne « introuvable »", async () => {
    api.getDeck.mockRejectedValue(new ApiError(404, "deck introuvable"));
    render(<DeckBuilderView deckId="d1" />);
    expect(await screen.findByText("Deck introuvable")).toBeInTheDocument();
  });
});
