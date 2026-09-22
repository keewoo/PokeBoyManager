import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CollectionView } from "@/app/collection/collection-view";
import {
  getCollectionFacets,
  listCollection,
  type CollectionFacets,
  type CollectionListItem,
  type CollectionListResponse,
} from "@/lib/api/collection";

const replace = vi.fn();
let searchParamsValue = "";
// Le vrai `useSearchParams` de Next.js renvoie une référence stable tant que l'URL ne change
// pas réellement ; `CollectionView` s'appuie dessus (`useMemo`/`useEffect` sur `searchParams`).
// Un mock qui reconstruirait un `URLSearchParams` à chaque rendu casserait cette hypothèse et
// provoquerait une boucle de rendu propre au test — caché derrière ce cache.
let cachedSearchParams: { for: string; value: URLSearchParams } | null = null;
function stableSearchParams(): URLSearchParams {
  if (!cachedSearchParams || cachedSearchParams.for !== searchParamsValue) {
    cachedSearchParams = { for: searchParamsValue, value: new URLSearchParams(searchParamsValue) };
  }
  return cachedSearchParams.value;
}

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => stableSearchParams(),
}));

vi.mock("@/lib/api/collection", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/collection")>(
    "@/lib/api/collection"
  );
  return {
    ...actual,
    listCollection: vi.fn(),
    getCollectionFacets: vi.fn(),
  };
});

const FACETS: CollectionFacets = {
  sets: [{ set_id: "set-1", name: "Écarlate et Violet", code: "sv01" }],
  series: ["Écarlate et Violet"],
  rarities: ["rare"],
  card_types: ["Pokémon"],
  languages: ["fr"],
  variants: ["normal"],
  condition_grades: ["mint"],
};

const BASE_ITEM: CollectionListItem = {
  id: "item-1",
  card_id: "card-1",
  set_id: "set-1",
  card_name: "Dracaufeu ex",
  card_number: "XY121",
  set_name: "Promo XY",
  set_code: "promo-xy",
  series: null,
  rarity: "rare",
  card_type: "Pokémon",
  element_type: "fire",
  hp: 180,
  language: "fr",
  variant: "normal",
  condition_grade: "mint",
  counterfeit_suspected: false,
  purchase_price: null,
  purchase_currency: null,
  acquired_at: "2026-09-01",
  value_eur: "145.5000",
  value_change_30d_eur: "10.0000",
  value_change_30d_pct: "7.4",
  is_duplicate: false,
};

function response(overrides: Partial<CollectionListResponse> = {}): CollectionListResponse {
  return {
    items: [BASE_ITEM],
    next_cursor: null,
    aggregates: {
      items_total: 1,
      items_priced: 1,
      items_missing_price: 0,
      total_value_eur: "145.5000",
      value_change_7d_eur: "2.0000",
      value_change_30d_eur: "10.0000",
    },
    ...overrides,
  };
}

describe("CollectionView", () => {
  beforeEach(() => {
    replace.mockReset();
    searchParamsValue = "";
    cachedSearchParams = null;
    vi.mocked(listCollection).mockReset();
    vi.mocked(getCollectionFacets).mockReset();
    vi.mocked(getCollectionFacets).mockResolvedValue(FACETS);
  });

  it("affiche les cartes, la valeur totale et les filtres issus des facettes", async () => {
    vi.mocked(listCollection).mockResolvedValue(response());

    render(<CollectionView />);

    expect(await screen.findByText("Dracaufeu ex")).toBeInTheDocument();
    // Le total agrégé et le prix de la carte affichent tous deux "145,50 €" ici (une seule
    // carte) : les deux occurrences prouvent que l'agrégat et la grille se sont bien chargés.
    expect(screen.getAllByText(/145,50/)).toHaveLength(2);
    expect(await screen.findByRole("checkbox", { name: "rare" })).toBeInTheDocument();
  });

  it("affiche l'état vide dédié quand la collection n'a aucune carte", async () => {
    vi.mocked(listCollection).mockResolvedValue(response({ items: [] }));

    render(<CollectionView />);

    expect(await screen.findByText("Ta collection est vide")).toBeInTheDocument();
  });

  it("affiche un message distinct quand un filtre actif ne trouve rien", async () => {
    searchParamsValue = "rarity=secrete";
    vi.mocked(listCollection).mockResolvedValue(
      response({
        items: [],
        aggregates: {
          items_total: 0,
          items_priced: 0,
          items_missing_price: 0,
          total_value_eur: "0",
          value_change_7d_eur: "0",
          value_change_30d_eur: "0",
        },
      })
    );

    render(<CollectionView />);

    expect(await screen.findByText("Aucune carte ne correspond à ces filtres.")).toBeInTheDocument();
    expect(screen.queryByText("Ta collection est vide")).not.toBeInTheDocument();
  });

  it("coche un filtre de rareté et met à jour l'URL avec le nouveau paramètre", async () => {
    vi.mocked(listCollection).mockResolvedValue(response());

    const user = userEvent.setup();
    render(<CollectionView />);
    await screen.findByText("Dracaufeu ex");

    await user.click(await screen.findByRole("checkbox", { name: "rare" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/collection?rarity=rare"));
  });

  it("charge la page suivante au clic sur « Charger plus »", async () => {
    // `mockImplementation` plutôt que `mockResolvedValueOnce` enchaînés : React peut rejouer
    // l'effet de chargement initial (StrictMode), la réponse doit donc rester stable tant que
    // `cursor` n'est pas fourni — seul le clic réel sur « Charger plus » en envoie un.
    const secondItem: CollectionListItem = { ...BASE_ITEM, id: "item-2", card_name: "Mimiqui ex" };
    vi.mocked(listCollection).mockImplementation(async (filters) =>
      filters.cursor
        ? response({ items: [secondItem], next_cursor: null })
        : response({ next_cursor: "cursor-1" })
    );

    const user = userEvent.setup();
    render(<CollectionView />);
    await screen.findByText("Dracaufeu ex");

    await user.click(screen.getByRole("button", { name: "Charger plus" }));

    expect(await screen.findByText("Mimiqui ex")).toBeInTheDocument();
    expect(screen.getByText("Dracaufeu ex")).toBeInTheDocument();
    expect(vi.mocked(listCollection)).toHaveBeenLastCalledWith(
      expect.objectContaining({ cursor: "cursor-1" })
    );
  });
});
