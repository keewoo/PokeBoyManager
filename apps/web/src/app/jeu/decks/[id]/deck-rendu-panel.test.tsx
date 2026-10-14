import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DeckRenduPanel } from "@/app/jeu/decks/[id]/deck-rendu-panel";
import * as renduApi from "@/lib/api/rendu";
import type { ApercuDeckRendu } from "@/lib/api/rendu";

// Lot `j-rendu-carte`, mission point 2 : le repli sur l'image officielle est **dit au joueur dans
// le constructeur de deck**. Un repli muet ferait croire que ses photos n'ont pas été prises en
// compte, alors qu'elles l'ont été et jugées illisibles à la taille d'un plateau.
vi.mock("@/lib/api/rendu", async (orig) => ({
  ...(await orig<typeof renduApi>()),
  getDeckRendu: vi.fn(),
}));

const api = vi.mocked(renduApi);

function makeApercu(partial: Partial<ApercuDeckRendu> = {}): ApercuDeckRendu {
  return {
    rendu_effectif: "photo",
    rendu_deck: null,
    nb_photos: 18,
    nb_officielles: 2,
    cartes: [
      { card_id: "c1", nom: "Carapuce", origine: "officielle", raison: "photo trop sombre" },
      { card_id: "c2", nom: "Salamèche", origine: "officielle", raison: "aucune photo de cette carte" },
    ],
    ...partial,
  };
}

describe("DeckRenduPanel — ce que ce deck montrera en jeu", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getDeckRendu.mockResolvedValue(makeApercu());
  });

  it("nomme chaque carte qui se repliera, avec sa raison", async () => {
    render(<DeckRenduPanel deckId="d1" renduDeck={null} onChangerRendu={() => {}} />);
    await waitFor(() => expect(screen.getByTestId("deck-rendu-replis")).toBeInTheDocument());
    expect(screen.getByText("Carapuce")).toBeInTheDocument();
    expect(screen.getByText("photo trop sombre")).toBeInTheDocument();
    expect(screen.getByText("Salamèche")).toBeInTheDocument();
    expect(screen.getByText("aucune photo de cette carte")).toBeInTheDocument();
  });

  it("donne le compte complet (combien avec ma photo, combien en officielle)", async () => {
    render(<DeckRenduPanel deckId="d1" renduDeck={null} onChangerRendu={() => {}} />);
    await waitFor(() => expect(screen.getByText(/18 avec ta photo/)).toBeInTheDocument());
    expect(screen.getByText(/2 en image officielle/)).toBeInTheDocument();
  });

  it("ne liste aucun repli quand le deck joue déjà en images officielles", async () => {
    api.getDeckRendu.mockResolvedValue(
      makeApercu({ rendu_effectif: "officielle", rendu_deck: "officielle", cartes: [] })
    );
    render(<DeckRenduPanel deckId="d1" renduDeck="officielle" onChangerRendu={() => {}} />);
    await waitFor(() =>
      expect(screen.getByText(/se joue avec les images officielles/i)).toBeInTheDocument()
    );
    expect(screen.queryByTestId("deck-rendu-replis")).toBeNull();
  });

  it("laisse choisir le rendu du deck, chaîne vide = suivre le réglage du compte", async () => {
    const onChangerRendu = vi.fn();
    render(<DeckRenduPanel deckId="d1" renduDeck="photo" onChangerRendu={onChangerRendu} />);
    const choix = await screen.findByTestId("deck-rendu-choix");
    await userEvent.selectOptions(choix, "");
    expect(onChangerRendu).toHaveBeenCalledWith("");
  });

  it("dit qu'un aperçu n'a pas pu être chargé — jamais « tout va bien » par défaut", async () => {
    api.getDeckRendu.mockRejectedValue(new Error("coupure"));
    render(<DeckRenduPanel deckId="d1" renduDeck={null} onChangerRendu={() => {}} />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.queryByText(/avec ta photo/)).toBeNull();
  });
});
