import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MentionsLegalesPage from "@/app/mentions-legales/page";
import ConfidentialitePage from "@/app/confidentialite/page";
import ConditionsPage from "@/app/conditions/page";

describe("Pages légales (brouillons)", () => {
  it("Mentions légales : titre et mention de brouillon", () => {
    render(<MentionsLegalesPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Mentions légales" })).toBeInTheDocument();
    expect(screen.getByText(/Brouillon/)).toBeInTheDocument();
  });

  it("Confidentialité : titre et mention de brouillon", () => {
    render(<ConfidentialitePage />);
    expect(
      screen.getByRole("heading", { level: 1, name: "Politique de confidentialité" })
    ).toBeInTheDocument();
    expect(screen.getByText(/Brouillon/)).toBeInTheDocument();
  });

  it("Conditions générales : titre et mention de brouillon", () => {
    render(<ConditionsPage />);
    expect(
      screen.getByRole("heading", { level: 1, name: "Conditions générales d'utilisation" })
    ).toBeInTheDocument();
    expect(screen.getByText(/Brouillon/)).toBeInTheDocument();
  });
});
