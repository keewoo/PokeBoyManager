import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GameBoard } from "./game-board";
import type { Animation } from "@/lib/game/animations";
import type { VueActionLegale, VueJoueur, VuePartie, VuePokemon } from "@/lib/game/plateau";

/**
 * Critère d'acceptation n°1 du lot `j-anim-socle` — **aucune animation ne peut empêcher une action
 * légale d'être jouée**.
 *
 * Ce test est celui qui mord : il rend le plateau avec une animation **en cours** et joue un coup
 * légal. Il échouerait si la couche d'animation capturait les clics (un oubli de
 * `pointer-events-none`), si elle recouvrait la barre d'actions, ou si le plateau se mettait à
 * conditionner son rendu à la fin d'une animation.
 */

function pk(ref: string, over: Partial<VuePokemon> = {}): VuePokemon {
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

const MOI: VueJoueur = {
  id: "a",
  actif: pk("mon-actif"),
  banc: [],
  defausse: [],
  zone_perdue: [],
  pioche_nombre: 40,
  recompenses_nombre: 6,
  main: [{ instance_id: "m1", ref: "carte-main" }],
};

const ADV: VueJoueur = {
  id: "b",
  actif: pk("adv-actif"),
  banc: [],
  defausse: [],
  zone_perdue: [],
  pioche_nombre: 40,
  recompenses_nombre: 6,
  main_nombre: 7,
};

const PASSER: VueActionLegale = {
  type: "avancer_phase",
  params: {},
  etiquette: "Passer à la phase suivante",
  cibles: [],
  irreversible: false,
};

const VUE: VuePartie = {
  schema_version: 1,
  pour: "a",
  joueurs: [MOI, ADV],
  tour: {
    joueur_actif: "a",
    numero: 3,
    phase: "principale",
    energie_posee: false,
    supporter_joue: false,
    retraite_faite: false,
  },
  stade: null,
  stade_proprietaire: null,
  terminee: false,
  vainqueur: null,
  raison_fin: null,
  actions_legales: [PASSER],
  actions_refusees: [],
};

const EN_COURS: Animation = {
  cle: "3:0",
  numero: 3,
  rang: 0,
  type: "ko",
  effet: "ko",
  duree: 600,
  cible: "i-adv-actif",
  camp: "adversaire",
  resume: false,
  nombre: 1,
  typage: null,
};

describe("GameBoard — une animation en cours n'empêche rien", () => {
  it("le coup légal se joue pendant l'animation, immédiatement", async () => {
    const onJouer = vi.fn().mockResolvedValue(undefined);
    render(
      <GameBoard vue={VUE} onJouer={onJouer} animation={EN_COURS} animationDuree={600} />,
    );
    // L'animation est bien à l'écran…
    expect(screen.getByTestId("anim-couche")).toBeInTheDocument();
    // … et le coup part quand même, sans attendre sa fin.
    fireEvent.click(screen.getByTestId("action-avancer_phase"));
    await waitFor(() => expect(onJouer).toHaveBeenCalledTimes(1));
    expect(onJouer).toHaveBeenCalledWith(PASSER, null);
  });

  it("la carte reste cliquable sous la couche (pointer-events-none)", () => {
    render(<GameBoard vue={VUE} animation={EN_COURS} animationDuree={600} />);
    const couche = screen.getByTestId("anim-couche");
    expect(couche.className).toContain("pointer-events-none");
    // La couche vit DANS l'arène, en position absolue : elle n'allonge pas la page (le plateau ne
    // tolère aucun défilement, lot `j-plateau-layout`).
    expect(couche.closest(".pbm-arena")).not.toBeNull();
    expect(couche.className).toContain("absolute");
  });

  it("le plateau se rend exactement pareil sans animation : l'état ne dépend pas d'elle", () => {
    const { container: avec } = render(
      <GameBoard vue={VUE} animation={EN_COURS} animationDuree={600} />,
    );
    const { container: sans } = render(<GameBoard vue={VUE} />);
    // La seule différence est la couche : les zones, les compteurs et les cartes sont identiques.
    expect(avec.querySelector("[data-testid='anim-couche']")).not.toBeNull();
    expect(sans.querySelector("[data-testid='anim-couche']")).toBeNull();
    const zones = (racine: HTMLElement) =>
      Array.from(racine.querySelectorAll("[data-testid^='zone-']")).map((n) => n.textContent);
    expect(zones(avec as HTMLElement)).toEqual(zones(sans as HTMLElement));
  });

  it("offre de passer l'animation quand l'écran le permet", () => {
    const onSauterAnimation = vi.fn();
    render(
      <GameBoard
        vue={VUE}
        animation={EN_COURS}
        animationDuree={600}
        animationsEnAttente={4}
        onSauterAnimation={onSauterAnimation}
      />,
    );
    fireEvent.click(screen.getByTestId("anim-sauter"));
    expect(onSauterAnimation).toHaveBeenCalledTimes(1);
  });
});
