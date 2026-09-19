import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LegalFooter } from "@/components/legal-footer";

describe("LegalFooter", () => {
  it("relie les trois pages légales", () => {
    render(<LegalFooter />);
    expect(screen.getByRole("link", { name: "Mentions légales" })).toHaveAttribute(
      "href",
      "/mentions-legales"
    );
    expect(screen.getByRole("link", { name: "Confidentialité" })).toHaveAttribute(
      "href",
      "/confidentialite"
    );
    expect(screen.getByRole("link", { name: "Conditions générales" })).toHaveAttribute(
      "href",
      "/conditions"
    );
  });

  it("précise que le site n'est pas affilié à Nintendo, Creatures, GAME FREAK ni The Pokémon Company", () => {
    render(<LegalFooter />);
    expect(
      screen.getByText(/n'est pas affilié à Nintendo, Creatures, GAME FREAK ni à The Pokémon Company/)
    ).toBeInTheDocument();
  });
});
