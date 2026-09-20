import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DashboardView } from "@/components/dashboard/dashboard-view";
import { getDashboard, type DashboardResponse } from "@/lib/api/dashboard";
import { getProfile, type ProfileResponse } from "@/lib/api/profile";

vi.mock("@/lib/api/dashboard", () => ({ getDashboard: vi.fn() }));
vi.mock("@/lib/api/profile", () => ({ getProfile: vi.fn() }));

const PROFILE: ProfileResponse = {
  id: "user-1",
  email: "jf@exemple.fr",
  email_verified: true,
  pending_email: null,
  pseudo: "dresseur_jf",
  has_avatar: false,
  first_name: null,
  last_name: "Fontaine",
  birth_date: "2000-01-01",
};

function dashboard(overrides: Partial<DashboardResponse> = {}): DashboardResponse {
  return {
    items_total: 2,
    items_priced: 2,
    items_missing_price: 0,
    total_value_eur: "145.5000",
    value_change_30d_eur: "12.3000",
    value_history: [
      { as_of: "2026-06-22", total_value_eur: "100.0000" },
      { as_of: "2026-09-20", total_value_eur: "145.5000" },
    ],
    top_movers: [
      {
        item_id: "item-1",
        card_id: "card-1",
        card_name: "Dracaufeu ex",
        card_number: "XY121",
        set_name: "Promo XY",
        value_eur: "80.0000",
        value_change_30d_eur: "12.3000",
        value_change_30d_pct: "9.2",
      },
    ],
    recent_additions: [
      { item_id: "item-2", card_id: "card-2", card_name: "Mew", set_name: "151", added_at: "2026-09-19T10:00:00Z" },
      { item_id: "item-3", card_id: "card-3", card_name: "Pikachu", set_name: "151", added_at: "2026-09-18T10:00:00Z" },
    ],
    ...overrides,
  };
}

describe("DashboardView", () => {
  it("affiche la valeur totale, la variation 30 j et le pseudo", async () => {
    vi.mocked(getDashboard).mockResolvedValue(dashboard());
    vi.mocked(getProfile).mockResolvedValue(PROFILE);

    render(<DashboardView />);

    expect(await screen.findByText(/Salut dresseur_jf/)).toBeInTheDocument();
    expect(screen.getByText("145,50 €")).toBeInTheDocument();
    expect(screen.getByText(/sur 30 j/)).toBeInTheDocument();
  });

  it("liste les plus fortes variations avec un lien vers la fiche carte", async () => {
    vi.mocked(getDashboard).mockResolvedValue(dashboard());
    vi.mocked(getProfile).mockResolvedValue(PROFILE);

    render(<DashboardView />);

    const link = await screen.findByRole("link", { name: /Dracaufeu ex/ });
    expect(link).toHaveAttribute("href", "/carte/card-1");
  });

  it("propose le raccourci « Ajouter des photos »", async () => {
    vi.mocked(getDashboard).mockResolvedValue(dashboard());
    vi.mocked(getProfile).mockResolvedValue(PROFILE);

    render(<DashboardView />);

    await waitFor(() => {
      expect(screen.getAllByRole("link", { name: "Ajouter des photos" })[0]).toHaveAttribute(
        "href",
        "/ajouter"
      );
    });
  });

  it("affiche un état vide quand la collection n'a aucun ajout récent", async () => {
    vi.mocked(getDashboard).mockResolvedValue(
      dashboard({ items_total: 0, items_priced: 0, top_movers: [], recent_additions: [] })
    );
    vi.mocked(getProfile).mockResolvedValue(PROFILE);

    render(<DashboardView />);

    expect(await screen.findByText("Ta collection est vide")).toBeInTheDocument();
  });

  it("affiche une erreur si le tableau de bord ne charge pas", async () => {
    vi.mocked(getDashboard).mockRejectedValue(new Error("panne réseau"));
    vi.mocked(getProfile).mockResolvedValue(PROFILE);

    render(<DashboardView />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
