import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/app-shell";
import { ThemeProvider } from "@/lib/theme-provider";

vi.mock("next/navigation", () => ({
  usePathname: () => "/collection",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

describe("AppShell", () => {
  it("marque le lien de navigation actif via aria-current", () => {
    render(
      <ThemeProvider>
        <AppShell hasSession>
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

  it("visiteur : propose inscription/connexion, jamais profil ni déconnexion", () => {
    render(
      <ThemeProvider>
        <AppShell hasSession={false}>
          <p>contenu</p>
        </AppShell>
      </ThemeProvider>
    );
    expect(screen.getByRole("link", { name: "Connexion" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Inscription" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Profil" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Collection" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Déconnexion/ })).not.toBeInTheDocument();
  });

  it("connecté : propose profil et déconnexion, jamais inscription/connexion", () => {
    render(
      <ThemeProvider>
        <AppShell hasSession>
          <p>contenu</p>
        </AppShell>
      </ThemeProvider>
    );
    expect(screen.getByRole("link", { name: "Profil" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Déconnexion/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Connexion" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Inscription" })).not.toBeInTheDocument();
  });
});
