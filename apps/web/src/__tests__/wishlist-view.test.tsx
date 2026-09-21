import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SouhaitsPage from "@/app/souhaits/page";
import { searchCatalog } from "@/lib/api/validation";
import {
  createWishlistItem,
  deleteWishlistItem,
  listWishlist,
  type WishlistItem,
} from "@/lib/api/wishlist";

vi.mock("@/lib/api/wishlist", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/wishlist")>("@/lib/api/wishlist");
  return {
    ...actual,
    listWishlist: vi.fn(),
    createWishlistItem: vi.fn(),
    updateWishlistItem: vi.fn(),
    deleteWishlistItem: vi.fn(),
  };
});

vi.mock("@/lib/api/validation", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/validation")>(
    "@/lib/api/validation"
  );
  return { ...actual, searchCatalog: vi.fn() };
});

const ITEM: WishlistItem = {
  id: "item-1",
  card_id: "card-1",
  set_id: "set-1",
  card_name: "Dracaufeu",
  card_number: "6",
  set_name: "Set 151",
  set_code: "sv03.5",
  rarity: "rare",
  target_price_eur: "10.00",
  note: null,
  current_price_eur: "8.00",
  target_reached: true,
};

describe("Page /souhaits", () => {
  beforeEach(() => {
    vi.mocked(listWishlist).mockReset();
    vi.mocked(createWishlistItem).mockReset();
    vi.mocked(deleteWishlistItem).mockReset();
    vi.mocked(searchCatalog).mockReset();
  });

  it("affiche un état vide sans vœu", async () => {
    vi.mocked(listWishlist).mockResolvedValue({ items: [] });
    render(<SouhaitsPage />);

    expect(await screen.findByText(/aucun vœu pour l'instant/i)).toBeInTheDocument();
  });

  it("liste les vœux avec le prix cible, le prix courant et le badge objectif atteint", async () => {
    vi.mocked(listWishlist).mockResolvedValue({ items: [ITEM] });
    render(<SouhaitsPage />);

    expect(await screen.findByText("Dracaufeu")).toBeInTheDocument();
    expect(screen.getByText(/objectif atteint/i)).toBeInTheDocument();
  });

  it("cherche une carte puis l'ajoute aux vœux", async () => {
    vi.mocked(listWishlist).mockResolvedValue({ items: [] });
    vi.mocked(searchCatalog).mockResolvedValue([
      {
        card_id: "card-2",
        set_id: "set-2",
        number: "25",
        name: "Pikachu",
        matched_name: "Pikachu",
        language: "fr",
        set_name: "Set X",
        set_code: "x",
        score: 1,
      },
    ]);
    vi.mocked(createWishlistItem).mockResolvedValue({ ...ITEM, id: "item-2", card_name: "Pikachu" });

    const user = userEvent.setup();
    render(<SouhaitsPage />);
    await screen.findByText(/aucun vœu pour l'instant/i);

    await user.type(screen.getByLabelText(/chercher une carte au catalogue/i), "Pika");
    const option = await screen.findByRole("button", { name: /pikachu/i });
    await user.click(option);
    await user.click(screen.getByRole("button", { name: /ajouter à mes vœux/i }));

    await waitFor(() => expect(createWishlistItem).toHaveBeenCalledWith({
      card_id: "card-2",
      target_price_eur: null,
      note: null,
    }));
    expect(await screen.findByText("Pikachu")).toBeInTheDocument();
  });

  it("retire un vœu", async () => {
    vi.mocked(listWishlist).mockResolvedValue({ items: [ITEM] });
    vi.mocked(deleteWishlistItem).mockResolvedValue(undefined);

    const user = userEvent.setup();
    render(<SouhaitsPage />);
    await screen.findByText("Dracaufeu");

    await user.click(screen.getByRole("button", { name: /retirer/i }));

    await waitFor(() => expect(deleteWishlistItem).toHaveBeenCalledWith("item-1"));
    expect(screen.queryByText("Dracaufeu")).not.toBeInTheDocument();
  });
});
