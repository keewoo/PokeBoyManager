import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CardTile } from "@/components/card-tile";

describe("CardTile", () => {
  it("affiche le nom, l'extension, le prix et la variation", () => {
    render(
      <CardTile
        href="/carte/abc123"
        name="Dracaufeu"
        setName="Écarlate et Violet"
        number="006/198"
        price="42,50 €"
        delta={8.1}
        rarity="rare-holo"
        condition="near-mint"
      />
    );
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/carte/abc123");
    expect(screen.getByText("Dracaufeu")).toBeInTheDocument();
    expect(screen.getByText("Écarlate et Violet · 006/198")).toBeInTheDocument();
    expect(screen.getByText("42,50 €")).toBeInTheDocument();
    expect(screen.getByText("+8,1 %")).toBeInTheDocument();
    expect(screen.getByText("Rare holo")).toBeInTheDocument();
    expect(screen.getByText("Near Mint")).toBeInTheDocument();
  });

  it("affiche un espace réservé quand aucune image n'est disponible", () => {
    render(
      <CardTile
        href="/carte/xyz"
        name="Bulbizarre"
        setName="Base"
        number="044/102"
        price="1,20 €"
        rarity="commune"
        condition="bon"
      />
    );
    expect(screen.getByText("Image à venir")).toBeInTheDocument();
  });
});
