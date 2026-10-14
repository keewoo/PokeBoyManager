import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BoardCard, CardBack } from "./board-card";
import type { VueCarte } from "@/lib/game/plateau";

/**
 * Lot `j-rendu-carte` — les **trois rendus** d'une carte sur le plateau, et le fait que l'écran
 * n'en choisit aucun : il affiche ce que le serveur a décidé (DJ5).
 *
 * Ces tests échouent sans le changement du lot : avant lui, `BoardCard` n'affichait aucune image
 * (`<img>` absent), seulement la `ref` en texte.
 */

const PHOTO: VueCarte = {
  instance_id: "i1",
  ref: "base1-25-pikachu",
  rendu: {
    origine: "photo",
    url: "/jeu/rendu/parties/g1/photos/item1",
    url_zoom: "/jeu/rendu/parties/g1/photos/item1",
    credit: "photo de Aymeric",
    url_repli: "/img/cards/c1?size=low",
  },
};

const OFFICIELLE: VueCarte = {
  instance_id: "i2",
  ref: "base1-4-charizard",
  rendu: {
    origine: "officielle",
    url: "/img/cards/c2?size=low",
    url_zoom: "/img/cards/c2?size=high",
    raison: "photo trop sombre",
  },
};

const SANS_IMAGE: VueCarte = { instance_id: "i3", ref: "inconnue-du-catalogue" };

describe("BoardCard — la photo du propriétaire", () => {
  it("affiche la photo servie par le serveur, avec son origine", () => {
    render(<BoardCard carte={PHOTO} />);
    const image = screen.getByTestId("image-carte");
    expect(image).toHaveAttribute("src", "/jeu/rendu/parties/g1/photos/item1");
    expect(image).toHaveAttribute("data-origine", "photo");
  });

  it("annonce le crédit « photo de … » sur le plateau, sans écrire par-dessus les indicateurs", () => {
    render(<BoardCard carte={PHOTO} etiquette="Actif" onPeek={() => {}} />);
    // Sur le plateau, le crédit est porté par l'aria-label (60 px de large : pas de place pour
    // un bandeau de texte, et les énergies occupent le bas de la carte).
    expect(screen.getByRole("button", { name: /photo de Aymeric/i })).toBeInTheDocument();
    expect(screen.queryByTestId("credit-photo")).toBeNull();
  });

  it("écrit le crédit au zoom, là où il y a la place de le lire", () => {
    render(<BoardCard carte={PHOTO} taille="zoom" />);
    expect(screen.getByTestId("credit-photo")).toHaveTextContent("photo de Aymeric");
  });

  it("replie sur l'image officielle si la photo ne se charge pas — jamais de trou", () => {
    render(<BoardCard carte={PHOTO} />);
    fireEvent.error(screen.getByTestId("image-carte"));
    const image = screen.getByTestId("image-carte");
    expect(image).toHaveAttribute("src", "/img/cards/c1?size=low");
    expect(image).toHaveAttribute("data-origine", "officielle");
    // Le crédit disparaît avec la photo : créditer quelqu'un pour l'image du catalogue serait faux.
    expect(screen.queryByTestId("credit-photo")).toBeNull();
  });

  it("si le repli échoue aussi, le nom de la carte redevient visible", () => {
    render(<BoardCard carte={PHOTO} />);
    fireEvent.error(screen.getByTestId("image-carte"));
    fireEvent.error(screen.getByTestId("image-carte"));
    expect(screen.queryByTestId("image-carte")).toBeNull();
    const nom = screen.getByText("base1-25-pikachu");
    expect(nom.className).not.toContain("sr-only");
  });
});

describe("BoardCard — l'image officielle", () => {
  it("affiche l'image officielle quand c'est elle que le serveur a décidée", () => {
    render(<BoardCard carte={OFFICIELLE} />);
    const image = screen.getByTestId("image-carte");
    expect(image).toHaveAttribute("src", "/img/cards/c2?size=low");
    expect(image).toHaveAttribute("data-origine", "officielle");
  });

  it("prend la taille zoom au zoom (lisible sans pincer l'écran)", () => {
    render(<BoardCard carte={OFFICIELLE} taille="zoom" />);
    expect(screen.getByTestId("image-carte")).toHaveAttribute("src", "/img/cards/c2?size=high");
  });

  it("ne montre pas la raison du repli sur le plateau (c'est le constructeur de deck qui la dit)", () => {
    render(<BoardCard carte={OFFICIELLE} />);
    expect(screen.queryByText(/trop sombre/i)).toBeNull();
  });
});

describe("BoardCard — aucune image", () => {
  it("garde le nom lisible quand la carte n'a aucun rendu (ref inconnue du catalogue, D9)", () => {
    render(<BoardCard carte={SANS_IMAGE} />);
    expect(screen.queryByTestId("image-carte")).toBeNull();
    expect(screen.getByText("inconnue-du-catalogue").className).not.toContain("sr-only");
  });

  it("n'invente aucune URL d'image à partir de la ref", () => {
    const { container } = render(<BoardCard carte={SANS_IMAGE} />);
    expect(container.querySelectorAll("img")).toHaveLength(0);
  });
});

describe("CardBack — le dos de carte", () => {
  it("se dessine sans rien charger (aucune image, aucune requête)", () => {
    const { container } = render(<CardBack />);
    expect(container.querySelectorAll("img")).toHaveLength(0);
    expect(screen.getByTestId("dos-carte")).toBeInTheDocument();
  });

  it("se nomme pour les lecteurs d'écran", () => {
    render(<CardBack etiquette="carte cachée" />);
    expect(screen.getByRole("img", { name: "carte cachée" })).toBeInTheDocument();
  });

  it("garde le format d'une carte (63/88) pour qu'un retournement ne déplace rien", () => {
    render(<CardBack />);
    expect(screen.getByTestId("dos-carte").className).toContain("aspect-[63/88]");
  });
});
