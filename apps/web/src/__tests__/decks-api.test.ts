import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createDeck,
  deleteDeck,
  duplicateDeck,
  getDeck,
  getDeckCardFacets,
  listDecks,
  removeDeckCard,
  searchDeckCards,
  setDeckCard,
  updateDeck,
} from "@/lib/api/decks";
import { apiGet, apiJson } from "@/lib/api/client";

vi.mock("@/lib/api/client", () => ({
  apiGet: vi.fn(() => Promise.resolve({})),
  apiJson: vi.fn(() => Promise.resolve({})),
}));

const mockGet = vi.mocked(apiGet);
const mockJson = vi.mocked(apiJson);

describe("api/decks", () => {
  beforeEach(() => {
    mockGet.mockClear();
    mockJson.mockClear();
  });

  it("liste et détail passent par les bonnes routes", () => {
    listDecks();
    getDeck("d1");
    expect(mockGet).toHaveBeenNthCalledWith(1, "/me/decks");
    expect(mockGet).toHaveBeenNthCalledWith(2, "/me/decks/d1");
  });

  it("création, renommage, duplication, suppression", () => {
    createDeck({ name: "Feu", format: "expanded" });
    updateDeck("d1", { name: "Eau" });
    duplicateDeck("d1");
    deleteDeck("d1");
    expect(mockJson).toHaveBeenNthCalledWith(1, "POST", "/me/decks", {
      name: "Feu",
      format: "expanded",
    });
    expect(mockJson).toHaveBeenNthCalledWith(2, "PATCH", "/me/decks/d1", { name: "Eau" });
    expect(mockJson).toHaveBeenNthCalledWith(3, "POST", "/me/decks/d1/duplicate");
    expect(mockJson).toHaveBeenNthCalledWith(4, "DELETE", "/me/decks/d1");
  });

  it("ajout et retrait d'une carte du deck", () => {
    setDeckCard("d1", "c9", 4);
    removeDeckCard("d1", "c9");
    expect(mockJson).toHaveBeenNthCalledWith(1, "PUT", "/me/decks/d1/cards/c9", { quantity: 4 });
    expect(mockJson).toHaveBeenNthCalledWith(2, "DELETE", "/me/decks/d1/cards/c9");
  });

  it("la recherche encode tous les filtres dans la query string", () => {
    searchDeckCards({
      deckId: "d1",
      q: "pika",
      setId: "s1",
      cardType: "Lightning",
      rarity: "Rare",
      owned: true,
      duplicates: true,
      cursor: "cur",
      limit: 20,
    });
    const path = mockGet.mock.calls[0]![0] as string;
    expect(path.startsWith("/me/decks/cards?")).toBe(true);
    const query = new URLSearchParams(path.split("?")[1]);
    expect(query.get("deck_id")).toBe("d1");
    expect(query.get("q")).toBe("pika");
    expect(query.get("set_id")).toBe("s1");
    expect(query.get("card_type")).toBe("Lightning");
    expect(query.get("rarity")).toBe("Rare");
    expect(query.get("owned")).toBe("true");
    expect(query.get("duplicates")).toBe("true");
    expect(query.get("cursor")).toBe("cur");
    expect(query.get("limit")).toBe("20");
  });

  it("la recherche sans filtre n'ajoute pas de query string", () => {
    searchDeckCards({});
    expect(mockGet).toHaveBeenCalledWith("/me/decks/cards");
  });

  it("les facettes ont leur propre route", () => {
    getDeckCardFacets();
    expect(mockGet).toHaveBeenCalledWith("/me/decks/cards/facets");
  });
});
