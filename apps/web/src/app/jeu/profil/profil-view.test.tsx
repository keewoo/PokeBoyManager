import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as navigation from "next/navigation";

import { ProfilJeuView } from "@/app/jeu/profil/profil-view";
import * as collectionApi from "@/lib/api/collection";
import type { CollectionListItem, CollectionListResponse } from "@/lib/api/collection";
import * as profileApi from "@/lib/api/profile";
import type { ProfileResponse } from "@/lib/api/profile";
import * as profilJeuApi from "@/lib/api/profil-jeu";
import type { ProfilJeu } from "@/lib/api/profil-jeu";

// Lot `j-profil-jeu` — la vitrine du profil de joueur (DJ6). On ne substitue que les appels
// réseau : les libellés (`libelleMesure`, `libelleDecor`) sont ceux du produit, les remplacer ne
// testerait rien. `ApiError` non plus n'est pas substitué — c'est lui qui porte le message du 422,
// et c'est précisément ce que l'écran doit afficher tel quel.
vi.mock("next/navigation", () => ({
  notFound: vi.fn(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));
vi.mock("@/lib/api/profile", async (orig) => ({
  ...(await orig<typeof profileApi>()),
  getProfile: vi.fn(),
}));
vi.mock("@/lib/api/profil-jeu", async (orig) => ({
  ...(await orig<typeof profilJeuApi>()),
  getProfilJeu: vi.fn(),
  poserCarteFetiche: vi.fn(),
}));
vi.mock("@/lib/api/collection", async (orig) => ({
  ...(await orig<typeof collectionApi>()),
  listCollection: vi.fn(),
}));

const profile = vi.mocked(profileApi);
const api = vi.mocked(profilJeuApi);
const collection = vi.mocked(collectionApi);
const notFound = vi.mocked(navigation.notFound);

function makeProfile(gameAccess: boolean): ProfileResponse {
  return {
    id: "u-1",
    email: "joueur@example.com",
    pseudo: "Ash",
    game_access: gameAccess,
  } as unknown as ProfileResponse;
}

function makeVitrine(partial: Partial<ProfilJeu> = {}): ProfilJeu {
  return {
    pseudo: "Ash",
    a_un_avatar: false,
    carte_fetiche: null,
    badges_actifs: true,
    badges: [
      {
        code: "premiere-victoire",
        nom: "Première victoire",
        description: "Gagner une partie contre un autre joueur.",
        mesure: "issue",
        obtenu: true,
        obtenu_a: "2026-10-14T18:00:00+00:00",
        game_id: "g-1",
      },
      {
        code: "ko-en-un-coup",
        nom: "K.O. en un coup",
        description: "Mettre K.O. un Pokémon encore intact, d'une seule attaque.",
        mesure: "exploit",
        obtenu: false,
        obtenu_a: null,
        game_id: null,
      },
    ],
    mesures_possibles: ["construction", "exploit", "issue", "volume"],
    palier_parties: 10,
    decors: ["arene", "caldeira", "lagon", "orage", "temple", "faille"],
    decor_choisi: "lagon",
    ...partial,
  };
}

function makeCarte(partial: Partial<CollectionListItem> = {}): CollectionListItem {
  return {
    id: "item-1",
    card_id: "card-1",
    set_id: "set-1",
    card_name: "Pikachu",
    card_number: "58",
    set_name: "Base",
    set_code: "base",
    series: null,
    rarity: null,
    card_type: "Pokémon",
    element_type: "lightning",
    hp: 60,
    language: "fr",
    variant: "normal",
    condition_grade: null,
    counterfeit_suspected: false,
    purchase_price: null,
    purchase_currency: null,
    acquired_at: null,
    value_eur: null,
    value_change_30d_eur: null,
    value_change_30d_pct: null,
    is_duplicate: false,
    ...partial,
  };
}

function makePage(items: CollectionListItem[]): CollectionListResponse {
  return {
    items,
    next_cursor: null,
    aggregates: {
      items_total: items.length,
      items_priced: 0,
      items_missing_price: items.length,
      total_value_eur: "0",
      value_change_7d_eur: "0",
      value_change_30d_eur: "0",
    },
  };
}

describe("ProfilJeuView — ma vitrine de joueur", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    profile.getProfile.mockResolvedValue(makeProfile(true));
    api.getProfilJeu.mockResolvedValue(makeVitrine());
    collection.listCollection.mockResolvedValue(makePage([makeCarte()]));
  });

  it("reprend le pseudo du compte et montre les badges, obtenus comme à obtenir", async () => {
    render(<ProfilJeuView />);
    await waitFor(() => expect(screen.getByTestId("pseudo")).toHaveTextContent("Ash"));

    const badges = screen.getAllByTestId("badge");
    expect(badges).toHaveLength(2);
    expect(badges[0]).toHaveAttribute("data-obtenu", "oui");
    // Un badge non obtenu reste visible AVEC sa description : c'est un objectif, pas un mystère.
    expect(badges[1]).toHaveAttribute("data-obtenu", "non");
    expect(badges[1]).toHaveTextContent("d'une seule attaque");
  });

  it("dit que les badges sont éteints sans afficher de grille vide", async () => {
    api.getProfilJeu.mockResolvedValue(makeVitrine({ badges_actifs: false, badges: [] }));
    render(<ProfilJeuView />);
    await waitFor(() => expect(screen.getByTestId("badges-eteints")).toBeInTheDocument());
    expect(screen.queryAllByTestId("badge")).toHaveLength(0);
    // L'identité reste affichée : ce n'est pas la même option.
    expect(screen.getByTestId("pseudo")).toHaveTextContent("Ash");
  });

  it("montre les six décors, aucun verrouillé, celui du joueur marqué", async () => {
    render(<ProfilJeuView />);
    await waitFor(() => expect(screen.getByTestId("decors")).toBeInTheDocument());
    const items = screen.getByTestId("decors").querySelectorAll("li");
    expect(items).toHaveLength(6);
    const choisis = [...items].filter((li) => li.getAttribute("data-choisi") === "oui");
    expect(choisis).toHaveLength(1);
    expect(choisis[0]).toHaveAttribute("data-decor", "lagon");
  });

  it("choisit une carte fétiche dans la collection et affiche celle que le serveur renvoie", async () => {
    api.poserCarteFetiche.mockResolvedValue(
      makeVitrine({
        carte_fetiche: {
          card_id: "card-1",
          nom: "Pikachu",
          rendu: {
            origine: "photo",
            url: "/jeu/rendu/lancements/l-1/photos/item-1?v=zoom",
            url_zoom: "/jeu/rendu/lancements/l-1/photos/item-1?v=zoom",
            credit: null,
            raison: null,
            url_repli: "/img/cards/card-1?size=low",
          },
        },
      })
    );
    render(<ProfilJeuView />);
    await waitFor(() => expect(screen.getByTestId("sans-fetiche")).toBeInTheDocument());

    await userEvent.click(screen.getByTestId("chercher-fetiche"));
    await waitFor(() => expect(screen.getByTestId("cartes-proposees")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /Choisir Pikachu/ }));

    expect(api.poserCarteFetiche).toHaveBeenCalledWith("card-1");
    await waitFor(() =>
      expect(screen.getByTestId("carte-fetiche")).toHaveAttribute("data-card-id", "card-1")
    );
  });

  it("affiche la raison du serveur quand l'adversaire verra l'image officielle", async () => {
    api.getProfilJeu.mockResolvedValue(
      makeVitrine({
        carte_fetiche: {
          card_id: "card-9",
          nom: "Bulbizarre",
          rendu: {
            origine: "officielle",
            url: "/img/cards/card-9?size=low",
            url_zoom: "/img/cards/card-9?size=high",
            credit: null,
            raison: "hors d'une partie, les photos ne sont pas servies",
            url_repli: null,
          },
        },
      })
    );
    render(<ProfilJeuView />);
    await waitFor(() =>
      expect(screen.getByTestId("raison-rendu")).toHaveTextContent(
        "hors d'une partie, les photos ne sont pas servies"
      )
    );
  });

  it("affiche le refus du serveur tel quel quand la carte n'est pas possédée", async () => {
    const { ApiError } = await import("@/lib/api/client");
    api.poserCarteFetiche.mockRejectedValue(
      new ApiError(422, "cette carte n'est pas dans ta collection")
    );
    render(<ProfilJeuView />);
    await waitFor(() => expect(screen.getByTestId("sans-fetiche")).toBeInTheDocument());

    await userEvent.click(screen.getByTestId("chercher-fetiche"));
    await waitFor(() => expect(screen.getByTestId("cartes-proposees")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /Choisir Pikachu/ }));

    await waitFor(() =>
      expect(screen.getByText(/pas dans ta collection/)).toBeInTheDocument()
    );
  });

  it("rend une page inexistante à un compte sans accès au jeu (D11)", async () => {
    profile.getProfile.mockResolvedValue(makeProfile(false));
    render(<ProfilJeuView />);
    await waitFor(() => expect(notFound).toHaveBeenCalled());
  });
});
