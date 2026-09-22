import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReplacementCard } from "@/components/replacement-card";
import { codeFond, empreinte, fondPour } from "@/lib/replacement-card";

// 3 827 cartes du catalogue n'ont aucune image officielle. Plutôt qu'un cadre cassé, la carte est
// composée à partir de ses vraies données, avec un fond générique DÉTERMINISTE : la même carte
// garde toujours le même visuel. Ces tests gardent cette stabilité et le rendu des trois cas.
describe("fond déterministe", () => {
  it("empreinte est stable pour une même chaîne", () => {
    expect(empreinte("carte-123")).toBe(empreinte("carte-123"));
  });

  it("le fond choisi ne change pas entre deux appels (même carte, même visuel)", () => {
    const id = "3f2504e0-4f89-41d3-9a0c-0305e82c3301";
    expect(fondPour(id, "fire")).toBe(fondPour(id, "fire"));
  });

  it("choisit un des neuf fonds du type, numéroté 01 à 09", () => {
    for (const id of ["a", "b", "c", "carte-xyz", "0000", "zzzz-9999"]) {
      expect(fondPour(id, "water")).toMatch(/^\/fonds\/water-0[1-9]\.webp$/);
    }
  });

  it("une carte sans type (Dresseur) retombe sur colorless", () => {
    expect(codeFond(null)).toBe("colorless");
    expect(codeFond(undefined)).toBe("colorless");
    expect(codeFond("inconnu")).toBe("colorless");
    expect(fondPour("carte-1", null)).toMatch(/^\/fonds\/colorless-0[1-9]\.webp$/);
  });
});

describe("ReplacementCard", () => {
  it("compose un Pokémon avec nom, PV, type, extension, numéro et rareté", () => {
    render(
      <ReplacementCard
        cardId="carte-1"
        name="Scarabrute"
        elementType="grass"
        hp={90}
        supertype="Pokémon"
        setName="Méga-Ascension"
        cardNumber="001"
        rarity="Un Diamant"
      />
    );

    expect(screen.getByRole("img", { name: /Scarabrute — visuel non disponible/ })).toBeInTheDocument();
    expect(screen.getByText("Scarabrute")).toBeInTheDocument();
    expect(screen.getByText("90 PV")).toBeInTheDocument();
    expect(screen.getByText("Plante")).toBeInTheDocument();
    expect(screen.getByText(/Méga-Ascension · 001/)).toBeInTheDocument();
    expect(screen.getByText("Un Diamant")).toBeInTheDocument();
    expect(screen.getByText("Visuel non disponible")).toBeInTheDocument();
  });

  it("pour un Dresseur, affiche la catégorie au lieu des PV et prend un fond colorless", () => {
    render(
      <ReplacementCard
        cardId="carte-2"
        name="Professeur Chen"
        elementType={null}
        hp={null}
        supertype="Dresseur"
        setName="Promo SM"
        cardNumber="SM12"
      />
    );

    expect(screen.getByText("Dresseur")).toBeInTheDocument();
    expect(screen.queryByText(/PV/)).not.toBeInTheDocument();
    const fond = document.querySelector("img[aria-hidden]") as HTMLImageElement | null;
    expect(fond?.getAttribute("src")).toMatch(/^\/fonds\/colorless-0[1-9]\.webp$/);
  });
});
