import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GameBoard } from "./game-board";
import { DECOR_DEFAUT } from "@/lib/game/decors";
import type { VueJoueur, VuePartie, VuePokemon } from "@/lib/game/plateau";

/**
 * Le **décor** sur le plateau (lot `j-arene-decors`) : il se pose, il se change, et il ne touche à
 * rien d'autre.
 *
 * Le critère d'acceptation « le changement de décor n'affecte ni la disposition ni la lisibilité »
 * se vérifie à deux niveaux, et il faut les deux : ici on prouve que **rien du plateau ne dépend du
 * décor** (le DOM rendu est identique, à l'attribut près), et `e2e/plateau-responsive.spec.ts`
 * prouve dans un vrai navigateur qu'aucun décor ne fait apparaître de défilement. Un test en jsdom
 * ne peut pas mesurer une mise en page — il peut, lui, montrer qu'il n'y a rien à mesurer.
 */

function pokemon(ref: string, type?: string): VuePokemon {
  return {
    cartes: [{ instance_id: `i-${ref}`, ref, type }],
    energies: [],
    outil: null,
    compteurs_degats: 0,
    etats_speciaux: [],
    orientation: "normale",
    type,
  };
}

function carte(ref: string, type?: string) {
  return { instance_id: `i-${ref}`, ref, type };
}

function vue(): VuePartie {
  const moi: VueJoueur = {
    id: "a",
    actif: pokemon("moi-actif", "fire"),
    banc: [pokemon("moi-banc1", "fire")],
    defausse: [carte("moi-defausse1", "fire")],
    zone_perdue: [],
    pioche_nombre: 41,
    recompenses_nombre: 6,
    main: [carte("main1", "fire"), carte("main2", "water")],
    recompenses_jetons: ["j1", "j2", "j3", "j4", "j5", "j6"],
  };
  const adversaire: VueJoueur = {
    id: "b",
    actif: pokemon("adv-actif", "water"),
    banc: [],
    defausse: [],
    zone_perdue: [],
    pioche_nombre: 39,
    recompenses_nombre: 5,
    main_nombre: 3,
  };
  return {
    schema_version: 1,
    pour: "a",
    joueurs: [moi, adversaire],
    tour: {
      joueur_actif: "a",
      numero: 4,
      phase: "principale",
      energie_posee: false,
      supporter_joue: false,
      retraite_faite: false,
    },
    stade: null,
    stade_proprietaire: null,
    terminee: false,
  } as VuePartie;
}

/** L'arène, telle qu'elle est dans le DOM. */
function arene(): HTMLElement {
  const el = screen.getByTestId("plateau").querySelector(".pbm-arena");
  if (!el) throw new Error("arène introuvable dans le plateau");
  return el as HTMLElement;
}

describe("décor du plateau", () => {
  it("porte le décor par défaut quand l'appelant n'en fournit aucun", () => {
    // Le replay rend `GameBoard` sans connaître les décors : il doit obtenir le fond d'origine,
    // pas un plateau sans fond.
    render(<GameBoard vue={vue()} />);
    expect(arene().dataset.decor).toBe(DECOR_DEFAUT);
    expect(arene().dataset.decorMoment).toBe("jour");
  });

  it("porte le décor et l'éclairage demandés", () => {
    render(<GameBoard vue={vue()} decor="caldeira" decorMoment="nuit" />);
    expect(arene().dataset.decor).toBe("caldeira");
    expect(arene().dataset.decorMoment).toBe("nuit");
  });

  it("ne peint plus le fond dans une classe : le décor serait sans effet", () => {
    render(<GameBoard vue={vue()} decor="lagon" />);
    // Une classe `bg-[radial-gradient(...)]` l'emporterait sur le fond du décor, et le réglage
    // n'aurait plus aucun effet visible — un bug muet, puisque `data-decor` serait toujours posé.
    expect(arene().className).not.toContain("bg-[radial-gradient");
  });

  it("rend exactement le même plateau sous les six décors", () => {
    // C'est la formulation vérifiable de « le changement de décor n'affecte pas la disposition » :
    // si le DOM est identique une fois les attributs de décor retirés, aucun composant ne peut
    // dépendre du décor — ni pour sa taille, ni pour sa présence, ni pour son texte.
    const empreintes = new Set<string>();
    for (const decor of ["arene", "caldeira", "lagon", "orage", "temple", "faille"]) {
      const { unmount } = render(<GameBoard vue={vue()} decor={decor} />);
      const html = screen
        .getByTestId("plateau")
        .innerHTML.replace(/data-decor(-moment)?="[^"]*"/g, "");
      empreintes.add(html);
      unmount();
    }
    expect(
      empreintes.size,
      "le plateau rendu diffère d'un décor à l'autre : un composant dépend du décor",
    ).toBe(1);
  });
});
