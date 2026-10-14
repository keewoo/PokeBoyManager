import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EffetTypeAttaque } from "@/components/game/effet-type";
import { SPECS, type Typage, effetAttaque } from "@/lib/game/anim-types";

/**
 * Le rendu d'un effet typé (lot `j-anim-attaques-typees`).
 *
 * **Le test qui mord sans le changement** : le composant n'existait pas. Et il vérifie ici les deux
 * propriétés qui ne sont pas négociables — l'effet ne capture aucun clic, et la version réduite est
 * **immobile mais annoncée**.
 */

function typage(partiel: Partial<Typage> = {}): Typage {
  return {
    type: "fire",
    degats: 90,
    faiblesse: false,
    resistance: false,
    echec: false,
    ...partiel,
  };
}

describe("EffetTypeAttaque — mode animé", () => {
  it("ne rend rien sans effet", () => {
    const { container } = render(<EffetTypeAttaque effet={null} cle="1:0" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("compose les couches de son type, et les nomme en attribut", () => {
    const effet = effetAttaque(typage({ type: "water" }), { duree: 420 })!;
    render(<EffetTypeAttaque effet={effet} cle="1:0" />);
    const couche = screen.getByTestId("fx-typee");
    expect(couche).toHaveAttribute("data-fx", "eau");
    // Les couches rendues sont exactement celles que la table déclare — ni plus, ni moins.
    const rendues = Array.from(couche.querySelectorAll("[data-couche]"))
      .map((n) => n.getAttribute("data-couche"))
      .filter((c) => c !== "trace");
    expect(rendues.sort()).toEqual([...SPECS.water!.couches].sort());
  });

  it("ne capture jamais un clic, et reste dans les limites de la carte", () => {
    const effet = effetAttaque(typage(), { duree: 420 })!;
    render(<EffetTypeAttaque effet={effet} cle="1:0" />);
    const couche = screen.getByTestId("fx-typee");
    // Une animation ne peut pas empêcher un coup légal d'être joué.
    expect(couche.className).toContain("pointer-events-none");
    expect(couche.className).toContain("absolute");
    expect(couche.className).toContain("overflow-hidden");
    // Le journal porte déjà la phrase en texte : la doubler ferait bégayer les lecteurs d'écran.
    expect(couche).toHaveAttribute("aria-hidden", "true");
  });

  it("injecte au CSS les durées calculées par le module, jamais des valeurs en dur", () => {
    const effet = effetAttaque(typage({ type: "fire" }), { duree: 420 })!;
    render(<EffetTypeAttaque effet={effet} cle="1:0" />);
    const style = screen.getByTestId("fx-typee").getAttribute("style") ?? "";
    expect(style).toContain(`${effet.duree}ms`);
    expect(style).toContain(`${effet.trace}ms`);
  });

  it("rend autant de particules que l'intensité en demande", () => {
    const effet = effetAttaque(typage({ type: "fairy", degats: 300 }), { duree: 420 })!;
    render(<EffetTypeAttaque effet={effet} cle="1:0" />);
    const particules = screen.getByTestId("fx-typee").querySelectorAll(".pbm-fx-particule");
    expect(particules).toHaveLength(effet.particules);
    // Chaque particule part dans sa direction, de façon déterministe : une capture de recette
    // reste reproductible.
    expect(particules[0]?.getAttribute("style")).toContain("--pbm-fx-angle");
  });

  it("marque la faiblesse, la résistance et l'échec en attributs — le CSS n'a rien à deviner", () => {
    const renforce = effetAttaque(typage({ degats: 120, faiblesse: true }), { duree: 420 })!;
    render(<EffetTypeAttaque effet={renforce} cle="1:0" />);
    expect(screen.getByTestId("fx-typee")).toHaveAttribute("data-renforce", "");

    const rate = effetAttaque(typage({ degats: 0, echec: true }), { duree: 480 })!;
    render(<EffetTypeAttaque effet={rate} cle="2:0" />);
    const couches = screen.getAllByTestId("fx-typee");
    expect(couches[couches.length - 1]).toHaveAttribute("data-echec", "");
    expect(couches[couches.length - 1]).toHaveAttribute("data-palier", "echec");
  });

  it("une trace n'est rendue que par les types qui en laissent une", () => {
    const avec = effetAttaque(typage({ type: "fire" }), { duree: 420 })!;
    const { container, rerender } = render(<EffetTypeAttaque effet={avec} cle="1:0" />);
    expect(container.querySelector('[data-couche="trace"]')).not.toBeNull();

    const sans = effetAttaque(typage({ type: "fairy" }), { duree: 420 })!;
    rerender(<EffetTypeAttaque effet={sans} cle="2:0" />);
    expect(container.querySelector('[data-couche="trace"]')).toBeNull();
  });
});

describe("EffetTypeAttaque — version réduite", () => {
  it("ne bouge pas, et porte toute l'information en texte", () => {
    const effet = effetAttaque(typage({ degats: 120, faiblesse: true }), {
      duree: 420,
      reduit: true,
    })!;
    render(<EffetTypeAttaque effet={effet} cle="1:0" />);
    // Aucune couche animée : la version réduite est un autre canal, pas la même chose en plus court.
    expect(screen.queryByTestId("fx-typee")).toBeNull();
    const badge = screen.getByTestId("fx-reduit");
    expect(badge.querySelector(".pbm-fx-couche")).toBeNull();
    expect(badge.textContent).toContain("120");
  });

  it("est ANNONCÉE aux lecteurs d'écran — elle est le seul canal visuel qui reste", () => {
    const effet = effetAttaque(typage({ type: "psychic", degats: 60 }), {
      duree: 420,
      reduit: true,
    })!;
    render(<EffetTypeAttaque effet={effet} cle="1:0" />);
    const badge = screen.getByTestId("fx-reduit");
    // Contrairement à la couche animée (`aria-hidden`), celle-ci est nommée : couper les animations
    // ne doit jamais vouloir dire ne plus savoir ce qui vient de se passer.
    expect(badge).not.toHaveAttribute("aria-hidden");
    expect(badge).toHaveAttribute("role", "img");
    expect(badge.getAttribute("aria-label")).toContain("Psy");
    expect(badge.getAttribute("aria-label")).toContain("60");
  });

  it("ne capture pas de clic non plus", () => {
    const effet = effetAttaque(typage(), { duree: 420, reduit: true })!;
    render(<EffetTypeAttaque effet={effet} cle="1:0" />);
    expect(screen.getByTestId("fx-reduit").className).toContain("pointer-events-none");
  });
});
