import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import * as gamesApi from "@/lib/api/games";
import type { Recapitulatif } from "@/lib/api/games";
import { FinPartie } from "./fin-partie";

/**
 * L'écran de fin de partie (lot `j-partie-fin-ui`).
 *
 * Ce qu'on vérifie ici, et pourquoi : l'écran **n'invente aucun chiffre** (ils viennent tous du
 * récapitulatif serveur), il annonce l'issue du point de vue du joueur connecté, il traite les
 * fins anormales comme les autres, la revanche navigue vers la nouvelle partie, et un refus du
 * serveur est **affiché** et non avalé. Le dernier point est le plus important pour ce dépôt : un
 * `catch` muet sur la revanche laisserait un bouton qui ne fait rien, sans un mot.
 */

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

vi.mock("@/lib/api/games", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/api/games")>();
  return { ...mod, getRecapitulatif: vi.fn(), listGames: vi.fn(), revancheGame: vi.fn() };
});

const games = vi.mocked(gamesApi);

function recap(over: Partial<Recapitulatif> = {}): Recapitulatif {
  return {
    game_id: "g1",
    statut: "terminee",
    raison_fin: "derniere_recompense",
    vainqueur_user_id: "moi",
    entrainement: false,
    coups: 42,
    tours: 7,
    debut: "2026-10-14T10:00:00+00:00",
    fin: "2026-10-14T10:07:12+00:00",
    duree_s: 432,
    joueurs: [
      {
        seat: 0,
        user_id: "moi",
        pseudo: "Sacha",
        degats_infliges: 180,
        kos_infliges: 3,
        recompenses_prises: 6,
        cartes_jouees: 9,
        energies_attachees: 5,
        coups_joues: 21,
      },
      {
        seat: 1,
        user_id: "lui",
        pseudo: "Régis",
        degats_infliges: 60,
        kos_infliges: 1,
        recompenses_prises: 2,
        cartes_jouees: 4,
        energies_attachees: 3,
        coups_joues: 21,
      },
    ],
    meilleur_coup: { numero: 31, user_id: "moi", degats: 120, ko: true },
    ...over,
  };
}

beforeEach(() => {
  push.mockReset();
  games.getRecapitulatif.mockReset();
  games.listGames.mockReset();
  games.revancheGame.mockReset();
  games.listGames.mockResolvedValue([]);
});

describe("annonce du résultat", () => {
  it("annonce la victoire et la raison, du point de vue du joueur connecté", async () => {
    games.getRecapitulatif.mockResolvedValue(recap());
    render(<FinPartie gameId="g1" moiUserId="moi" raisonFinVue="derniere_recompense" />);

    expect(await screen.findByTestId("fin-partie-titre")).toHaveTextContent("Gagné");
    expect(screen.getByTestId("fin-partie-raison")).toHaveTextContent(
      "Tu as pris ta dernière carte récompense.",
    );
    expect(screen.getByTestId("fin-partie-raison-courte")).toHaveTextContent(
      "dernière récompense prise",
    );
  });

  it("annonce la défaite sans la commenter, et avec le fait vu de l'autre côté", async () => {
    games.getRecapitulatif.mockResolvedValue(recap({ vainqueur_user_id: "lui" }));
    render(<FinPartie gameId="g1" moiUserId="moi" raisonFinVue="derniere_recompense" />);

    expect(await screen.findByTestId("fin-partie-titre")).toHaveTextContent("C'est passé près");
    expect(screen.getByTestId("fin-partie-raison")).toHaveTextContent(
      "Ton adversaire a pris sa dernière carte récompense.",
    );
  });

  it.each([
    ["abandon", "Ton adversaire a préféré arrêter la partie."],
    ["temps_ecoule", "Le temps de ton adversaire s'est écoulé."],
    ["desertion", "Ton adversaire n'est pas revenu dans la partie."],
  ])("traite la fin anormale « %s » avec le même soin", async (raison, phrase) => {
    // Critère 4 de la mission : abandon, désertion et temps ne sont pas des cas dégradés.
    games.getRecapitulatif.mockResolvedValue(recap({ raison_fin: raison }));
    render(<FinPartie gameId="g1" moiUserId="moi" raisonFinVue={raison} />);
    expect(await screen.findByTestId("fin-partie-raison")).toHaveTextContent(phrase);
  });

  it("annonce une partie nulle sans vainqueur", async () => {
    games.getRecapitulatif.mockResolvedValue(
      recap({ vainqueur_user_id: null, raison_fin: "egalite" }),
    );
    render(<FinPartie gameId="g1" moiUserId="moi" raisonFinVue="egalite" />);
    expect(await screen.findByTestId("fin-partie-titre")).toHaveTextContent("Match nul");
    expect(screen.getByTestId("fin-partie-raison-courte")).toHaveTextContent("égalité");
  });
});

