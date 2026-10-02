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
vi.mock("next/navigation", () => ({ notFound: () => notFound() }));

vi.mock("@/lib/api/profile", () => ({ getProfile: vi.fn() }));
vi.mock("@/lib/api/games", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/api/games")>();
  return { ...mod, getGameState: vi.fn() };
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
  profile.getProfile.mockReset();
  games.getGameState.mockReset();
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
