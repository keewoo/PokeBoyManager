import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { JournalPanel } from "./journal-panel";
import type { LigneJournal } from "@/lib/game/journal";

function ligne(over: Partial<LigneJournal> = {}): LigneJournal {
  return {
    cle: "0-0",
    numero: 0,
    type: "cartes_piochees",
    texte: "Tu pioches 2 cartes.",
    traduit: true,
    categorie: "moi",
    refs: [],
    surligne: null,
    detailDegats: null,
    ...over,
  };
}

/** Le tiroir est replié par défaut (plateau plein écran) : on l'ouvre pour voir le fil. */
function ouvrir() {
  fireEvent.click(screen.getByRole("button", { name: /Journal/ }));
}

describe("JournalPanel", () => {
  it("est un tiroir replié par défaut, qui s'ouvre et se replie", () => {
    render(<JournalPanel lignes={[ligne()]} />);
    // Replié : le corps n'est pas rendu.
    expect(screen.queryByTestId("journal-liste")).toBeNull();
    ouvrir();
    expect(screen.getByTestId("journal-liste")).toBeInTheDocument();
    ouvrir();
    expect(screen.queryByTestId("journal-liste")).toBeNull();
  });

  it("affiche chaque ligne en français, la plus récente en tête et mise en évidence", () => {
    render(
      <JournalPanel
        lignes={[
          ligne({ cle: "0-0", numero: 0, texte: "Tu pioches 2 cartes." }),
          ligne({ cle: "1-0", numero: 1, categorie: "adversaire", texte: "L'adversaire pioche 1 carte." }),
        ]}
      />,
    );
    ouvrir();
    const items = screen.getAllByTestId("ligne-journal");
    // Ordre anti-chronologique : la plus récente (#1) en tête.
    expect(items[0]).toHaveTextContent("L'adversaire pioche 1 carte.");
    expect(items[0]).toHaveAttribute("data-derniere", "");
    expect(items[1]).not.toHaveAttribute("data-derniere");
  });

  it("filtre par catégorie (mes coups / adversaire / effets auto)", () => {
    render(
      <JournalPanel
        lignes={[
          ligne({ cle: "0-0", categorie: "moi", texte: "Tu pioches 2 cartes." }),
          ligne({ cle: "1-0", categorie: "adversaire", texte: "L'adversaire pioche." }),
          ligne({ cle: "2-0", categorie: "auto", type: "etat_checkup", texte: "Poison sur ton Actif : 10 dégâts." }),
        ]}
      />,
    );
    ouvrir();
    expect(screen.getAllByTestId("ligne-journal")).toHaveLength(3);
    // On masque l'adversaire : sa ligne disparaît, les autres restent.
    fireEvent.click(screen.getByTestId("filtre-adversaire"));
    expect(screen.getAllByTestId("ligne-journal")).toHaveLength(2);
    expect(screen.queryByText("L'adversaire pioche.")).toBeNull();
    expect(screen.getByText("Poison sur ton Actif : 10 dégâts.")).toBeInTheDocument();
  });

  it("rend le détail du calcul des dégâts consultable à la demande", () => {
    render(
      <JournalPanel
        lignes={[
          ligne({
            cle: "0-1",
            type: "degats",
            texte: "Dégâts : 120 (12 compteurs).",
            detailDegats: "60 base, ×2 faiblesse = 120",
          }),
        ]}
      />,
    );
    ouvrir();
    // Le détail n'est pas affiché tant qu'on ne le demande pas.
    expect(screen.queryByTestId("detail-degats")).toBeNull();
    fireEvent.click(screen.getByTestId("detail-degats-bouton"));
    expect(screen.getByTestId("detail-degats")).toHaveTextContent("60 base, ×2 faiblesse = 120");
  });

  it("remonte l'instance à surligner au survol (reliure journal ↔ plateau)", () => {
    const onSurvol = vi.fn();
    render(
      <JournalPanel
        lignes={[ligne({ cle: "0-0", type: "ko", texte: "l'Actif adverse est mis K.O.", surligne: "p-9" })]}
        onSurvol={onSurvol}
      />,
    );
    ouvrir();
    const item = screen.getByTestId("ligne-journal");
    fireEvent.mouseEnter(item);
    expect(onSurvol).toHaveBeenCalledWith("p-9");
    fireEvent.mouseLeave(item);
    expect(onSurvol).toHaveBeenCalledWith(null);
  });

  it("montre toujours une ligne non traduite, même quand les filtres sont actifs (un bug se voit)", () => {
    render(
      <JournalPanel
        lignes={[ligne({ cle: "0-0", traduit: false, texte: "Événement non traduit : effet_mysterieux" })]}
      />,
    );
    ouvrir();
    // Même en coupant tous les filtres, la ligne non traduite reste visible.
    fireEvent.click(screen.getByTestId("filtre-moi"));
    fireEvent.click(screen.getByTestId("filtre-adversaire"));
    fireEvent.click(screen.getByTestId("filtre-auto"));
    const item = screen.getByTestId("ligne-journal");
    expect(item).toHaveAttribute("data-traduit", "non");
    expect(within(item).getByText(/non traduit/)).toBeInTheDocument();
  });
});
