import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/app-shell";
import { ThemeProvider } from "@/lib/theme-provider";

vi.mock("next/navigation", () => ({
  usePathname: () => "/collection",
}));

describe("AppShell", () => {
  it("marque le lien de navigation actif via aria-current", () => {
    render(
      <ThemeProvider>
        <AppShell>
          <p>contenu</p>
        </AppShell>
      </ThemeProvider>
    );
    expect(screen.getByRole("link", { name: "Collection" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Accueil" })).not.toHaveAttribute("aria-current");
  });

  it("affiche les enfants dans le contenu principal", () => {
    render(
      <ThemeProvider>
        <AppShell>
          <p>contenu du test</p>
        </AppShell>
      </ThemeProvider>
    );
    expect(screen.getByText("contenu du test")).toBeInTheDocument();
  });
});
