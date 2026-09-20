import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LandingPage } from "@/components/landing/landing-page";
import type { FeaturedCard } from "@/lib/api/featured-cards";

const SAMPLE_CARDS: FeaturedCard[] = [
  { id: "11111111-1111-1111-1111-111111111111", name: "Dracaufeu-EX", number: "6", set_name: "Écarlate et Violet" },
  { id: "22222222-2222-2222-2222-222222222222", name: "Pikachu VMAX", number: "44", set_name: "Voltage Éclatant" },
];

describe("LandingPage (accueil visiteur)", () => {
  it("affiche l'accroche et mène à l'inscription et à la connexion", () => {
    render(<LandingPage featuredCards={[]} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "On retrouve chaque carte"
    );
    expect(screen.getByRole("link", { name: "Créer mon espace" })).toHaveAttribute(
      "href",
      "/inscription"
    );
    expect(screen.getByRole("link", { name: "J'ai déjà un compte" })).toHaveAttribute(
      "href",
      "/connexion"
    );
  });

  it("présente les quatre étapes photo → reconnaissance → valeur → histoire", () => {
    render(<LandingPage featuredCards={[]} />);
    expect(screen.getByText("Une carte ou tout un classeur")).toBeInTheDocument();
    expect(screen.getByText("Tu vérifies, tu valides")).toBeInTheDocument();
    expect(screen.getByText("Ta collection, cotée chaque jour")).toBeInTheDocument();
    expect(screen.getByText("Chaque carte raconte quelque chose")).toBeInTheDocument();
  });

  it("précise qu'on peut apporter sa propre IA", () => {
    render(<LandingPage featuredCards={[]} />);
    expect(screen.getByText("Apporte ta propre IA")).toBeInTheDocument();
    expect(screen.getByText("Claude · Anthropic")).toBeInTheDocument();
    expect(screen.getByText("Gemini · Google")).toBeInTheDocument();
    expect(screen.getByText("ChatGPT · OpenAI")).toBeInTheDocument();
  });

  it("affiche le pied de page légal", () => {
    render(<LandingPage featuredCards={[]} />);
    expect(screen.getByRole("link", { name: "Mentions légales" })).toBeInTheDocument();
  });

  it("affiche l'illustration d'accueil avec un texte alternatif descriptif, à la place du bloc de démonstration vide", () => {
    render(<LandingPage featuredCards={[]} />);

    const hero = screen.getByAltText(/dresseur photographie son classeur/i);
    expect(hero).toBeInTheDocument();
    expect(hero.tagName).toBe("IMG");
    // L'ancien `ScanDemo` (neuf rectangles vides) est retiré, pas seulement caché.
    expect(screen.queryByLabelText(/exemple : une photo de neuf cartes/i)).not.toBeInTheDocument();
  });

  it("affiche de vraies cartes du catalogue quand elles sont fournies", () => {
    render(<LandingPage featuredCards={SAMPLE_CARDS} />);

    expect(screen.getByAltText(/Dracaufeu-EX · Écarlate et Violet n°6/)).toBeInTheDocument();
    expect(screen.getByAltText(/Pikachu VMAX · Voltage Éclatant n°44/)).toBeInTheDocument();
  });

  it("n'affiche pas la section « Dans le catalogue » sans carte", () => {
    render(<LandingPage featuredCards={[]} />);

    expect(screen.queryByText("Dans le catalogue")).not.toBeInTheDocument();
  });
});
