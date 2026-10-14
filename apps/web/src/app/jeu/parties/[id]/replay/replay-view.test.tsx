import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import * as gamesApi from "@/lib/api/games";
import type { ReplayEtape, ReplayPage } from "@/lib/api/games";
import * as profileApi from "@/lib/api/profile";
import type { ProfileResponse } from "@/lib/api/profile";

import { ReplayView } from "./replay-view";

/**
 * L'écran de replay (lot `j-replay`) — ce qu'il fait des réponses du serveur.
 *
 * Le serveur fait autorité : ce test vérifie que l'écran **n'invente rien** autour de ses réponses.
 * Un 404 devient une page inexistante ; un 409 (partie en cours) dit pourquoi il n'y a rien à
 * rejouer, **sans** afficher de plateau ; un 422 sur `vue=moi` (spectateur) bascule en vue complète
 * **en le disant**. Et la navigation est locale : avancer d'un coup n'appelle pas le serveur.
 *
 * La logique de navigation elle-même (bornes, fil du journal, complétude) est pure et testée à
 * part : `src/lib/game/replay.test.ts`.
 */

const notFound = vi.fn();
vi.mock("next/navigation", () => ({ notFound: () => notFound() }));

vi.mock("@/lib/api/profile", () => ({ getProfile: vi.fn() }));
vi.mock("@/lib/api/games", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/api/games")>();
  return {
    ...mod,
    getReplay: vi.fn(),
    listReplayPartages: vi.fn(),
    ouvrirPartageReplay: vi.fn(),
    fermerPartageReplay: vi.fn(),
  };
});

const profile = vi.mocked(profileApi);
const games = vi.mocked(gamesApi);

const JID_A = "aaaa-1111";
const JID_B = "bbbb-2222";

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

/** Une vue de plateau minimale mais suffisante pour que `GameBoard` rende. */
function vueMinimale(pour: string, terminee = false) {
  const actif = {
    cartes: [{ instance_id: "i1", ref: "mon-actif" }],
    energies: [],
    outil: null,
    compteurs_degats: 0,
    etats_speciaux: [],
    orientation: "normale",
  };
  return {
    schema_version: 1,
    pour,
    joueurs: [
      {
        id: JID_A,
        actif,
        banc: [],
        defausse: [],
        zone_perdue: [],
        pioche_nombre: 40,
        recompenses_nombre: 6,
        main: [],
      },
      {
        id: JID_B,
        actif,
        banc: [],
        defausse: [],
        zone_perdue: [],
        pioche_nombre: 40,
        recompenses_nombre: 6,
        main_nombre: 7,
      },
    ],
    tour: {
      joueur_actif: JID_A,
      numero: 0,
      phase: "principale",
      energie_posee: false,
      supporter_joue: false,
      retraite_faite: false,
    },
    stade: null,
    stade_proprietaire: null,
    terminee,
    vainqueur: terminee ? JID_A : null,
    raison_fin: terminee ? "abandon" : null,
  };
}

function etape(rang: number, destinataires: string[]): ReplayEtape {
  return {
    rang,
    coup:
      rang === 0
        ? null
        : {
            numero: rang - 1,
            auteur: JID_A,
            type: "piocher",
            horodatage: "2026-10-14T10:00:00Z",
            empreinte: `e${rang}`,
          },
    vues: Object.fromEntries(destinataires.map((d) => [d, vueMinimale(d, rang === 2)])),
    evenements: Object.fromEntries(destinataires.map((d) => [d, []])),
  };
}

function page(overrides: Partial<ReplayPage> = {}): ReplayPage {
  const destinataires = overrides.vue === "complete" ? [JID_A, JID_B] : [JID_A];
  return {
    game_id: "g1",
    statut: "terminee",
    raison_fin: "abandon",
    vainqueur_user_id: "u1",
    engagement: "deadbeef",
    graine: "a1b2",
    vue: "moi",
    joueurs: [
      { seat: 0, user_id: "u1", joueur_id: JID_A, pseudo: "Alice", bot_niveau: null },
      { seat: 1, user_id: "u2", joueur_id: JID_B, pseudo: "Bob", bot_niveau: null },
    ],
    total: 2,
    depuis: 0,
    limite: 50,
    complet: true,
    etapes: [etape(0, destinataires), etape(1, destinataires), etape(2, destinataires)],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  profile.getProfile.mockResolvedValue(makeProfile(true));
  games.listReplayPartages.mockResolvedValue([]);
});

