import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GameBoard } from "./game-board";
import type { VueJoueur, VuePartie, VuePokemon } from "@/lib/game/plateau";

function pokemon(ref: string, over: Partial<VuePokemon> = {}): VuePokemon {
  return {
    cartes: [{ instance_id: `i-${ref}`, ref }],
    energies: [],
    outil: null,
    compteurs_degats: 0,
    etats_speciaux: [],
    orientation: "normale",
    ...over,
  };
}

function carte(ref: string) {
  return { instance_id: `i-${ref}`, ref };
}

const MOI: VueJoueur = {
  id: "a",
  actif: pokemon("moi-actif", { energies: [carte("en1"), carte("en2")], compteurs_degats: 20 }),
  banc: [pokemon("moi-banc1")],
  defausse: [carte("moi-defausse1")],
  zone_perdue: [],
  pioche_nombre: 41,
  recompenses_nombre: 6,
  main: [carte("main1"), carte("main2"), carte("main3")],
  recompenses_jetons: ["j1", "j2", "j3", "j4", "j5", "j6"],
};

const ADVERSAIRE: VueJoueur = {
  id: "b",
  actif: pokemon("adv-actif"),
  banc: [pokemon("adv-banc1")],
  defausse: [carte("adv-defausse1")],
  zone_perdue: [],
  pioche_nombre: 39,
  recompenses_nombre: 5,
  main_nombre: 3,
};

const VUE: VuePartie = {
  schema_version: 1,
  pour: "a",
  joueurs: [MOI, ADVERSAIRE],
  tour: {
    joueur_actif: "a",
    numero: 4,
    phase: "principale",
    energie_posee: false,
    supporter_joue: false,
    retraite_faite: false,
  },
  stade: carte("stade-foret"),
  stade_proprietaire: "a",
  terminee: false,
  vainqueur: null,
  raison_fin: null,
};

describe("GameBoard — disposition des deux camps", () => {
  it("rend les deux camps, leurs actifs et le Stade partagé", () => {
    render(<GameBoard vue={VUE} />);
    expect(screen.getByText("Toi")).toBeInTheDocument();
    expect(screen.getByText("Adversaire")).toBeInTheDocument();
    expect(screen.getByText("moi-actif")).toBeInTheDocument();
    expect(screen.getByText("adv-actif")).toBeInTheDocument();
    expect(screen.getByText("stade-foret")).toBeInTheDocument();
  });

  it("rend ma main (identités) mais seulement le NOMBRE de la main adverse", () => {
    render(<GameBoard vue={VUE} />);
    const main = screen.getByTestId("main-joueur");
    expect(within(main).getByText("main1")).toBeInTheDocument();
    expect(within(main).getByText("main3")).toBeInTheDocument();
    // La main adverse n'est qu'un compteur — aucune identité (anti-triche, serveur autoritaire).
    expect(screen.getByLabelText(/Main adverse : 3 carte/)).toBeInTheDocument();
  });

  it("affiche les zones cachées en compteur et les zones publiques en consultation", () => {
    render(<GameBoard vue={VUE} />);
    // Deux pioches (la mienne, l'adverse), chacune un simple nombre.
    const pioches = screen.getAllByTestId("zone-cachee-pioche");
    expect(pioches).toHaveLength(2);
    expect(pioches.some((p) => p.textContent?.includes("41"))).toBe(true);
    expect(pioches.some((p) => p.textContent?.includes("39"))).toBe(true);
    // Les défausses sont consultables (publiques).
    expect(screen.getByTestId("zone-publique-ma défausse")).toBeInTheDocument();
    expect(screen.getByTestId("zone-publique-défausse adverse")).toBeInTheDocument();
  });

  it("annonce les récompenses restantes des deux joueurs", () => {
    render(<GameBoard vue={VUE} />);
    // Les récompenses sont une zone cachée : un repère visuel (pips) + une annonce accessible.
    expect(screen.getAllByLabelText(/Toi : 6 récompense/).length).toBeGreaterThan(0);
    expect(screen.getByLabelText(/Adversaire : 5 récompense/)).toBeInTheDocument();
  });

  it("ouvre le zoom au survol d'une carte et le referme à la sortie", () => {
    render(<GameBoard vue={VUE} />);
    expect(screen.queryByTestId("card-zoom")).toBeNull();
    const monActif = screen.getByRole("button", { name: /Mon actif — moi-actif/ });
    fireEvent.mouseEnter(monActif);
    const zoom = screen.getByTestId("card-zoom");
    expect(within(zoom).getByText("moi-actif")).toBeInTheDocument();
    fireEvent.mouseLeave(monActif);
    expect(screen.queryByTestId("card-zoom")).toBeNull();
  });
});
