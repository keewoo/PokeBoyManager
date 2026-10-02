import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatutConnexion } from "@/components/game/connection-status";

describe("StatutConnexion", () => {
  it("n'affiche rien quand la connexion est directe", () => {
    const { container } = render(<StatutConnexion etat="direct" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("annonce une connexion dégradée et rassure sur la continuité", () => {
    render(<StatutConnexion etat="degrade" />);
    const statut = screen.getByRole("status");
    expect(statut).toHaveTextContent(/connexion dégradée/i);
    expect(statut).toHaveTextContent(/continue/i); // la partie n'est pas interrompue
    expect(statut).toHaveAttribute("data-etat", "degrade");
    expect(statut).toHaveAttribute("aria-live", "polite");
  });

  it("montre l'état de connexion initial", () => {
    render(<StatutConnexion etat="connexion" />);
    expect(screen.getByRole("status")).toHaveTextContent(/connexion à la partie/i);
  });
});
