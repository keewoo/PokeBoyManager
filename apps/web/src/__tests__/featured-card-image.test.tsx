import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FeaturedCardImage } from "@/components/landing/featured-card-image";

describe("FeaturedCardImage", () => {
  it("affiche l'image avec son texte alternatif et un chargement paresseux", () => {
    render(<FeaturedCardImage src="/api/img/cards/abc?size=low" alt="Dracaufeu-EX" />);

    const img = screen.getByAltText("Dracaufeu-EX");
    expect(img).toHaveAttribute("loading", "lazy");
    expect(img).toHaveAttribute("src", "/api/img/cards/abc?size=low");
  });

  it("bascule sur une vignette de repli quand l'image échoue à charger", () => {
    render(<FeaturedCardImage src="/api/img/cards/abc?size=low" alt="Dracaufeu-EX" />);

    fireEvent.error(screen.getByAltText("Dracaufeu-EX"));

    expect(screen.queryByAltText("Dracaufeu-EX")).not.toBeInTheDocument();
    expect(screen.getByText("Image à venir")).toBeInTheDocument();
  });
});
