import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ApparitionPokemon } from "@/components/game/apparition-pokemon";
import { CALQUES, apparitionDe, signalApparition } from "@/lib/game/anim-apparition";
import type { Animation } from "@/lib/game/animations";
import { TYPAGE_VIDE } from "@/lib/game/anim-types";

const URL = "/img/apparitions/base1-4";

function animation(partiel: Partial<Animation> = {}): Animation {
  return {
    cle: "7:0",
    numero: 7,
    rang: 0,
    type: "pokemon_pose",
    effet: "pose",
    duree: 300,
    cible: "carte-a",
    camp: "moi",
    resume: false,
    nombre: 1,
    typage: null,
    ...partiel,
  };
}

function monter(partiel: Partial<Animation> = {}) {
  const apparition = apparitionDe(signalApparition(animation(partiel))!, "carte-a", URL);
  return render(<ApparitionPokemon apparition={apparition} />);
}

describe("ApparitionPokemon", () => {
  it("ne rend RIEN sans apparition — le cas courant, et il ne laisse aucun trou", () => {
    const { container } = render(<ApparitionPokemon apparition={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("empile les quatre calques, dans l'ordre du fond vers l'avant", () => {
    monter();
    const couche = screen.getByTestId("apparition-pokemon");
    const calques = [...couche.querySelectorAll(".pbm-a-calque")].map((n) =>
      n.getAttribute("data-calque"),
    );
    expect(calques).toEqual([...CALQUES]);
  });

  it("ne charge l'image QU'UNE fois, partagée par les calques — jamais une `img` par calque", () => {
    const { container } = monter();
    expect(container.querySelectorAll("img")).toHaveLength(0);
    const couche = screen.getByTestId("apparition-pokemon") as HTMLElement;
    expect(couche.style.getPropertyValue("--pbm-a-image")).toContain(URL);
  });

  it("donne à chaque calque sa propre amplitude : sans ça, pas de parallaxe", () => {
    monter();
    const amplitudes = [...screen.getByTestId("apparition-pokemon").querySelectorAll(".pbm-a-calque")].map(
      (n) => (n as HTMLElement).style.getPropertyValue("--pbm-a-amplitude"),
    );
    expect(new Set(amplitudes).size).toBeGreaterThan(1);
  });

  it("reste `aria-hidden` : c'est le journal de partie qui porte le texte, pas l'effet", () => {
    monter();
    expect(screen.getByTestId("apparition-pokemon")).toHaveAttribute("aria-hidden");
  });

  it("porte le motif et le type en attributs de données, pour que le CSS teinte sans logique JS", () => {
    monter({ type: "attaque_declaree", typage: { ...TYPAGE_VIDE, type: "fire", degats: 90 } });
    const couche = screen.getByTestId("apparition-pokemon");
    expect(couche).toHaveAttribute("data-motif", "attaque");
    expect(couche).toHaveAttribute("data-type", "fire");
  });

  it("dit « aucun » plutôt que de laisser l'attribut vide quand il n'y a pas de type", () => {
    monter();
    expect(screen.getByTestId("apparition-pokemon")).toHaveAttribute("data-type", "aucun");
  });

  it("rend les particules d'une attaque typée, et aucune pour une pose", () => {
    const { container: avecType } = monter({
      type: "attaque_declaree",
      typage: { ...TYPAGE_VIDE, type: "lightning", degats: 150 },
    });
    expect(avecType.querySelectorAll(".pbm-a-particule").length).toBeGreaterThan(0);

    const { container: pose } = monter();
    expect(pose.querySelectorAll(".pbm-a-particule")).toHaveLength(0);
  });
});
