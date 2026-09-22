import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/app-shell";
import { ThemeProvider } from "@/lib/theme-provider";

vi.mock("next/navigation", () => ({
  usePathname: () => "/jeu/decks",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

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
});
