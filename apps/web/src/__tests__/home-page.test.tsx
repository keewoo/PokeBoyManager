import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HomePage from "@/app/page";

describe("HomePage (visiteur)", () => {
  it("affiche l'accroche et mène à l'inscription et à la connexion", () => {
    render(<HomePage />);
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

  it("présente les trois étapes photo → reconnaissance → valeur", () => {
    render(<HomePage />);
    expect(screen.getByText("Une carte ou tout un classeur")).toBeInTheDocument();
    expect(screen.getByText("Tu vérifies, tu valides")).toBeInTheDocument();
    expect(screen.getByText("Ta collection, cotée chaque jour")).toBeInTheDocument();
  });

  it("précise qu'on peut apporter sa propre IA", () => {
    render(<HomePage />);
    expect(screen.getByText("Apporte ta propre IA")).toBeInTheDocument();
    expect(screen.getByText("Claude · Anthropic")).toBeInTheDocument();
    expect(screen.getByText("Gemini · Google")).toBeInTheDocument();
    expect(screen.getByText("ChatGPT · OpenAI")).toBeInTheDocument();
  });

  it("affiche le pied de page légal", () => {
    render(<HomePage />);
    expect(screen.getByRole("link", { name: "Mentions légales" })).toBeInTheDocument();
  });
});
