import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GameBoard } from "./game-board";
import { ApiError } from "@/lib/api/client";
import type { VueActionLegale, VueActionRefusee, VueCible, VueJoueur, VuePartie, VuePokemon } from "@/lib/game/plateau";

/**
 * Interactions du plateau (lot `j-plateau-interactions`), au niveau composant — la CI fait foi.
 *
 * Ils prouvent les trois critères d'acceptation : aucune règle rejouée côté client (l'écran ne fait
 * que soumettre ce que le serveur déclare), un coup refusé affiche la **raison du moteur**, et un
 * double clic ne joue jamais deux fois. Plus les deux modes (tap sur cible) et la confirmation d'un
 * coup irréversible.
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

function vueAvec(
  legales: VueActionLegale[],
  refusees: VueActionRefusee[] = [],
): VuePartie {
  return {
    schema_version: 1,
    pour: "a",
    joueurs: [MOI, ADV],
    tour: {
      joueur_actif: "a",
      numero: 0,
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
    actions_legales: legales,
    actions_refusees: refusees,
  };
}

const PASSER: VueActionLegale = {
  type: "avancer_phase",
  params: {},
  etiquette: "Passer à la phase suivante",
  cibles: [],
  irreversible: false,
};

describe("GameBoard — soumettre un coup", () => {
  it("un clic soumet le coup exact du moteur ; un double clic ne le joue qu'une fois", async () => {
    const onJouer = vi.fn().mockResolvedValue(undefined);
    render(<GameBoard vue={vueAvec([PASSER])} onJouer={onJouer} />);
    const btn = screen.getByTestId("action-avancer_phase");
    fireEvent.click(btn);
    fireEvent.click(btn); // double clic quasi simultané (réseau lent, doigt pressé)
    await waitFor(() => expect(onJouer).toHaveBeenCalledTimes(1));
    expect(onJouer).toHaveBeenCalledWith(PASSER, null);
  });

  it("affiche la raison du moteur quand le serveur refuse le coup (422)", async () => {
    const onJouer = vi
      .fn()
      .mockRejectedValue(new ApiError(422, "Ce n'est pas le tour de « a » (R-5.1)."));
    render(<GameBoard vue={vueAvec([PASSER])} onJouer={onJouer} />);
    fireEvent.click(screen.getByTestId("action-avancer_phase"));
    expect(await screen.findByText(/Ce n'est pas le tour de/)).toBeInTheDocument();
  });

  it("est en lecture seule sans onJouer : aucune barre d'actions", () => {
    render(<GameBoard vue={vueAvec([PASSER])} />);
    expect(screen.queryByTestId("barre-actions")).not.toBeInTheDocument();
    expect(screen.getByTestId("plateau")).toBeInTheDocument();
  });
});

describe("GameBoard — confirmation d'un coup irréversible", () => {
  const ABANDON: VueActionLegale = {
    type: "abandonner",
    params: {},
    etiquette: "Abandonner la partie",
    cibles: [],
    irreversible: true,
  };

  it("ne joue qu'après un « oui » explicite, et pas si on annule", async () => {
    const onJouer = vi.fn().mockResolvedValue(undefined);
    render(<GameBoard vue={vueAvec([ABANDON])} onJouer={onJouer} />);

    fireEvent.click(screen.getByTestId("action-abandonner"));
    expect(screen.getByTestId("confirmation")).toBeInTheDocument();
    expect(onJouer).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("annuler")); // on se ravise
    expect(onJouer).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("action-abandonner"));
    fireEvent.click(screen.getByTestId("confirmer"));
    await waitFor(() => expect(onJouer).toHaveBeenCalledTimes(1));
    expect(onJouer).toHaveBeenCalledWith(ABANDON, null);
  });
});

describe("GameBoard — cibles illuminées", () => {
  it("un coup ciblé illumine sa cible, et un tap dessus le soumet avec cette cible", async () => {
    const cible: VueCible = { genre: "pokemon_en_jeu", reference: "i-mon-actif", etiquette: "Mon actif" };
    const action: VueActionLegale = {
      type: "soigner",
      params: {},
      etiquette: "Soigner",
      cibles: [cible],
      irreversible: false,
    };
    const onJouer = vi.fn().mockResolvedValue(undefined);
    render(<GameBoard vue={vueAvec([action])} onJouer={onJouer} />);

    fireEvent.click(screen.getByTestId("action-soigner")); // → phase de ciblage
    const carte = screen.getByLabelText(/Mon actif/);
    expect(carte).toHaveAttribute("data-illumine", "");
    fireEvent.click(carte);
    await waitFor(() => expect(onJouer).toHaveBeenCalledTimes(1));
    expect(onJouer).toHaveBeenCalledWith(action, cible);
  });
});

describe("GameBoard — coup refusé grisé", () => {
  it("affiche la commande refusée désactivée, avec la règle et le message du moteur", () => {
    const refus: VueActionRefusee = {
      type: "avancer_phase",
      params: {},
      etiquette: "Passer à la phase suivante",
      regle: "R-5.1",
      message: "Ce n'est pas le tour de « a ».",
      irreversible: false,
    };
    render(<GameBoard vue={vueAvec([], [refus])} onJouer={vi.fn()} />);
    const btn = screen.getByTestId("refus-avancer_phase");
    expect(btn).toBeDisabled();
    expect(btn.getAttribute("title")).toContain("R-5.1");
    expect(btn.getAttribute("title")).toContain("Ce n'est pas le tour de");
  });
});
