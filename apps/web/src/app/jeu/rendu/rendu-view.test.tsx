import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RenduView } from "@/app/jeu/rendu/rendu-view";
import * as profileApi from "@/lib/api/profile";
import type { ProfileResponse } from "@/lib/api/profile";
import * as renduApi from "@/lib/api/rendu";
import type { ReglagesRendu } from "@/lib/api/rendu";
import * as navigation from "next/navigation";

// Lot `j-rendu-carte` — l'écran « Mes cartes en jeu » (DJ5). On ne substitue que les appels
// réseau : les libellés (`libelleRendu`) sont ceux du produit, les remplacer ne testerait rien.
vi.mock("next/navigation", () => ({
  notFound: vi.fn(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));
vi.mock("@/lib/api/profile", () => ({ getProfile: vi.fn() }));
vi.mock("@/lib/api/rendu", async (orig) => ({
  ...(await orig<typeof renduApi>()),
  getRenduSettings: vi.fn(),
  updateRenduSettings: vi.fn(),
}));

const profile = vi.mocked(profileApi);
const api = vi.mocked(renduApi);
const notFound = vi.mocked(navigation.notFound);

function makeProfile(gameAccess: boolean): ProfileResponse {
  return {
    id: "u-1",
    email: "joueur@example.com",
    pseudo: "joueur",
    game_access: gameAccess,
  } as unknown as ProfileResponse;
}

function makeReglages(partial: Partial<ReglagesRendu> = {}): ReglagesRendu {
  return {
    rendus_possibles: ["officielle", "photo"],
    rendu_defaut: "photo",
    jamais_montrer_mes_photos: false,
    largeur_jeu: 420,
    hauteur_jeu: 587,
    ...partial,
  };
}

describe("RenduView — mes cartes en jeu", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    profile.getProfile.mockResolvedValue(makeProfile(true));
    api.getRenduSettings.mockResolvedValue(makeReglages());
  });

  it("montre le rendu par défaut du compte, celui du serveur", async () => {
    render(<RenduView />);
    await waitFor(() => expect(screen.getByTestId("rendu-photo")).toBeChecked());
    expect(screen.getByTestId("rendu-officielle")).not.toBeChecked();
  });

  it("bascule sur les images officielles en n'envoyant QUE ce champ (PATCH partiel)", async () => {
    api.updateRenduSettings.mockResolvedValue(makeReglages({ rendu_defaut: "officielle" }));
    render(<RenduView />);
    await waitFor(() => expect(screen.getByTestId("rendu-officielle")).toBeInTheDocument());
    await userEvent.click(screen.getByTestId("rendu-officielle"));
    // Un PATCH partiel : envoyer tout l'état écraserait un réglage changé dans un autre onglet.
    expect(api.updateRenduSettings).toHaveBeenCalledWith({ rendu_defaut: "officielle" });
  });

  it("pose le veto « ne jamais montrer mes photos » et dit ce qu'il implique", async () => {
    api.updateRenduSettings.mockResolvedValue(
      makeReglages({ jamais_montrer_mes_photos: true })
    );
    render(<RenduView />);
    await waitFor(() => expect(screen.getByTestId("jamais-montrer")).toBeInTheDocument());
    await userEvent.click(screen.getByTestId("jamais-montrer"));
    expect(api.updateRenduSettings).toHaveBeenCalledWith({ jamais_montrer_mes_photos: true });
    // Le réglage protège sans priver : c'est écrit, parce qu'un réglage qu'on ne comprend pas
    // n'est pas un réglage.
    expect(screen.getByText(/tu continues de voir tes propres photos/i)).toBeInTheDocument();
  });

  it("publie la taille réelle servie en partie (le joueur peut lire le chiffre)", async () => {
    render(<RenduView />);
    await waitFor(() => expect(screen.getByText(/420×587/)).toBeInTheDocument());
  });

  it("dit que le repli sur l'officielle est automatique — jamais d'attente en partie", async () => {
    render(<RenduView />);
    await waitFor(() =>
      expect(screen.getByText(/l'image officielle prend le relais automatiquement/i)).toBeInTheDocument()
    );
  });

  it("rend une page inexistante à un compte sans accès au jeu (D11)", async () => {
    profile.getProfile.mockResolvedValue(makeProfile(false));
    render(<RenduView />);
    await waitFor(() => expect(notFound).toHaveBeenCalled());
  });

  it("dit l'échec de chargement plutôt que d'afficher des réglages qui ne sont pas les miens", async () => {
    api.getRenduSettings.mockRejectedValue(new Error("coupure"));
    render(<RenduView />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.queryByTestId("rendu-photo")).toBeNull();
  });
});
