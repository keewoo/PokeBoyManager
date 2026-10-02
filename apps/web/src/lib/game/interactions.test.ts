import { describe, expect, it } from "vitest";

import {
  REPOS,
  cibleParReference,
  ciblesIlluminees,
  enAttente,
  reduire,
  type Selection,
} from "./interactions";
import type { VueActionLegale, VueCible } from "@/lib/game/plateau";

/**
 * Tests de la machine à états **pure** de l'interaction (lot `j-plateau-interactions`). Ils prouvent
 * l'enchaînement tap-tap / glisser-déposer sans navigateur : choisir un coup, cibler, confirmer un
 * coup irréversible, annuler — et qu'aucun geste hors contexte ne force une soumission. Ce fichier
 * échoue tant que le module `interactions` n'existe pas (« test qui échoue sans le changement »).
 */

function direct(over: Partial<VueActionLegale> = {}): VueActionLegale {
  return { type: "avancer_phase", params: {}, etiquette: "Passer", cibles: [], irreversible: false, ...over };
}

function cible(reference: string): VueCible {
  return { genre: "pokemon_en_jeu", reference, etiquette: reference };
}

function cible2(over: Partial<VueActionLegale> = {}): VueActionLegale {
  return {
    type: "attaquer",
    params: {},
    etiquette: "Attaquer",
    cibles: [cible("p1"), cible("p2")],
    irreversible: false,
    ...over,
  };
}

describe("reduire — coups directs (sans cible)", () => {
  it("un coup réversible part immédiatement, sans étape intermédiaire", () => {
    const action = direct();
    const r = reduire(REPOS, { t: "choisir-action", action });
    expect(r.selection).toEqual(REPOS);
    expect(r.soumission).toEqual({ action, cible: null });
  });

  it("un coup irréversible demande confirmation avant de partir", () => {
    const action = direct({ type: "abandonner", etiquette: "Abandonner", irreversible: true });
    const r1 = reduire(REPOS, { t: "choisir-action", action });
    expect(r1.soumission).toBeUndefined();
    expect(r1.selection).toEqual({ phase: "confirmation", action, cible: null });
    const r2 = reduire(r1.selection, { t: "confirmer" });
    expect(r2.selection).toEqual(REPOS);
    expect(r2.soumission).toEqual({ action, cible: null });
  });
});

describe("reduire — coups ciblés", () => {
  it("choisir un coup ciblé illumine ses cibles, et choisir une cible le soumet", () => {
    const action = cible2();
    const r1 = reduire(REPOS, { t: "choisir-action", action });
    expect(r1.selection).toEqual({ phase: "cible", action });
    expect(ciblesIlluminees(r1.selection)).toEqual(new Set(["p1", "p2"]));
    const r2 = reduire(r1.selection, { t: "choisir-cible", cible: cible("p2") });
    expect(r2.selection).toEqual(REPOS);
    expect(r2.soumission).toEqual({ action, cible: cible("p2") });
  });

  it("un coup ciblé irréversible demande confirmation après le choix de la cible", () => {
    const action = cible2({ irreversible: true });
    const r1 = reduire(REPOS, { t: "choisir-action", action });
    const r2 = reduire(r1.selection, { t: "choisir-cible", cible: cible("p1") });
    expect(r2.soumission).toBeUndefined();
    expect(r2.selection).toEqual({ phase: "confirmation", action, cible: cible("p1") });
    const r3 = reduire(r2.selection, { t: "confirmer" });
    expect(r3.soumission).toEqual({ action, cible: cible("p1") });
  });

  it("une cible hors de la liste valide est ignorée (aucune soumission)", () => {
    const r1 = reduire(REPOS, { t: "choisir-action", action: cible2() });
    const r2 = reduire(r1.selection, { t: "choisir-cible", cible: cible("inconnu") });
    expect(r2.selection).toEqual(r1.selection);
    expect(r2.soumission).toBeUndefined();
  });
});

describe("reduire — annulation et gestes hors contexte", () => {
  it("annuler revient au repos sans rien soumettre", () => {
    const enCours: Selection = { phase: "cible", action: cible2() };
    const r = reduire(enCours, { t: "annuler" });
    expect(r.selection).toEqual(REPOS);
    expect(r.soumission).toBeUndefined();
  });

  it("choisir une cible sans coup en cours ne fait rien", () => {
    const r = reduire(REPOS, { t: "choisir-cible", cible: cible("p1") });
    expect(r.selection).toEqual(REPOS);
    expect(r.soumission).toBeUndefined();
  });

  it("confirmer sans coup à confirmer ne fait rien", () => {
    const r = reduire(REPOS, { t: "confirmer" });
    expect(r.soumission).toBeUndefined();
  });
});

describe("aides d'affichage", () => {
  it("enAttente distingue le repos d'un coup en préparation", () => {
    expect(enAttente(REPOS)).toBe(false);
    expect(enAttente({ phase: "cible", action: cible2() })).toBe(true);
    expect(enAttente({ phase: "confirmation", action: direct(), cible: null })).toBe(true);
  });

  it("cibleParReference retrouve une cible valide pendant le ciblage, sinon null", () => {
    const sel: Selection = { phase: "cible", action: cible2() };
    expect(cibleParReference(sel, "p1")).toEqual(cible("p1"));
    expect(cibleParReference(sel, "p9")).toBeNull();
    expect(cibleParReference(REPOS, "p1")).toBeNull();
  });
});
