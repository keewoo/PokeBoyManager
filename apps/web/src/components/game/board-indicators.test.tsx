import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BoardCard } from "./board-card";
import type { VuePokemon } from "@/lib/game/plateau";

function pokemon(over: Partial<VuePokemon> = {}): VuePokemon {
  return {
    cartes: [{ instance_id: "base-1", ref: "base1-25-pikachu" }],
    energies: [],
    outil: null,
    compteurs_degats: 0,
    etats_speciaux: [],
    orientation: "normale",
    ...over,
  };
}

describe("BoardCard — indicateurs d'état (lot j-plateau-etat-visuel)", () => {
  it("affiche les PV restants ET le maximum, en plus des compteurs de dégâts", () => {
    render(
      <BoardCard
        carte={{ instance_id: "base-1", ref: "base1-25-pikachu" }}
        pokemon={pokemon({ compteurs_degats: 20, pv_restants: 40, pv_max: 60 })}
        etiquette="Actif"
      />,
    );
    const pv = screen.getByTestId("pv-restants");
    expect(pv).toHaveAttribute("aria-label", "PV restants : 40 sur 60");
    expect(pv.textContent).toContain("40");
    expect(pv.textContent).toContain("/60");
    // Les dégâts restent visibles comme des compteurs (R-10.4) : 20 dégâts = 2 compteurs.
    expect(screen.getByLabelText("20 dégâts (2 compteurs)")).toBeInTheDocument();
  });

  it("type chaque énergie par une ABRÉVIATION, pas seulement par une couleur (daltonisme)", () => {
    render(
      <BoardCard
        carte={{ instance_id: "base-1", ref: "base1-25-pikachu" }}
        pokemon={pokemon({
          energies: [
            { instance_id: "e1", ref: "r-eau", type: "water" },
            { instance_id: "e2", ref: "r-feu", type: "fire" },
          ],
        })}
        etiquette="Actif"
      />,
    );
    const groupe = screen.getByLabelText("Énergies : Eau, Feu");
    // Chaque pastille porte un signe textuel (abréviation) en plus de sa couleur.
    expect(within(groupe).getByText("Ea")).toBeInTheDocument();
    expect(within(groupe).getByText("Fe")).toBeInTheDocument();
  });

  it("montre l'Outil, nommé par son type", () => {
    render(
      <BoardCard
        carte={{ instance_id: "base-1", ref: "base1-25-pikachu" }}
        pokemon={pokemon({ outil: { instance_id: "o1", ref: "r-outil", type: "metal" } })}
        etiquette="Actif"
      />,
    );
    expect(screen.getByLabelText("Outil : Métal")).toBeInTheDocument();
  });

  it("montre un état spécial par une icône nommée ET oriente la carte (double signal)", () => {
    const { container } = render(
      <BoardCard
        carte={{ instance_id: "base-1", ref: "base1-25-pikachu" }}
        pokemon={pokemon({ etats_speciaux: ["endormi"], orientation: "endormi" })}
        etiquette="Actif"
      />,
    );
    expect(screen.getByRole("img", { name: "Endormi" })).toBeInTheDocument();
    // L'orientation physique de la carte double le signal (couchée pour endormi).
    expect(container.querySelector('[data-orientation="endormi"]')).not.toBeNull();
  });

  it("met la carte en évidence quand le Pokémon vient d'agir", () => {
    const { container } = render(
      <BoardCard
        carte={{ instance_id: "base-1", ref: "base1-25-pikachu" }}
        pokemon={pokemon()}
        etiquette="Actif"
        miseEnEvidence
      />,
    );
    expect(container.querySelector("[data-mise-en-evidence]")).not.toBeNull();
  });

  it("sans information de PV (catalogue muet), n'invente pas de PV restants (D9)", () => {
    render(
      <BoardCard
        carte={{ instance_id: "base-1", ref: "base1-25-pikachu" }}
        pokemon={pokemon({ compteurs_degats: 20 })}
        etiquette="Actif"
      />,
    );
    expect(screen.queryByTestId("pv-restants")).toBeNull();
    // Mais les dégâts restent lisibles.
    expect(screen.getByLabelText("20 dégâts (2 compteurs)")).toBeInTheDocument();
  });
});