describe("ReplayView", () => {
  it("affiche le plateau au rang 0 et la position dans la partie", async () => {
    games.getReplay.mockResolvedValue(page());
    render(<ReplayView gameId="g1" />);

    await waitFor(() => expect(screen.getByTestId("replay-controles")).toBeInTheDocument());
    expect(screen.getByTestId("replay-position")).toHaveTextContent("0 / 2");
    // Lecture seule : aucune barre d'actions (le `GameBoard` sans `onJouer` n'en rend pas).
    expect(screen.queryByTestId("barre-actions")).not.toBeInTheDocument();
  });

  it("avance et recule SANS rappeler le serveur (la navigation est locale)", async () => {
    games.getReplay.mockResolvedValue(page());
    render(<ReplayView gameId="g1" />);
    await waitFor(() => expect(screen.getByTestId("replay-position")).toHaveTextContent("0 / 2"));

    const appelsApresChargement = games.getReplay.mock.calls.length;
    await userEvent.click(screen.getByLabelText("Coup suivant"));
    expect(screen.getByTestId("replay-position")).toHaveTextContent("1 / 2");
    await userEvent.click(screen.getByLabelText("Coup suivant"));
    expect(screen.getByTestId("replay-position")).toHaveTextContent("2 / 2");
    await userEvent.click(screen.getByLabelText("Coup précédent"));
    expect(screen.getByTestId("replay-position")).toHaveTextContent("1 / 2");

    // C'est l'intérêt du lot : on rejoue le journal localement.
    expect(games.getReplay.mock.calls.length).toBe(appelsApresChargement);
  });

  it("ne sort jamais des rangs chargés : les boutons de bout sont désactivés", async () => {
    games.getReplay.mockResolvedValue(page());
    render(<ReplayView gameId="g1" />);
    await waitFor(() => expect(screen.getByTestId("replay-position")).toHaveTextContent("0 / 2"));

    expect(screen.getByLabelText("Coup précédent")).toBeDisabled();
    await userEvent.click(screen.getByLabelText("Coup suivant"));
    await userEvent.click(screen.getByLabelText("Coup suivant"));
    expect(screen.getByTestId("replay-position")).toHaveTextContent("2 / 2");
    expect(screen.getByLabelText("Coup suivant")).toBeDisabled();
  });

  it("enchaîne les pages jusqu'à `complet`, et annonce ce qui manque en route", async () => {
    const p1 = page({ total: 4, complet: false, depuis: 0 });
    const p2 = page({
      total: 4,
      complet: true,
      depuis: 3,
      etapes: [etape(3, [JID_A]), etape(4, [JID_A])],
    });
    games.getReplay.mockResolvedValueOnce(p1).mockResolvedValueOnce(p2);

    render(<ReplayView gameId="g1" />);
    await waitFor(() => expect(games.getReplay).toHaveBeenCalledTimes(2));
    // La deuxième page est demandée là où la première s'est arrêtée.
    expect(games.getReplay).toHaveBeenLastCalledWith("g1", {
      vue: "moi",
      depuis: 3,
      limite: 50,
    });
    // Tout est là : plus rien à signaler.
    await waitFor(() =>
      expect(screen.queryByTestId("replay-incomplet")).not.toBeInTheDocument(),
    );
  });

  it("dit ce qui n'est pas chargé plutôt que de laisser croire que la partie s'arrête là", async () => {
    // Une page partielle dont la suivante échoue : l'écran doit l'ÉCRIRE (règle « pas de
    // troncature muette »), sinon la fin du curseur passerait pour la fin de la partie.
    games.getReplay
      .mockResolvedValueOnce(page({ total: 10, complet: false, depuis: 0 }))
      .mockRejectedValueOnce(new ApiError(500, "Boum"));

    render(<ReplayView gameId="g1" />);
    await waitFor(() => expect(screen.getByTestId("replay-incomplet")).toBeInTheDocument());
    expect(screen.getByTestId("replay-incomplet")).toHaveTextContent("8 coup(s) non chargé(s)");
  });

  it("une partie encore en cours (409) ne montre aucun plateau, et dit pourquoi", async () => {
    games.getReplay.mockRejectedValue(
      new ApiError(409, "Partie encore en cours : son replay ne s'ouvre qu'à la fin."),
    );
    render(<ReplayView gameId="g1" />);

    await waitFor(() => expect(screen.getByTestId("replay-avis")).toBeInTheDocument());
    expect(screen.getByTestId("replay-avis")).toHaveTextContent("ne s'ouvre qu'à la fin");
    // Le critère du lot : rien de la partie n'est montré avant sa fin.
    expect(screen.queryByTestId("replay-controles")).not.toBeInTheDocument();
    expect(notFound).not.toHaveBeenCalled();
  });

  it("un compte sans droit de regarder (404) tombe sur une page inexistante", async () => {
    games.getReplay.mockRejectedValue(new ApiError(404, "Partie introuvable."));
    render(<ReplayView gameId="g1" />);
    await waitFor(() => expect(notFound).toHaveBeenCalled());
  });

  it("un spectateur (422 sur `vue=moi`) bascule en vue complète — et on le lui dit", async () => {
    games.getReplay.mockImplementation(async (_id, options) => {
      if ((options?.vue ?? "moi") === "moi") {
        throw new ApiError(422, "Vous ne jouez pas cette partie : demandez la vue complète.");
      }
      return page({ vue: "complete" });
    });

    render(<ReplayView gameId="g1" />);
    await waitFor(() => expect(screen.getByTestId("replay-avis")).toBeInTheDocument());
    expect(screen.getByTestId("replay-avis")).toHaveTextContent("vue complète");
    // Et la vue complète laisse choisir par quels yeux regarder — les deux joueurs, nommés.
    const parLesYeuxDe = await screen.findByLabelText("Regarder par les yeux de");
    expect(parLesYeuxDe).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Alice" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Bob" })).toBeInTheDocument();
  });

  it("sans droit d'accès au jeu (D11), la page n'existe pas", async () => {
    profile.getProfile.mockResolvedValue(makeProfile(false));
    games.getReplay.mockResolvedValue(page());
    render(<ReplayView gameId="g1" />);
    await waitFor(() => expect(notFound).toHaveBeenCalled());
    expect(games.getReplay).not.toHaveBeenCalled();
  });
});
