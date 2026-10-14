import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BoardCard } from "./board-card";
import { CardZoom } from "./card-zoom";
import { effetAttaque } from "@/lib/game/anim-types";
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

/**
 * ⛔ L'effet typé ne cache JAMAIS un compteur de dégâts (lot `j-anim-attaques-typees`).
 *
 * C'est le risque que le lot nomme en propre : « dix animations écrites séparément : [...] l'une
 * d'elles finira par cacher un compteur de dégâts au moment décisif ». La parade n'est pas une
 * consigne mais un **ordre de DOM** : l'effet et les indicateurs sont tous deux `absolute`, donc
 * c'est leur ordre qui décide lequel passe au-dessus. L'effet est rendu avant, donc dessous.
 *
 * **Le test qui mord sans le changement** : inverser les deux lignes dans `board-card.tsx` le fait
 * tomber — et c'est exactement la régression qu'on ne verrait pas à l'œil sur une machine de bureau,
 * où l'effet passe en 400 ms.
 */
describe("BoardCard — l'effet typé passe SOUS les indicateurs", () => {
  const POKEMON = {
    cartes: [CARTE],
    energies: [],
    outil: null,
    compteurs_degats: 90,
    etats_speciaux: [],
    orientation: "normale" as const,
    pv_restants: 30,
    pv_max: 120,
  };

  it("l'effet est rendu AVANT les indicateurs : il ne peut pas les recouvrir", () => {
    const effet = effetAttaque(
      { type: "fire", degats: 90, faiblesse: true, resistance: false, echec: false },
      { duree: 420 },
    )!;
    const { container } = render(
      <BoardCard carte={CARTE} pokemon={POKEMON} effet={effet} effetCle="1:0" />,
    );
    const racine = container.firstElementChild!;
    const enfants = Array.from(racine.children);
    const rangEffet = enfants.findIndex((n) => n.getAttribute("data-testid") === "fx-typee");
    // Les indicateurs sont rendus dans un fragment : on repère le compteur de dégâts par son nom.
    const compteur = screen.getByLabelText(/90 dégâts/);
    const rangCompteur = enfants.findIndex((n) => n.contains(compteur));
    expect(rangEffet, "aucun effet typé rendu").toBeGreaterThanOrEqual(0);
    expect(rangCompteur, "aucun compteur de dégâts rendu").toBeGreaterThanOrEqual(0);
    expect(
      rangEffet,
      "l'effet typé est rendu APRÈS les indicateurs : il recouvrirait le compteur de dégâts",
    ).toBeLessThan(rangCompteur);
  });

  it("les compteurs et les PV restants restent lisibles pendant l'effet", () => {
    const effet = effetAttaque(
      { type: "lightning", degats: 120, faiblesse: false, resistance: false, echec: false },
      { duree: 420 },
    )!;
    render(<BoardCard carte={CARTE} pokemon={POKEMON} effet={effet} effetCle="1:0" />);
    expect(screen.getByLabelText(/90 dégâts/)).toBeInTheDocument();
    expect(screen.getByTestId("pv-restants")).toBeInTheDocument();
  });

  it("le geste de la carte est porté en attribut, et la durée vient du module", () => {
    const effet = effetAttaque(
      { type: "psychic", degats: 60, faiblesse: false, resistance: false, echec: false },
      { duree: 420 },
    )!;
    const { container } = render(
      <BoardCard carte={CARTE} pokemon={POKEMON} effet={effet} effetCle="1:0" />,
    );
    const racine = container.firstElementChild!;
    expect(racine).toHaveAttribute("data-fx-geste", "distorsion");
    expect(racine.getAttribute("style")).toContain(`${effet.duree}ms`);
  });

  it("sans effet, aucun attribut de geste n'est posé et rien n'est rendu en plus", () => {
    const { container } = render(<BoardCard carte={CARTE} pokemon={POKEMON} />);
    expect(container.firstElementChild).not.toHaveAttribute("data-fx-geste");
    expect(screen.queryByTestId("fx-typee")).toBeNull();
    expect(screen.queryByTestId("fx-reduit")).toBeNull();
  });
});
