import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/app-shell";
import type { ProfileResponse } from "@/lib/api/profile";
import * as profileApi from "@/lib/api/profile";
import { ThemeProvider } from "@/lib/theme-provider";

// Lot `j-salon-partie`, critère 5 : l'entrée « Jouer » n'apparaît qu'aux comptes avec le droit
// d'accès au jeu (D11). Pour les autres, le jeu n'existe pas à l'écran.

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/lib/api/decks", () => ({
  fetchDeckAlerts: vi.fn().mockResolvedValue({ alerts: [], unread_count: 0 }),
}));
vi.mock("@/lib/api/profile", () => ({ getProfile: vi.fn() }));
const profile = vi.mocked(profileApi);

function makeProfile(gameAccess: boolean): ProfileResponse {
  return {
    id: "u1",
    email: "joueur@example.com",
    email_verified: true,
    pending_email: null,
    pseudo: "joueur",
    has_avatar: false,
    first_name: null,
    last_name: "Dresseur",
    birth_date: "2000-01-01",
    game_access: gameAccess,
  };
}

function renderShell(hasSession: boolean) {
  return render(
    <ThemeProvider>
      <AppShell hasSession={hasSession}>
        <p>contenu</p>
      </AppShell>
    </ThemeProvider>
  );
}

beforeEach(() => {
  profile.getProfile.mockReset();
});

describe("AppShell — entrée Jouer (gating game_access)", () => {
  it("compte avec accès au jeu : le lien Jouer apparaît et pointe vers /jeu/salon", async () => {
    profile.getProfile.mockResolvedValue(makeProfile(true));
    renderShell(true);
    const link = await screen.findByRole("link", { name: "Jouer" });
    expect(link).toHaveAttribute("href", "/jeu/salon");
  });

  it("compte sans accès au jeu : aucun lien Jouer", async () => {
    profile.getProfile.mockResolvedValue(makeProfile(false));
    renderShell(true);
    // On attend que le profil soit chargé (le lien Decks est présent dès le rendu).
    await screen.findByRole("link", { name: "Decks" });
    await waitFor(() => expect(profile.getProfile).toHaveBeenCalled());
    expect(screen.queryByRole("link", { name: "Jouer" })).not.toBeInTheDocument();
  });

  it("visiteur non connecté : aucun lien Jouer, et le profil n'est pas interrogé", () => {
    renderShell(false);
    expect(screen.queryByRole("link", { name: "Jouer" })).not.toBeInTheDocument();
    expect(profile.getProfile).not.toHaveBeenCalled();
  });
});
