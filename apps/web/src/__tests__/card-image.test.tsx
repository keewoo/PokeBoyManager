import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CardImage } from "@/components/card-image";

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

  it("garde la même classe sur l'image et sur le repli, pour que la mise en page ne bouge pas", () => {
    const { rerender } = render(
      <CardImage src="/api/cards/abc/image" alt="Dracaufeu" className="aspect-[63/88] w-full" />
    );
    expect(screen.getByRole("img", { name: "Dracaufeu" })).toHaveClass("aspect-[63/88]", "w-full");

    rerender(<CardImage src={null} alt="Dracaufeu" className="aspect-[63/88] w-full" />);
    expect(screen.getByRole("img", { name: /Dracaufeu — / })).toHaveClass("aspect-[63/88]", "w-full");
  });
});
