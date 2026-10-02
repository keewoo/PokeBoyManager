import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SalonView } from "@/app/jeu/salon/salon-view";
import * as decksApi from "@/lib/api/decks";
import type { DeckSummary } from "@/lib/api/decks";
import * as gamesApi from "@/lib/api/games";
import type { GameSummary } from "@/lib/api/games";
import * as invitationsApi from "@/lib/api/invitations";
import type { Invitation } from "@/lib/api/invitations";
import * as matchmakingApi from "@/lib/api/matchmaking";
import type { FileState, Presence } from "@/lib/api/matchmaking";
import * as navigation from "next/navigation";
import * as profileApi from "@/lib/api/profile";
import type { ProfileResponse } from "@/lib/api/profile";

// On préserve les constantes (`GAME_EN_COURS`, `FILE_*`, `INVITATION_EN_ATTENTE`) et on ne remplace
// que les fonctions d'appel : l'écran lit ces constantes pour discriminer les états.
vi.mock("next/navigation", () => ({
  notFound: vi.fn(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));
vi.mock("@/lib/api/profile", () => ({ getProfile: vi.fn() }));
vi.mock("@/lib/api/games", async (orig) => ({
  ...(await orig<typeof gamesApi>()),
  listGames: vi.fn(),
}));
vi.mock("@/lib/api/decks", async (orig) => ({
  ...(await orig<typeof decksApi>()),
  listDecks: vi.fn(),
}));
vi.mock("@/lib/api/matchmaking", async (orig) => ({
  ...(await orig<typeof matchmakingApi>()),
  getQueue: vi.fn(),
  enterQueue: vi.fn(),
  leaveQueue: vi.fn(),
  getPresence: vi.fn(),
  checkDeckPlayable: vi.fn(),
}));
vi.mock("@/lib/api/invitations", async (orig) => ({
  ...(await orig<typeof invitationsApi>()),
  listReceivedInvitations: vi.fn(),
  acceptInvitation: vi.fn(),
  refuseInvitation: vi.fn(),
  createInviteLink: vi.fn(),
}));

const profile = vi.mocked(profileApi);
const games = vi.mocked(gamesApi);
const decks = vi.mocked(decksApi);
const matchmaking = vi.mocked(matchmakingApi);
const invitations = vi.mocked(invitationsApi);
const notFound = vi.mocked(navigation.notFound);

function makeProfile(gameAccess: boolean): ProfileResponse {
  return {
    id: "me",
    email: "me@example.com",
    email_verified: true,
    pending_email: null,
    pseudo: "moi",
    has_avatar: false,
    first_name: null,
    last_name: "Dresseur",
    birth_date: "2000-01-01",
    game_access: gameAccess,
  };
}

function game(over: Partial<GameSummary> = {}): GameSummary {
  return {
    id: "g1",
    status: "en_cours",
    current_numero: 3,
    vainqueur_user_id: null,
    raison_fin: null,
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-01T10:05:00Z",
    ...over,
  };
}

function deck(over: Partial<DeckSummary> = {}): DeckSummary {
  return {
    id: "d1",
    name: "Deck feu",
    format: "standard",
    card_count: 20,
    legal: true,
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-01T10:00:00Z",
    ...over,
  };
}

function file(over: Partial<FileState> = {}): FileState {
  return {
    status: "absent",
    game_id: null,
    adversaire_user_id: null,
    position: null,
    joueurs_en_file: null,
    attente_secondes: null,
    ...over,
  };
}

function presence(over: Partial<Presence> = {}): Presence {
  return { en_ligne: 2, en_partie: 0, en_file: 0, autres_disponibles: 1, options: [], ...over };
}

function invitation(over: Partial<Invitation> = {}): Invitation {
  return {
    id: "i1",
    mode: "pseudo",
    statut: "en_attente",
    inviter_user_id: "autre",
    invitee_user_id: "me",
    inviter_deck_id: null,
    invitee_deck_id: null,
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  profile.getProfile.mockResolvedValue(makeProfile(true));
  games.listGames.mockResolvedValue([]);
  decks.listDecks.mockResolvedValue({ decks: [] });
  matchmaking.getQueue.mockResolvedValue(file());
  matchmaking.getPresence.mockResolvedValue(presence());
  matchmaking.checkDeckPlayable.mockResolvedValue({ deck_id: "d1", jouable: true, refus: [] });
  invitations.listReceivedInvitations.mockResolvedValue([]);
});

describe("SalonView", () => {
  it("compte sans accès au jeu : page inexistante (notFound)", async () => {
    profile.getProfile.mockResolvedValue(makeProfile(false));
    render(<SalonView />);
    await waitFor(() => expect(notFound).toHaveBeenCalled());
  });

  it("met la reprise d'une partie en cours en tête, reprenable en un clic", async () => {
    games.listGames.mockResolvedValue([game({ id: "g42", status: "en_cours" })]);
    render(<SalonView />);
    const reprise = await screen.findByTestId("reprise");
    const link = within(reprise).getByRole("link", { name: "Reprendre" });
    expect(link).toHaveAttribute("href", "/jeu/parties/g42");
  });

  it("affiche la jouabilité d'un deck AVANT l'entrée, et autorise l'entrée si jouable", async () => {
    decks.listDecks.mockResolvedValue({ decks: [deck({ id: "d1", name: "Feu" })] });
    matchmaking.checkDeckPlayable.mockResolvedValue({ deck_id: "d1", jouable: true, refus: [] });
    render(<SalonView />);
    await screen.findByText("Deck jouable");
    expect(matchmaking.checkDeckPlayable).toHaveBeenCalledWith("d1");
    expect(screen.getByRole("button", { name: "Entrer dans la file" })).toBeEnabled();
  });

  it("deck non jouable : les cartes en cause sont nommées et l'entrée est bloquée (D9)", async () => {
    decks.listDecks.mockResolvedValue({ decks: [deck({ id: "d1" })] });
    matchmaking.checkDeckPlayable.mockResolvedValue({
      deck_id: "d1",
      jouable: false,
      refus: [{ carte: "Insolourdo", raison: "effet non scripté" }],
    });
    render(<SalonView />);
    await screen.findByText(/Insolourdo/);
    expect(screen.getByText(/effet non scripté/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Entrer dans la file" })).toBeDisabled();
  });

  it("personne en ligne : propose concrètement d'inviter ou de s'entraîner", async () => {
    matchmaking.getPresence.mockResolvedValue(
      presence({ autres_disponibles: 0, options: ["invitation", "entrainement_bot"] })
    );
    render(<SalonView />);
    expect(await screen.findByRole("button", { name: "Inviter un ami" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "S'entraîner contre le bot (bientôt)" })
    ).toBeDisabled();
  });

  it("partie trouvée : on peut la rejoindre en un clic", async () => {
    matchmaking.getQueue.mockResolvedValue(file({ status: "apparie", game_id: "gX" }));
    render(<SalonView />);
    const apparie = await screen.findByTestId("salon-apparie");
    expect(within(apparie).getByRole("link", { name: "Rejoindre la partie" })).toHaveAttribute(
      "href",
      "/jeu/parties/gX"
    );
  });

  it("montre les invitations reçues en attente, acceptables depuis le salon", async () => {
    invitations.listReceivedInvitations.mockResolvedValue([invitation({ id: "i7" })]);
    render(<SalonView />);
    const section = await screen.findByTestId("salon-invitations");
    expect(within(section).getByRole("button", { name: "Accepter" })).toBeInTheDocument();
  });

  it("rappelle le dernier résultat (partie close la plus récente)", async () => {
    games.listGames.mockResolvedValue([
      game({ id: "gw", status: "terminee", vainqueur_user_id: "me" }),
    ]);
    render(<SalonView />);
    const resultat = await screen.findByTestId("salon-dernier-resultat");
    expect(resultat).toHaveTextContent("Victoire");
  });
});
