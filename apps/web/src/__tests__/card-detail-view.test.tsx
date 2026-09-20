import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CardDetailView } from "@/app/carte/[id]/card-detail-view";
import {
  getCardDetail,
  getCardMyItems,
  getCardInsights,
  getInGameStudy,
  getCardPriceHistory,
  type CardDetail,
  type MyCardItem,
} from "@/lib/api/cards";

const replace = vi.fn();
let searchParamsValue = "";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(searchParamsValue),
}));

vi.mock("@/lib/api/cards", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/cards")>("@/lib/api/cards");
  return {
    ...actual,
    getCardDetail: vi.fn(),
    getCardMyItems: vi.fn(),
    getCardPriceHistory: vi.fn(),
    getCardInsights: vi.fn(),
    getInGameStudy: vi.fn(),
  };
});

const CARD: CardDetail = {
  id: "card-1",
  name: "Dracaufeu-EX",
  number: "XY121",
  rarity: "rare secrète",
  supertype: "Pokémon",
  hp: 180,
  has_image: true,
  illustrator: "Mitsuhiro Arita",
  set: {
    id: "set-1",
    name: "Promo XY",
    code: "promo-xy",
    series: "XY",
    release_date: "2016-05-01",
    total_cards: 198,
    logo_url: null,
  },
  prices_eur: { normal: null, holo: "42.50", reverse_holo: null, first_edition: null },
  ranking: { rarity_rank: 1, rarity_group_size: 3, value_percentile: 0.92 },
  owned_count: 1,
  collection_rank: { position: 1, total_priced: 5 },
};

const ITEM: MyCardItem = {
  id: "item-1",
  language: "fr",
  variant: "holo",
  condition_grade: "near_mint",
  counterfeit_suspected: false,
  purchase_price: "30",
  purchase_currency: "EUR",
  purchase_price_eur: "30.000000",
  acquired_at: "2026-09-01",
  value_eur: "42.5000",
  has_photo: false,
  condition_detail: null,
};

describe("CardDetailView", () => {
  beforeEach(() => {
    replace.mockReset();
    searchParamsValue = "";
    vi.mocked(getCardDetail).mockReset().mockResolvedValue(CARD);
    vi.mocked(getCardMyItems).mockReset().mockResolvedValue([ITEM]);
    vi.mocked(getCardPriceHistory).mockReset().mockResolvedValue({
      card_id: "card-1",
      variant: "holo",
      points: [
        { day: "2026-08-01", price_eur: "40.00" },
        { day: "2026-09-01", price_eur: "42.50" },
      ],
    });
    vi.mocked(getCardInsights).mockReset().mockResolvedValue({
      card_id: "card-1",
      status: "ready",
      anecdotes: [{ text: "Une anecdote sourcée.", source_url: "https://example.org" }],
      generated_at: "2026-09-01T00:00:00Z",
    });
    vi.mocked(getInGameStudy).mockReset().mockResolvedValue({
      card_id: "card-1",
      legalities: { standard: false, expanded: true },
      prize_rule: { applies: true, prizes_taken: 2, label: "2 cartes Récompense" },
      attacks: [{ name: "Explo-Combustion", damage: 150 }],
      abilities: null,
      tournament_presence: { status: "checked", source_url: null, checked_at: null, decks: [] },
      study: { status: "ready", text: "Trop lente pour le méta actuel.", generated_at: null },
    });
  });

  it("affiche l'en-tête de la fiche et l'onglet Valeur par défaut", async () => {
    render(<CardDetailView cardId="card-1" />);

    expect(await screen.findByText("Dracaufeu-EX")).toBeInTheDocument();
    expect(screen.getAllByText(/Promo XY/).length).toBeGreaterThan(0);
    expect(screen.getByText("n° 1 de ta collection")).toBeInTheDocument();
    // PERCENT_RANK 0,92 -> les 8 % les plus chers de l'extension, jamais "92 %" (sens inverse).
    expect(screen.getByText(/top 8 % de l'extension/)).toBeInTheDocument();
    expect(await screen.findByText("42,50 €")).toBeInTheDocument();
  });

  it("bascule vers l'onglet Mes exemplaires au clic", async () => {
    const user = userEvent.setup();
    render(<CardDetailView cardId="card-1" />);
    await screen.findByText("Dracaufeu-EX");

    await user.click(screen.getByRole("tab", { name: "Mes exemplaires" }));

    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(screen.getAllByText("near_mint").length).toBeGreaterThan(0);
    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith(expect.stringContaining("onglet=ex"), expect.anything())
    );
  });

  it("désactive la bascule « Ma photo » quand l'exemplaire n'a pas de photo", async () => {
    render(<CardDetailView cardId="card-1" />);
    await screen.findByText("Dracaufeu-EX");

    expect(screen.getByRole("button", { name: "Ma photo" })).toBeDisabled();
  });

  it("affiche un état vide pour Mes exemplaires quand la carte n'est pas possédée", async () => {
    vi.mocked(getCardMyItems).mockResolvedValue([]);
    vi.mocked(getCardDetail).mockResolvedValue({
      ...CARD,
      owned_count: 0,
      collection_rank: null,
    });
    const user = userEvent.setup();
    render(<CardDetailView cardId="card-1" />);
    await screen.findByText("Dracaufeu-EX");

    await user.click(screen.getByRole("tab", { name: "Mes exemplaires" }));

    expect(
      await screen.findByText("Tu ne possèdes aucun exemplaire de cette carte.")
    ).toBeInTheDocument();
  });
});
