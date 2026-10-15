import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MesPartiesView } from "@/app/jeu/parties/mes-parties-view";
import * as navigation from "next/navigation";
import * as profileApi from "@/lib/api/profile";
import type { ProfileResponse } from "@/lib/api/profile";
import * as statsApi from "@/lib/api/stats-joueur";
import type {
  HistoriqueParties,
  PartieJouee,
  StatistiquesJoueur,
  StatsDeck,
  Taux,
} from "@/lib/api/stats-joueur";

// Écran « Mes parties » (lot `j-stats-joueur`). Les fonctions de libellé (`libelleTaux`,
// `phraseNonSignificatif`, `libelleDuree`) ne sont PAS substituées : ce sont elles qui portent la
// mise en garde sur les petits nombres, et les remplacer ne testerait plus rien d'utile. Seuls les
// deux appels réseau le sont.
vi.mock("next/navigation", () => ({
  notFound: vi.fn(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));
vi.mock("@/lib/api/profile", () => ({ getProfile: vi.fn() }));
vi.mock("@/lib/api/stats-joueur", async (orig) => ({
  ...(await orig<typeof statsApi>()),
  listMesParties: vi.fn(),
  getMesStatistiques: vi.fn(),
}));

const profile = vi.mocked(profileApi);
const api = vi.mocked(statsApi);
const notFound = vi.mocked(navigation.notFound);

function makeProfile(gameAccess: boolean): ProfileResponse {
  return {
    id: "u-1",
    email: "joueur@example.com",
    pseudo: "jf",
    game_access: gameAccess,
  } as unknown as ProfileResponse;
}

/** Un taux cohérent : les colonnes se recomptent, comme le serveur les rend. */
function makeTaux(victoires: number, defaites: number, egalites = 0, seuil = 5): Taux {
  const parties = victoires + defaites + egalites;
  return {
    parties,
    victoires,
    defaites,
    egalites,
    pourcentage: parties === 0 ? null : Math.round((victoires * 100) / parties),
    significatif: parties >= seuil,
    parties_manquantes: Math.max(0, seuil - parties),
  };
}

function makeDeck(partial: Partial<StatsDeck> = {}): StatsDeck {
  return {
    deck_id: "d-1",
    deck_nom: "Brasier",
    taux: makeTaux(3, 0),
    chiffres: {
      parties: 3,
      degats_infliges: 300,
      kos_infliges: 6,
      recompenses_prises: 9,
      cartes_jouees: 40,
      energies_attachees: 12,
      coups_joues: 60,
      degats_par_partie: 100,
      coups_par_partie: 20,
    },
    duree_moyenne_s: 900,
    derniere_partie_a: "2026-10-10T18:00:00Z",
    adversaires: [
      {
        user_id: "u-2",
        pseudo: "aymeric",
        bot: false,
        taux: makeTaux(3, 0),
        derniere_partie_a: "2026-10-10T18:00:00Z",
      },
    ],
    ...partial,
  };
}

function makeStats(partial: Partial<StatistiquesJoueur> = {}): StatistiquesJoueur {
  const deck = makeDeck();
  return {
    seuil_significativite: 5,
    totaux: {
      taux: makeTaux(3, 0),
      serie_en_cours: 3,
      meilleure_serie: 3,
      temps_jeu_s: 2700,
      parties_entrainement: 1,
      temps_jeu_entrainement_s: 600,
      premiere_partie_a: "2026-10-01T18:00:00Z",
      derniere_partie_a: "2026-10-10T18:00:00Z",
    },
    chiffres: deck.chiffres,
    par_deck: [deck],
    par_adversaire: deck.adversaires,
    ...partial,
  };
}

function makePartie(partial: Partial<PartieJouee> = {}): PartieJouee {
  return {
    game_id: "g-1",
    finie_a: "2026-10-10T18:00:00Z",
    resultat: "victoire",
    raison_fin: "derniere_recompense",
    comptabilisee: true,
    entrainement: false,
    deck_id: "d-1",
    deck_nom: "Brasier",
    adversaire_user_id: "u-2",
    adversaire_pseudo: "aymeric",
    adversaire_bot: false,
    duree_s: 900,
    replay_disponible: true,
    ...partial,
  };
}

function makeHistorique(parties: PartieJouee[], total = parties.length): HistoriqueParties {
  return { total, limite: 20, offset: 0, parties };
}

describe("MesPartiesView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    profile.getProfile.mockResolvedValue(makeProfile(true));
    api.getMesStatistiques.mockResolvedValue(makeStats());
    api.listMesParties.mockResolvedValue(makeHistorique([makePartie()]));
  });

  it("affiche mes totaux, mes decks et mon historique", async () => {
    render(<MesPartiesView />);

    await waitFor(() => expect(screen.getAllByTestId("taux").length).toBeGreaterThan(0));
    expect(screen.getByText("Mes parties")).toBeInTheDocument();
    // La série et son record, le deck, l'adversaire, et la partie listée.
    expect(screen.getByText("record : 3")).toBeInTheDocument();
    expect(screen.getByTestId("deck")).toHaveAttribute("data-deck-id", "d-1");
    expect(screen.getByTestId("partie")).toHaveAttribute("data-resultat", "victoire");
    expect(screen.getAllByText(/aymeric/).length).toBeGreaterThan(0);
  });

  it("marque les taux calculés sur moins de cinq parties et dit ce qui manque", async () => {
    // **Le critère d'acceptation du lot, côté écran.** Trois victoires sur trois : 100 % s'affiche
    // (le masquer ressemblerait à un bug) mais la mise en garde est posée, chiffrée.
    render(<MesPartiesView />);

    await waitFor(() => expect(screen.getAllByTestId("non-significatif").length).toBeGreaterThan(0));
    const mises_en_garde = screen.getAllByTestId("non-significatif");
    expect(mises_en_garde[0]).toHaveTextContent("Sur 3 parties seulement");
    expect(mises_en_garde[0]).toHaveTextContent("encore 2");
    // Et aucun taux n'est présenté comme significatif tant que le seuil n'est pas atteint.
    for (const taux of screen.getAllByTestId("taux")) {
      expect(taux).toHaveAttribute("data-significatif", "non");
    }
  });

  it("ne met aucune réserve quand le taux porte sur assez de parties", async () => {
    const taux = makeTaux(6, 2);
    api.getMesStatistiques.mockResolvedValue(
      makeStats({
        totaux: { ...makeStats().totaux, taux },
        par_deck: [makeDeck({ taux, adversaires: [] })],
        par_adversaire: [],
      })
    );
    render(<MesPartiesView />);

    // Plusieurs blocs portent le même taux (totaux et deck) : on vérifie qu'ils sont tous
    // présentés comme significatifs, pas seulement qu'un pourcentage est affiché quelque part.
    await waitFor(() => expect(screen.getAllByText("75 %").length).toBeGreaterThan(0));
    expect(screen.queryByTestId("non-significatif")).not.toBeInTheDocument();
    for (const bloc of screen.getAllByTestId("taux")) {
      expect(bloc).toHaveAttribute("data-significatif", "oui");
    }
  });

  it("ne propose pas de replay pour une partie purgée, et explique pourquoi", async () => {
    api.listMesParties.mockResolvedValue(
      makeHistorique([makePartie({ replay_disponible: false })])
    );
    render(<MesPartiesView />);

    await waitFor(() => expect(screen.getByTestId("replay-absent")).toBeInTheDocument());
    expect(screen.queryByTestId("lien-replay")).not.toBeInTheDocument();
  });

  it("lie chaque partie à son replay", async () => {
    render(<MesPartiesView />);

    await waitFor(() => expect(screen.getByTestId("lien-replay")).toBeInTheDocument());
    expect(screen.getByTestId("lien-replay")).toHaveAttribute(
      "href",
      "/jeu/parties/g-1/replay"
    );
  });

  it("signale une partie d'entraînement qui ne compte pas", async () => {
    api.listMesParties.mockResolvedValue(
      makeHistorique([
        makePartie({
          comptabilisee: false,
          entrainement: true,
          adversaire_bot: true,
          adversaire_pseudo: null,
        }),
      ])
    );
    render(<MesPartiesView />);

    await waitFor(() => expect(screen.getByTestId("hors-compte")).toBeInTheDocument());
    expect(screen.getByTestId("hors-compte")).toHaveTextContent("ne compte pas");
  });

  it("nomme un deck supprimé au lieu de le fondre dans un autre", async () => {
    api.getMesStatistiques.mockResolvedValue(
      makeStats({ par_deck: [makeDeck({ deck_id: null, deck_nom: null })] })
    );
    render(<MesPartiesView />);

    await waitFor(() => expect(screen.getByText("Deck supprimé")).toBeInTheDocument());
    // Et il n'est pas proposé au filtre : on ne filtre pas sur un deck qui n'existe plus.
    expect(screen.queryByRole("option", { name: "Deck supprimé" })).not.toBeInTheDocument();
  });

  it("filtre l'historique par résultat sans recharger la page", async () => {
    render(<MesPartiesView />);
    await waitFor(() => expect(api.listMesParties).toHaveBeenCalled());

    await userEvent.selectOptions(screen.getByLabelText(/Résultat/), "defaite");

    await waitFor(() =>
      expect(api.listMesParties).toHaveBeenLastCalledWith(
        expect.objectContaining({ resultat: "defaite", offset: 0 })
      )
    );
  });

  it("masque l'entraînement sur demande, mais le montre par défaut", async () => {
    render(<MesPartiesView />);
    await waitFor(() => expect(api.listMesParties).toHaveBeenCalled());
    // Par défaut, aucun filtre d'entraînement : un historique amputé d'office ferait croire à
    // une perte de parties.
    expect(api.listMesParties).toHaveBeenLastCalledWith(
      expect.objectContaining({ entrainement: undefined })
    );

    await userEvent.click(screen.getByLabelText(/Masquer l'entraînement/));

    await waitFor(() =>
      expect(api.listMesParties).toHaveBeenLastCalledWith(
        expect.objectContaining({ entrainement: false })
      )
    );
  });

  it("pagine l'historique et dit où on en est", async () => {
    api.listMesParties.mockResolvedValue(
      makeHistorique([makePartie(), makePartie({ game_id: "g-2" })], 45)
    );
    render(<MesPartiesView />);

    await waitFor(() => expect(screen.getByTestId("page")).toHaveTextContent("Page 1 sur 3"));
    expect(screen.getByTestId("total")).toHaveTextContent("45");

    await userEvent.click(screen.getByRole("button", { name: "Plus anciennes" }));

    await waitFor(() =>
      expect(api.listMesParties).toHaveBeenLastCalledWith(
        expect.objectContaining({ offset: 20, limite: 20 })
      )
    );
  });

  it("dit qu'un chargement a échoué au lieu d'annoncer « aucune partie »", async () => {
    api.listMesParties.mockRejectedValue(new Error("réseau"));
    render(<MesPartiesView />);

    await waitFor(() => expect(screen.getByText("Chargement impossible.")).toBeInTheDocument());
    expect(screen.queryByTestId("partie")).not.toBeInTheDocument();
  });

  it("rend une page inexistante à un compte sans accès au jeu (D11)", async () => {
    profile.getProfile.mockResolvedValue(makeProfile(false));
    render(<MesPartiesView />);

    await waitFor(() => expect(notFound).toHaveBeenCalled());
  });
});
