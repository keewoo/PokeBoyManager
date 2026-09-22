import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/app-shell";
import { ThemeProvider } from "@/lib/theme-provider";

vi.mock("next/navigation", () => ({
  usePathname: () => "/collection",
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

describe("AppShell", () => {
  it("marque le lien de navigation actif via aria-current (connecté)", () => {
    renderShell(true);
    expect(screen.getByRole("link", { name: "Collection" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Tableau de bord" })).not.toHaveAttribute("aria-current");
  });

  it("affiche les enfants dans le contenu principal", () => {
    renderShell(false);
    expect(screen.getByText("contenu")).toBeInTheDocument();
  });

  it("visiteur : présentation, connexion, inscription — jamais les pages privées", () => {
    renderShell(false);

    expect(screen.getByRole("link", { name: "Présentation" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Connexion" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Inscription" })).toBeInTheDocument();

    expect(screen.queryByRole("link", { name: "Collection" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Ajouter" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Profil" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Tableau de bord" })).not.toBeInTheDocument();
  });

  it("connecté : tableau de bord, collection, ajouter, profil — jamais connexion/inscription", () => {
    renderShell(true);

    expect(screen.getByRole("link", { name: "Tableau de bord" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Collection" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ajouter" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Profil" })).toBeInTheDocument();

    expect(screen.queryByRole("link", { name: "Connexion" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Inscription" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Présentation" })).not.toBeInTheDocument();
  });

  // La charte définit une seule apparence : le sélecteur de thème a été retiré plutôt que
  // laissé en place sans effet. L'en-tête ne porte plus qu'une marque, le logotype.
  // La charte définit une seule apparence : le sélecteur de thème a été retiré plutôt que
  // laissé en place sans effet. Dans une barre d'application, la marque est l'ICÔNE plus le
  // mot-symbole — le logotype complet, qui porte sa signature, n'y serait pas lisible.
  it("l'en-tête porte l'icône et le mot-symbole, et pas de sélecteur de thème", () => {
    renderShell(false);
    const marque = screen.getByRole("link", { name: /PokéBoy — accueil/i });
    expect(marque).toBeInTheDocument();
    expect(marque.querySelector("img")).toHaveAttribute("src", "/icons/icon-192.png");
    expect(
      screen.queryByRole("button", { name: /passer au thème (clair|sombre)/i })
    ).not.toBeInTheDocument();
  });

  it("le bouton de menu mobile annonce son état via aria-expanded", async () => {
    const user = userEvent.setup();
    renderShell(false);

    const toggle = screen.getByRole("button", { name: "Ouvrir le menu" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await user.click(toggle);

    expect(screen.getByRole("button", { name: "Fermer le menu" })).toHaveAttribute(
      "aria-expanded",
      "true"
    );
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
