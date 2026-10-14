import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { typesDeMonCamp, useDecorArene } from "@/lib/game/use-decor";
import type { VueJoueur, VuePartie, VuePokemon } from "@/lib/game/plateau";

/**
 * Le branchement du décor sur une partie (lot `j-arene-decors`) : d'où viennent les types, et
 * pourquoi le décor ne bouge plus une fois choisi.
 *
 * Sans fournisseur de confort, `useConfort()` rend les défauts (`decor: null`) : ces tests
 * mesurent donc le **thème automatique**, c'est-à-dire le cas de celui qui n'a rien réglé — le cas
 * de tout le monde au premier lancement.
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

function vue(moi: Partial<VueJoueur>, advActifType = "psychic"): VuePartie {
  const base: VueJoueur = {
    id: "a",
    actif: null,
    banc: [],
    defausse: [],
    zone_perdue: [],
    pioche_nombre: 40,
    recompenses_nombre: 6,
    main: [],
    ...moi,
  };
  const adversaire: VueJoueur = {
    id: "b",
    actif: pokemon("adv", advActifType),
    banc: [pokemon("adv-banc", advActifType)],
    defausse: [carte("adv-def", advActifType)],
    zone_perdue: [],
    pioche_nombre: 40,
    recompenses_nombre: 6,
    main_nombre: 5,
  };
  return {
    schema_version: 1,
    pour: "a",
    joueurs: [base, adversaire],
    tour: {
      joueur_actif: "a",
      numero: 1,
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

describe("types de mon camp", () => {
  it("ramasse l'actif, le banc, la main et la défausse", () => {
    const v = vue({
      actif: pokemon("a1", "fire"),
      banc: [pokemon("b1", "water")],
      main: [carte("m1", "grass")],
      defausse: [carte("d1", "metal")],
    });
    expect(typesDeMonCamp(v).sort()).toEqual(["fire", "grass", "metal", "water"]);
  });

  it("ne regarde JAMAIS le camp adverse", () => {
    // La frontière anti-triche est posée côté serveur ; ce test vérifie qu'on ne la contourne pas
    // par la porte de derrière — un décor qui révélerait le type du deck adverse serait une fuite
    // d'information, même minuscule.
    const v = vue({ actif: pokemon("a1", "fire") }, "darkness");
    expect(typesDeMonCamp(v)).toEqual(["fire"]);
  });

  it("ignore les cartes sans type plutôt que d'échouer", () => {
    const v = vue({ actif: pokemon("a1"), main: [carte("m1"), carte("m2", "water")] });
    expect(typesDeMonCamp(v)).toEqual(["water"]);
  });

  it("rend une liste vide sur une vue incohérente, au lieu de casser le plateau", () => {
    // `separerCamps` lève sur une vue à un seul joueur. Le décor n'est pas une raison d'empêcher
    // l'affichage : il retombe sur le défaut, et l'erreur reste signalée là où c'est son rôle.
    const v = { ...vue({}), joueurs: [] } as unknown as VuePartie;
    expect(typesDeMonCamp(v)).toEqual([]);
  });
});

describe("décor d'une partie", () => {
  it("suit le type dominant de mon camp", () => {
    const v = vue({ main: [carte("m1", "fire"), carte("m2", "fire"), carte("m3", "water")] });
    const { result } = renderHook(() => useDecorArene(v, 14));
    expect(result.current.decor).toBe("caldeira");
    expect(result.current.moment).toBe("jour");
  });

  it("prend le décor par défaut tant qu'aucune carte n'est connue", () => {
    const { result } = renderHook(() => useDecorArene(null, 14));
    expect(result.current.decor).toBe("arene");
  });

  it("ne change plus de décor quand le camp change en cours de partie", () => {
    // Le cœur du figement : poser une Énergie Feu ne doit pas faire basculer l'arène du gymnase au
    // volcan au milieu d'une partie. Un décor qui change tout seul est une distraction, pas un décor.
    const depart = vue({ main: [carte("m1", "water"), carte("m2", "water")] });
    const { result, rerender } = renderHook(({ v }) => useDecorArene(v, 14), {
      initialProps: { v: depart },
    });
    expect(result.current.decor).toBe("lagon");

    const plusTard = vue({
      main: [carte("m1", "water")],
      defausse: [carte("d1", "fire"), carte("d2", "fire"), carte("d3", "fire")],
    });
    rerender({ v: plusTard });
    expect(result.current.decor, "le décor a bougé en cours de partie").toBe("lagon");
  });

  it("passe en ambiance de nuit le soir", () => {
    const v = vue({ main: [carte("m1", "darkness")] });
    expect(renderHook(() => useDecorArene(v, 22)).result.current.moment).toBe("nuit");
    expect(renderHook(() => useDecorArene(v, 3)).result.current.moment).toBe("nuit");
    expect(renderHook(() => useDecorArene(v, 9)).result.current.moment).toBe("jour");
  });
});
