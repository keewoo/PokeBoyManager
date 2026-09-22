import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/app-shell";
import * as decksApi from "@/lib/api/decks";
import { ThemeProvider } from "@/lib/theme-provider";

vi.mock("next/navigation", () => ({
  usePathname: () => "/jeu/decks",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/lib/api/decks", () => ({ fetchDeckAlerts: vi.fn() }));
const api = vi.mocked(decksApi);

beforeEach(() => {
  api.fetchDeckAlerts.mockReset();
  api.fetchDeckAlerts.mockResolvedValue({ alerts: [], unread_count: 0 });
});

function renderShell(hasSession: boolean) {
  return render(
    <ThemeProvider>
      <AppShell hasSession={hasSession}>
        <p>contenu</p>
      </AppShell>
    </ThemeProvider>
  );
}

describe("AppShell — lien Decks", () => {
  it("connecté : le lien Decks pointe vers /jeu/decks et s'allume sur la page", () => {
    renderShell(true);
    const link = screen.getByRole("link", { name: "Decks" });
    expect(link).toHaveAttribute("href", "/jeu/decks");
    expect(link).toHaveAttribute("aria-current", "page");
  });

  it("visiteur : aucun lien Decks", () => {
    renderShell(false);
    expect(screen.queryByRole("link", { name: "Decks" })).not.toBeInTheDocument();
  });

  it("connecté : un badge compte les decks devenus à compléter (mission collection-sync)", async () => {
    api.fetchDeckAlerts.mockResolvedValue({ alerts: [], unread_count: 3 });
    renderShell(true);
    const badge = await screen.findByTestId("decks-alert-badge");
    expect(badge).toHaveTextContent("3");
  });

  it("connecté sans alerte : aucun badge", async () => {
    renderShell(true);
    await screen.findByRole("link", { name: "Decks" });
    expect(screen.queryByTestId("decks-alert-badge")).not.toBeInTheDocument();
  });
});
