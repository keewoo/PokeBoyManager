import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BoardCard } from "./board-card";
import { CardZoom } from "./card-zoom";
import type { VueCarte } from "@/lib/game/plateau";

const CARTE: VueCarte = { instance_id: "i1", ref: "base1-25-pikachu" };

describe("BoardCard — déclenchement du zoom", () => {
  it("signale la carte au survol, puis null à la sortie (ouvre/ferme le zoom)", () => {
    const onPeek = vi.fn();
    render(<BoardCard carte={CARTE} onPeek={onPeek} />);
    const carte = screen.getByRole("button", { name: /pikachu/i });
    fireEvent.mouseEnter(carte);
    expect(onPeek).toHaveBeenLastCalledWith(CARTE);
    fireEvent.mouseLeave(carte);
    expect(onPeek).toHaveBeenLastCalledWith(null);
  });

  it("signale aussi la carte au focus clavier (accessibilité)", () => {
    const onPeek = vi.fn();
    render(<BoardCard carte={CARTE} onPeek={onPeek} />);
    fireEvent.focus(screen.getByRole("button", { name: /pikachu/i }));
    expect(onPeek).toHaveBeenCalledWith(CARTE);
  });

  it("sans onPeek, la carte n'est pas un bouton et n'ouvre pas de zoom", () => {
    render(<BoardCard carte={CARTE} />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("CardZoom — carte agrandie et lisible", () => {
  it("n'affiche rien sans carte", () => {
    const { container } = render(<CardZoom carte={null} onClose={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("agrandit la carte avec un texte en grande taille (lisible sans pincer)", () => {
    render(<CardZoom carte={CARTE} onClose={() => {}} />);
    const zoom = screen.getByTestId("card-zoom");
    expect(zoom).toBeInTheDocument();
    // La référence est rendue dans le zoom à une taille lisible (classe de grande taille).
    const titre = screen.getByText("base1-25-pikachu");
    expect(titre.className).toContain("text-lg");
  });

  it("se ferme en touchant le fond", () => {
    const onClose = vi.fn();
    render(<CardZoom carte={CARTE} onClose={onClose} />);
    fireEvent.click(screen.getByTestId("card-zoom"));
    expect(onClose).toHaveBeenCalled();
  });
});
