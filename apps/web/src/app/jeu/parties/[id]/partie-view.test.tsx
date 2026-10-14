import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import type { ProfileResponse } from "@/lib/api/profile";
import * as gamesApi from "@/lib/api/games";
import * as profileApi from "@/lib/api/profile";
import { PartieView } from "./partie-view";

// Le canal temps réel ouvre un WebSocket : on le remplace par une coquille inerte — ce test porte
// sur le gating et le chargement de la vue, pas sur le transport (couvert par `realtime.test.ts`).
vi.mock("@/lib/game/realtime", () => ({
  CanalPartie: class {
    constructor(public opts: unknown) {}
    demarrer() {}
    arreter() {}
  },
}));

const notFound = vi.fn();
// `useRouter` est exigé par l'écran de fin (lot `j-partie-fin-ui`), rendu quand la partie est
// terminée : sans lui dans le mock, le rendu casserait sur la seule partie finie de ce fichier.
const push = vi.fn();
vi.mock("next/navigation", () => ({
  notFound: () => notFound(),
  useRouter: () => ({ push }),
}));

vi.mock("@/lib/api/profile", () => ({ getProfile: vi.fn() }));
vi.mock("@/lib/api/games", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/api/games")>();
  // `getRecapitulatif` et `listGames` sont ceux que l'écran de fin appelle quand la partie
  // est terminée : sans eux, le test de la fin mesurerait un vrai `fetch` absent de jsdom.
  return {
    ...mod,
    getGameState: vi.fn(),
    getRecapitulatif: vi.fn(),
    listGames: vi.fn(),
  };
});

const profile = vi.mocked(profileApi);
const games = vi.mocked(gamesApi);

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

function etatMinimal() {
  const actif = {
    cartes: [{ instance_id: "i1", ref: "mon-actif" }],
    energies: [],
    outil: null,
    compteurs_degats: 0,
    etats_speciaux: [],
    orientation: "normale",
  };
  return {
    vue: {
      schema_version: 1,
      pour: "a",
      joueurs: [
        { id: "a", actif, banc: [], defausse: [], zone_perdue: [], pioche_nombre: 40, recompenses_nombre: 6, main: [] },
        { id: "b", actif, banc: [], defausse: [], zone_perdue: [], pioche_nombre: 40, recompenses_nombre: 6, main_nombre: 7 },
      ],
      tour: { joueur_actif: "a", numero: 0, phase: "principale", energie_posee: false, supporter_joue: false, retraite_faite: false },
      stade: null,
      stade_proprietaire: null,
      terminee: false,
      vainqueur: null,
      raison_fin: null,
    },
    evenements: [],
  };
}

beforeEach(() => {
  notFound.mockReset();
  push.mockReset();
  profile.getProfile.mockReset();
  games.getGameState.mockReset();
  games.getRecapitulatif.mockReset();
  games.listGames.mockReset();
  games.listGames.mockResolvedValue([]);
});

describe("PartieView — gating d'accès", () => {
  it("rend une page inexistante à un compte sans droit d'accès au jeu (D11)", async () => {
    profile.getProfile.mockResolvedValue(makeProfile(false));
    render(<PartieView gameId="g1" />);
    await waitFor(() => expect(notFound).toHaveBeenCalled());
    expect(games.getGameState).not.toHaveBeenCalled();
  });

  it("rend une page inexistante quand la partie n'appartient pas au joueur (404)", async () => {
    profile.getProfile.mockResolvedValue(makeProfile(true));
    games.getGameState.mockRejectedValue(new ApiError(404, "introuvable"));
    render(<PartieView gameId="g1" />);
    await waitFor(() => expect(notFound).toHaveBeenCalled());
  });
});

describe("PartieView — chargement du plateau", () => {
  it("charge la vue autoritaire et affiche le plateau", async () => {
    profile.getProfile.mockResolvedValue(makeProfile(true));
    games.getGameState.mockResolvedValue(etatMinimal());
    render(<PartieView gameId="g1" />);
    await waitFor(() => expect(screen.getByTestId("plateau")).toBeInTheDocument());
    expect(screen.getByText("Toi")).toBeInTheDocument();
    expect(notFound).not.toHaveBeenCalled();
  });
});

describe("PartieView — fin de partie", () => {
  it("n'affiche aucun écran de fin tant que la partie n'est pas terminée", async () => {
    profile.getProfile.mockResolvedValue(makeProfile(true));
    games.getGameState.mockResolvedValue(etatMinimal());
    render(<PartieView gameId="g1" />);
    await waitFor(() => expect(screen.getByTestId("plateau")).toBeInTheDocument());
    expect(screen.queryByTestId("fin-partie")).not.toBeInTheDocument();
    // Et le récapitulatif n'est même pas demandé : une partie en cours n'en a pas (409 serveur).
    expect(games.getRecapitulatif).not.toHaveBeenCalled();
  });

  it("affiche l'écran de fin quand le serveur déclare la partie terminée", async () => {
    // La fin est décidée par le serveur (`vue.terminee`), jamais déduite ici : c'est la seule
    // condition de déclenchement. Les chiffres, eux, viennent du récapitulatif — le plateau ne
    // compte rien (un F5 rejoue toute la partie, un compteur local doublerait).
    profile.getProfile.mockResolvedValue(makeProfile(true));
    const base = etatMinimal();
    const etat = {
      ...base,
      vue: {
        ...base.vue,
        terminee: true,
        vainqueur: "a",
        raison_fin: "derniere_recompense",
      },
    };
    games.getGameState.mockResolvedValue(etat);
    games.getRecapitulatif.mockResolvedValue({
      game_id: "g1",
      statut: "terminee",
      raison_fin: "derniere_recompense",
      vainqueur_user_id: "u1",
      entrainement: false,
      coups: 12,
      tours: 3,
      debut: "2026-10-14T10:00:00+00:00",
      fin: "2026-10-14T10:02:00+00:00",
      duree_s: 120,
      joueurs: [],
      meilleur_coup: null,
    });

    render(<PartieView gameId="g1" />);
    // L'annonce arrive d'abord sans résultat (« Partie terminée ») : le vainqueur ne vient que du
    // récapitulatif, et on n'en invente pas un en attendant.
    expect(await screen.findByTestId("fin-partie")).toBeInTheDocument();
    expect(games.getRecapitulatif).toHaveBeenCalledWith("g1");
    // Puis le récapitulatif arrive, et le profil donne `id: "u1"` : le vainqueur, c'est moi.
    await waitFor(() =>
      expect(screen.getByTestId("fin-partie-titre")).toHaveTextContent("Gagné"),
    );
    // Le plateau reste rendu derrière : l'écran de fin ne le remplace pas.
    expect(screen.getByTestId("plateau")).toBeInTheDocument();
  });
});
