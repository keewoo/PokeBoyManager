import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CardImage } from "@/components/card-image";

const replacement = {
  cardId: "carte-1",
  name: "Hyporoi-ex",
  elementType: "water",
  hp: 210,
  supertype: "Pokémon",
  setName: "Méga-Ascension",
  cardNumber: "042",
  rarity: "Rare",
};

// Une carte du catalogue sans image officielle laissait l'icône d'image cassée du navigateur,
// avec le texte alternatif en travers de la vignette — constaté en production deux fois, sur le
// tableau de bord puis sur l'écran de validation. Ces trois cas sont la garde.
describe("CardImage", () => {
  it("sans source connue, affiche le repli plutôt qu'une image vide", () => {
    render(<CardImage src={null} alt="Hyporoi-ex" />);

    expect(screen.queryByRole("img", { name: "Hyporoi-ex" })).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Hyporoi-ex — Aucune image disponible/ })).toBeInTheDocument();
  });

  it("quand le proxy répond 404, bascule sur le repli", () => {
    render(<CardImage src="/api/cards/abc/image" alt="Hyporoi-ex" label="Pas d'image" />);

    const image = screen.getByRole("img", { name: "Hyporoi-ex" });
    fireEvent.error(image);

    expect(screen.queryByRole("img", { name: "Hyporoi-ex" })).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Hyporoi-ex — Pas d'image/ })).toBeInTheDocument();
  });

  it("sans source mais AVEC des données de carte, compose la carte plutôt qu'un cadre vide", () => {
    render(<CardImage src={null} alt="Hyporoi-ex" replacement={replacement} />);

    expect(screen.getByRole("img", { name: /Hyporoi-ex — visuel non disponible/ })).toBeInTheDocument();
    expect(screen.getByText("210 PV")).toBeInTheDocument();
    expect(screen.getByText("Visuel non disponible")).toBeInTheDocument();
  });

  it("quand le proxy échoue, bascule sur la carte composée ET journalise l'incident", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    render(<CardImage src="/api/cards/abc/image" alt="Hyporoi-ex" replacement={replacement} />);

    fireEvent.error(screen.getByRole("img", { name: "Hyporoi-ex" }));

    expect(screen.getByRole("img", { name: /Hyporoi-ex — visuel non disponible/ })).toBeInTheDocument();
    // « ne pas masquer l'incident » : un repli là où une image officielle existe est une panne.
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("/api/cards/abc/image"));
    warn.mockRestore();
  });

  it("garde la même classe sur l'image et sur le repli, pour que la mise en page ne bouge pas", () => {
    const { rerender } = render(
      <CardImage src="/api/cards/abc/image" alt="Dracaufeu" className="aspect-[63/88] w-full" />
    );
    expect(screen.getByRole("img", { name: "Dracaufeu" })).toHaveClass("aspect-[63/88]", "w-full");

    rerender(<CardImage src={null} alt="Dracaufeu" className="aspect-[63/88] w-full" />);
    expect(screen.getByRole("img", { name: /Dracaufeu — / })).toHaveClass("aspect-[63/88]", "w-full");
  });
});
