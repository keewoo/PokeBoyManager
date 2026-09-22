import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DeckAiAssistant } from "@/app/jeu/decks/[id]/deck-ai-assistant";
import * as decksApi from "@/lib/api/decks";
import { ApiError } from "@/lib/api/client";
import type { DeckDetail, DeckProposalResponse } from "@/lib/api/decks";

vi.mock("@/lib/api/decks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/decks")>();
  return { ...actual, proposeDeck: vi.fn() };
});

const api = vi.mocked(decksApi);

function deck(): DeckDetail {
  return {
    id: "d1",
    name: "Deck IA",
    format: "standard",
    created_at: "2026-09-22T10:00:00Z",
    updated_at: "2026-09-22T10:05:00Z",
    cards: [],
    legality: {
      legal: true,
      card_count: 60,
      size_ok: true,
      format: "standard",
      format_label: "Standard",
      issues: [],
    },
  };
}

function proposal(): DeckProposalResponse {
  return {
    deck: deck(),
    explanations: [
      { card_id: "pika", card_name: "Pikachu", quantity: 4, reason: "Attaquant principal." },
    ],
    corrections: [{ code: "energy_fill", message: "Deck complété avec des Énergies de base (56 fire)." }],
    summary: "Deck Feu agressif.",
    provider: "anthropic",
    model: "claude",
    input_tokens: 1200,
    output_tokens: 300,
  };
}

describe("DeckAiAssistant", () => {
  beforeEach(() => vi.clearAllMocks());

  it("propose un deck avec les types choisis et remonte le deck au parent", async () => {
    const user = userEvent.setup();
    api.proposeDeck.mockResolvedValue(proposal());
    const onProposed = vi.fn();

    render(<DeckAiAssistant deckId="d1" onProposed={onProposed} disabled={false} />);

    await user.click(screen.getByRole("button", { name: /proposer un deck/i }));
    await user.click(screen.getByRole("button", { name: "Feu" }));
    await user.click(screen.getByRole("button", { name: /l'ia compose|proposer un deck/i }));

    await waitFor(() => expect(api.proposeDeck).toHaveBeenCalledTimes(1));
    expect(api.proposeDeck).toHaveBeenCalledWith(
      "d1",
      expect.objectContaining({ types: [{ type: "fire" }], size: 60 })
    );

    await waitFor(() => expect(onProposed).toHaveBeenCalledWith(expect.objectContaining({ id: "d1" })));

    // la stratégie, la trace des corrections et les explications carte par carte sont affichées
    expect(screen.getByText("Deck Feu agressif.")).toBeInTheDocument();
    expect(screen.getByText(/Deck complété avec des Énergies/)).toBeInTheDocument();
    expect(screen.getByText(/Pikachu/)).toBeInTheDocument();
    expect(screen.getByText(/Attaquant principal\./)).toBeInTheDocument();
  });

  it("affiche le message d'erreur de l'API (ex. clé IA manquante)", async () => {
    const user = userEvent.setup();
    api.proposeDeck.mockRejectedValue(new ApiError(409, "Aucune clé IA par défaut."));
    const onProposed = vi.fn();

    render(<DeckAiAssistant deckId="d1" onProposed={onProposed} disabled={false} />);
    await user.click(screen.getByRole("button", { name: /proposer un deck/i }));
    await user.click(screen.getByRole("button", { name: /l'ia compose|proposer un deck/i }));

    await waitFor(() =>
      expect(screen.getByText("Aucune clé IA par défaut.")).toBeInTheDocument()
    );
    expect(onProposed).not.toHaveBeenCalled();
  });
});
