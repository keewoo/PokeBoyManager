import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DecksListView } from "@/app/jeu/decks/decks-list-view";
import * as decksApi from "@/lib/api/decks";
import type { DeckDetail, DeckSummary } from "@/lib/api/decks";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/lib/api/decks", () => ({
  listDecks: vi.fn(),
  createDeck: vi.fn(),
  duplicateDeck: vi.fn(),
  deleteDeck: vi.fn(),
  fetchDeckAlerts: vi.fn(),
  markDeckAlertsRead: vi.fn(),
}));

const api = vi.mocked(decksApi);

function summary(over: Partial<DeckSummary> = {}): DeckSummary {
  return {
    id: "d1",
    name: "Deck feu",
    format: "standard",
    card_count: 60,
    legal: true,
    created_at: "2026-09-22T10:00:00Z",
    updated_at: "2026-09-22T10:00:00Z",
    ...over,
  };
}

function detail(over: Partial<DeckDetail> = {}): DeckDetail {
  return {
    id: "new1",
    name: "Nouveau",
    format: "standard",
    created_at: "2026-09-22T10:00:00Z",
    updated_at: "2026-09-22T10:00:00Z",
    cards: [],
    legality: {
      legal: false,
      card_count: 0,
      size_ok: false,
      format: "standard",
      format_label: "Standard",
      issues: [],
    },
    ...over,
  };
}

describe("DecksListView", () => {
  beforeEach(() => {
    push.mockClear();
    api.listDecks.mockReset();
    api.createDeck.mockReset();
    api.duplicateDeck.mockReset();
    api.deleteDeck.mockReset();
    api.fetchDeckAlerts.mockReset();
    api.markDeckAlertsRead.mockReset();
    // Par défaut : aucune alerte, pour ne pas changer les cas existants (le bandeau reste caché).
    api.fetchDeckAlerts.mockResolvedValue({ alerts: [], unread_count: 0 });
    api.markDeckAlertsRead.mockResolvedValue({ alerts: [], unread_count: 0 });
  });

  it("affiche les decks existants et leur légalité", async () => {
    api.listDecks.mockResolvedValue({
      decks: [summary({ id: "d1", name: "Deck feu", legal: true })],
    });
    render(<DecksListView />);
    expect(await screen.findByText("Deck feu")).toBeInTheDocument();
    expect(screen.getByText("Légal")).toBeInTheDocument();
  });

  it("montre un état vide quand il n'y a aucun deck", async () => {
    api.listDecks.mockResolvedValue({ decks: [] });
    render(<DecksListView />);
    expect(await screen.findByText(/Aucun deck pour l'instant/i)).toBeInTheDocument();
  });

  it("crée un deck et ouvre son constructeur", async () => {
    const user = userEvent.setup();
    api.listDecks.mockResolvedValue({ decks: [] });
    api.createDeck.mockResolvedValue(detail({ id: "new1", name: "Mon deck" }));
    render(<DecksListView />);
    await screen.findByText(/Aucun deck pour l'instant/i);

    await user.type(screen.getByLabelText("Nom du deck"), "Mon deck");
    await user.click(screen.getByRole("button", { name: /Créer et construire/i }));

    await waitFor(() =>
      expect(api.createDeck).toHaveBeenCalledWith({ name: "Mon deck" })
    );
    expect(push).toHaveBeenCalledWith("/jeu/decks/new1");
  });

  it("supprime un deck seulement après confirmation", async () => {
    const user = userEvent.setup();
    api.listDecks.mockResolvedValue({ decks: [summary({ id: "d1", name: "Deck feu" })] });
    api.deleteDeck.mockResolvedValue(undefined);
    render(<DecksListView />);
    const row = (await screen.findByText("Deck feu")).closest("li")!;

    await user.click(within(row).getByRole("button", { name: "Supprimer" }));
    expect(api.deleteDeck).not.toHaveBeenCalled(); // un premier clic n'agit pas

    await user.click(within(row).getByRole("button", { name: "Confirmer" }));
    await waitFor(() => expect(api.deleteDeck).toHaveBeenCalledWith("d1"));
    await waitFor(() => expect(screen.queryByText("Deck feu")).not.toBeInTheDocument());
  });

  it("duplique un deck et l'ajoute à la liste", async () => {
    const user = userEvent.setup();
    api.listDecks.mockResolvedValue({ decks: [summary({ id: "d1", name: "Deck feu" })] });
    api.duplicateDeck.mockResolvedValue(
      detail({ id: "d2", name: "Deck feu (copie)", legality: {
        legal: true, card_count: 60, size_ok: true, format: "standard",
        format_label: "Standard", issues: [],
      } })
    );
    render(<DecksListView />);
    const row = (await screen.findByText("Deck feu")).closest("li")!;

    await user.click(within(row).getByRole("button", { name: "Dupliquer" }));
    await waitFor(() => expect(api.duplicateDeck).toHaveBeenCalledWith("d1"));
    expect(await screen.findByText("Deck feu (copie)")).toBeInTheDocument();
  });

  it("affiche un bandeau d'alertes de collection et le referme quand on marque lu", async () => {
    const user = userEvent.setup();
    api.listDecks.mockResolvedValue({ decks: [summary({ id: "d1", name: "Deck feu", legal: false })] });
    api.fetchDeckAlerts.mockResolvedValue({
      alerts: [
        {
          id: "e1",
          deck_id: "d1",
          deck_name: "Deck feu",
          event_type: "card_incomplete",
          reason: "removed",
          card_id: "c1",
          card_name: "Dracaufeu",
          required: 1,
          owned: 0,
          missing: 1,
          read: false,
          created_at: "2026-09-22T10:00:00Z",
        },
      ],
      unread_count: 1,
    });
    render(<DecksListView />);
    const notice = await screen.findByTestId("deck-alerts-notice");
    expect(notice).toHaveTextContent("Deck feu");

    await user.click(within(notice).getByRole("button", { name: "Marquer comme lu" }));
    await waitFor(() => expect(api.markDeckAlertsRead).toHaveBeenCalled());
    expect(screen.queryByTestId("deck-alerts-notice")).not.toBeInTheDocument();
  });
});