describe("récapitulatif", () => {
  it("affiche les chiffres du serveur, sans en recalculer aucun", async () => {
    games.getRecapitulatif.mockResolvedValue(recap());
    render(<FinPartie gameId="g1" moiUserId="moi" raisonFinVue="derniere_recompense" />);

    expect(await screen.findByTestId("fin-partie-global")).toHaveTextContent("7 min 12 s");
    expect(screen.getByTestId("fin-partie-global")).toHaveTextContent("7 tours");
    expect(screen.getByTestId("fin-partie-global")).toHaveTextContent("42 coups");

    // Une ligne du tableau : l'en-tête de ligne, puis une cellule par joueur.
    const ligne = screen.getByRole("rowheader", { name: "Dégâts infligés" }).closest("tr");
    expect(ligne).not.toBeNull();
    expect(ligne!.textContent).toContain("180");
    expect(ligne!.textContent).toContain("60");

    // Le joueur connecté est nommé « Toi », l'autre par son pseudo.
    expect(screen.getByRole("columnheader", { name: "Toi" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Régis" })).toBeInTheDocument();
  });

  it("raconte le meilleur coup, et dit s'il a mis K.O.", async () => {
    games.getRecapitulatif.mockResolvedValue(recap());
    render(<FinPartie gameId="g1" moiUserId="moi" raisonFinVue="derniere_recompense" />);
    const texte = (await screen.findByTestId("fin-partie-meilleur-coup")).textContent ?? "";
    expect(texte).toContain("120 dégâts");
    expect(texte).toContain("31");
    expect(texte).toContain("K.O.");
  });

  it("dit « inconnue » quand la durée ne se calcule pas", async () => {
    games.getRecapitulatif.mockResolvedValue(recap({ duree_s: null }));
    render(<FinPartie gameId="g1" moiUserId="moi" raisonFinVue="abandon" />);
    expect(await screen.findByTestId("fin-partie-global")).toHaveTextContent("inconnue");
  });

  it("n'affiche aucun chiffre quand le récapitulatif échoue, et le dit", async () => {
    // Pas de repli silencieux : la fin est annoncée et la raison nommée (le plateau la connaît),
    // mais on n'invente pas de statistiques.
    games.getRecapitulatif.mockRejectedValue(new ApiError(500, "boum"));
    render(<FinPartie gameId="g1" moiUserId="moi" raisonFinVue="abandon" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("résumé");
    expect(screen.queryByTestId("fin-partie-recap")).not.toBeInTheDocument();
    expect(screen.getByTestId("fin-partie-raison-courte")).toHaveTextContent("abandon");
  });

  it("n'annonce pas un match nul quand le vainqueur n'est pas connu", async () => {
    // Le piège, et il est sournois : le vainqueur ne vient que du récapitulatif, et « pas de
    // vainqueur » veut dire « partie nulle ». Si l'absence de réponse se repliait sur cette
    // valeur, une panne réseau annoncerait un match nul à deux joueurs dont l'un a gagné — un
    // faux résultat, dit avec aplomb, que personne ne pourrait soupçonner.
    games.getRecapitulatif.mockRejectedValue(new ApiError(500, "boum"));
    render(<FinPartie gameId="g1" moiUserId="moi" raisonFinVue="derniere_recompense" />);

    expect(await screen.findByTestId("fin-partie-titre")).toHaveTextContent("Partie terminée");
    expect(screen.getByTestId("fin-partie-titre")).not.toHaveTextContent("Match nul");
    expect(screen.getByTestId("fin-partie-raison")).toHaveTextContent("n'a pas pu être chargé");
  });
});

describe("effet sur le compte", () => {
  it("montre la série de victoires en cours", async () => {
    games.getRecapitulatif.mockResolvedValue(recap());
    games.listGames.mockResolvedValue([
      {
        id: "g1",
        status: "terminee",
        current_numero: 42,
        vainqueur_user_id: "moi",
        raison_fin: "derniere_recompense",
        created_at: "2026-10-14T10:00:00+00:00",
        updated_at: "2026-10-14T10:07:12+00:00",
        entrainement: false,
      },
    ]);
    render(<FinPartie gameId="g1" moiUserId="moi" raisonFinVue="derniere_recompense" />);
    expect(await screen.findByTestId("fin-partie-serie")).toHaveTextContent("1 victoire");
  });

  it("dit qu'une partie d'entraînement ne compte pas, et ne montre pas de statistiques", async () => {
    games.getRecapitulatif.mockResolvedValue(recap({ entrainement: true }));
    render(<FinPartie gameId="g1" moiUserId="moi" raisonFinVue="derniere_recompense" />);
    expect(await screen.findByTestId("fin-partie-entrainement")).toHaveTextContent(
      "ne compte pas",
    );
    expect(screen.queryByTestId("fin-partie-compte")).not.toBeInTheDocument();
  });
});

describe("revanche et sorties", () => {
  it("relance la partie et navigue vers la nouvelle", async () => {
    games.getRecapitulatif.mockResolvedValue(recap());
    games.revancheGame.mockResolvedValue({ game_id: "g2", deja_creee: false });
    render(<FinPartie gameId="g1" moiUserId="moi" raisonFinVue="derniere_recompense" />);

    await userEvent.click(await screen.findByTestId("fin-partie-revanche"));
    await waitFor(() => expect(games.revancheGame).toHaveBeenCalledWith("g1"));
    expect(push).toHaveBeenCalledWith("/jeu/parties/g2");
  });

  it("suit la partie que l'adversaire a déjà créée (les deux ont cliqué)", async () => {
    games.getRecapitulatif.mockResolvedValue(recap());
    games.revancheGame.mockResolvedValue({ game_id: "g9", deja_creee: true });
    render(<FinPartie gameId="g1" moiUserId="moi" raisonFinVue="derniere_recompense" />);

    await userEvent.click(await screen.findByTestId("fin-partie-revanche"));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/jeu/parties/g9"));
  });

  it("affiche la raison du serveur quand la revanche est refusée", async () => {
    // Un bouton qui ne fait rien sans un mot, c'est la panne muette que ce dépôt a déjà payée.
    games.getRecapitulatif.mockResolvedValue(recap());
    games.revancheGame.mockRejectedValue(
      new ApiError(409, "Régis est déjà dans une partie en cours."),
    );
    render(<FinPartie gameId="g1" moiUserId="moi" raisonFinVue="derniere_recompense" />);

    await userEvent.click(await screen.findByTestId("fin-partie-revanche"));
    expect(await screen.findByRole("alert")).toHaveTextContent("déjà dans une partie");
    expect(push).not.toHaveBeenCalled();
    // Et le bouton redevient actionnable : le refus n'est pas définitif.
    expect(screen.getByTestId("fin-partie-revanche")).not.toBeDisabled();
  });

  it("propose le replay et le retour au salon", async () => {
    games.getRecapitulatif.mockResolvedValue(recap());
    render(<FinPartie gameId="g1" moiUserId="moi" raisonFinVue="derniere_recompense" />);
    expect(await screen.findByTestId("fin-partie-replay")).toHaveAttribute(
      "href",
      "/jeu/parties/g1/replay",
    );
    expect(screen.getByTestId("fin-partie-salon")).toHaveAttribute("href", "/jeu/salon");
  });

  it("se replie pour laisser voir le plateau, et se rouvre", async () => {
    // L'écran de fin ne doit pas emprisonner le joueur sur le résumé : la partie reste regardable.
    games.getRecapitulatif.mockResolvedValue(recap());
    render(<FinPartie gameId="g1" moiUserId="moi" raisonFinVue="derniere_recompense" />);

    await userEvent.click(await screen.findByTestId("fin-partie-replier"));
    expect(screen.queryByTestId("fin-partie")).not.toBeInTheDocument();

    await userEvent.click(screen.getByTestId("fin-partie-rouvrir"));
    expect(await screen.findByTestId("fin-partie")).toBeInTheDocument();
  });

  it("est posé hors du flux pour ne pas allonger la page du plateau", async () => {
    // La page `/jeu/parties/{id}` ne tolère aucun défilement (e2e `plateau-responsive`) : un
    // panneau en flux normal la rallongerait, et aucun test unitaire ne le verrait. On verrouille
    // donc le positionnement ici, là où il est lisible.
    games.getRecapitulatif.mockResolvedValue(recap());
    render(<FinPartie gameId="g1" moiUserId="moi" raisonFinVue="derniere_recompense" />);
    const dialogue = await screen.findByTestId("fin-partie");
    expect(dialogue.className).toContain("fixed");
    expect(dialogue.className).toContain("overflow-y-auto");
  });
});
