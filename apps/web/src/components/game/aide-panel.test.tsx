import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AidePanel } from "@/components/game/aide-panel";
import { ETAPES_GUIDE } from "@/lib/game/guide";
import type { VueActionLegale, VuePartie, VuePokemon } from "@/lib/game/plateau";

function pokemon(energies = 0): VuePokemon {
  return {
    cartes: [{ instance_id: "c1", ref: "base1-1" }],
    energies: Array.from({ length: energies }, (_, i) => ({ instance_id: `e${i}`, ref: "feu" })),
    outil: null,
    compteurs_degats: 0,
    etats_speciaux: [],
    orientation: "debout",
  };
}

function coup(type: string, etiquette = `faire ${type}`): VueActionLegale {
  return { type, params: {}, etiquette, cibles: [], irreversible: false };
}

function vue(
  options: {
    legales?: VueActionLegale[];
    monTour?: boolean;
    monActif?: VuePokemon | null;
    terminee?: boolean;
  } = {},
): VuePartie {
  const joueur = (id: string, actif: VuePokemon | null = null) => ({
    id,
    actif,
    banc: [],
    defausse: [],
    zone_perdue: [],
    pioche_nombre: 40,
    recompenses_nombre: 6,
  });
  return {
    schema_version: 1,
    pour: "a",
    joueurs: [joueur("a", options.monActif ?? null), joueur("b")],
    tour: {
      joueur_actif: options.monTour === false ? "b" : "a",
      numero: 3,
      phase: "principale",
      energie_posee: false,
      supporter_joue: false,
      retraite_faite: false,
    },
    stade: null,
    stade_proprietaire: null,
    terminee: options.terminee ?? false,
    vainqueur: null,
    raison_fin: null,
    actions_legales: options.legales ?? [coup("attacher_energie"), coup("declarer_attaque")],
  };
}

describe("AidePanel — l'aide ne joue jamais à la place du joueur", () => {
  it("n'expose aucun moyen de soumettre un coup", async () => {
    // Troisième critère d'acceptation. On ouvre tout, on clique TOUT ce qui est cliquable, et on
    // vérifie qu'aucune requête réseau ne part : le composant n'a aucune fonction de jeu en props.
    const appels = vi.fn();
    vi.stubGlobal("fetch", appels);
    const utilisateur = userEvent.setup();

    render(<AidePanel vue={vue()} premierePartie />);
    for (const bouton of screen.getAllByRole("button")) {
      await utilisateur.click(bouton);
    }
    // Les onglets ont pu se fermer : on les reparcourt une seconde fois, tous ouverts.
    for (const bouton of screen.getAllByRole("button")) {
      await utilisateur.click(bouton);
    }

    expect(appels).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("affiche les coups possibles en texte, pas en boutons jouables", async () => {
    const utilisateur = userEvent.setup();
    render(<AidePanel vue={vue({ legales: [coup("poser", "Poser Carapuce au banc")] })} />);
    await utilisateur.click(screen.getByTestId("aide-bascule"));

    const liste = screen.getByTestId("aide-coups");
    expect(within(liste).getByText("Poser Carapuce au banc")).toBeTruthy();
    // Aucun bouton dans la liste des coups : on lit, on va jouer soi-même dans la barre d'actions.
    expect(within(liste).queryAllByRole("button")).toHaveLength(0);
  });
});

describe("AidePanel — placement : hors du flux, et pas sur les boutons des autres", () => {
  it("est posé hors du flux, ancré à GAUCHE et borné en largeur", () => {
    // Deux invariants payés par des pannes connues de ce dépôt, d'où une garde explicite :
    //  1. `fixed` — un panneau en flux normal allonge la page du plateau et casse le job e2e
    //     `plateau-responsive` (aucun défilement toléré), sans que vitest ni `tsc` bronchent ;
    //  2. ancré à gauche et borné — à droite, le tiroir recouvre `anim-sauter`
    //     (`animation-layer.tsx`, `absolute right-2 top-2`) sur l'écran de référence 844 × 390, et
    //     `anim-fluidite.spec.ts` le clique : Playwright échoue sur une interception de clic.
    render(<AidePanel vue={vue()} premierePartie />);
    const enveloppe = screen.getByTestId("aide").parentElement;
    const classes = enveloppe?.className ?? "";

    expect(classes, "le tiroir d'aide doit rester hors du flux").toContain("fixed");
    expect(classes, "ancrer à gauche : la droite porte les boutons d'animation").toContain(
      "justify-start",
    );
    expect(classes, "ancrer à gauche, jamais à droite").not.toContain("justify-end");
    expect(
      screen.getByTestId("aide").className,
      "borner la largeur : le flanc droit de l'arène doit rester cliquable",
    ).toMatch(/w-\[15rem\]/);
  });
});

describe("AidePanel — pourquoi je ne peux pas faire ça", () => {
  it("explique un refus du moteur et dit ce qu'on peut faire à la place", () => {
    render(<AidePanel vue={vue()} refus="Énergie déjà attachée ce tour. (R-5.4)" />);

    const bloc = screen.getByTestId("aide-refus");
    // Le titre de la règle, en français d'enfant.
    expect(within(bloc).getByText("Une seule énergie par tour")).toBeTruthy();
    // Le message du serveur, tel quel : il fait autorité sur le fait.
    expect(within(bloc).getByText(/Énergie déjà attachée ce tour\./)).toBeTruthy();
    // Et la porte de sortie — la moitié utile de l'aide.
    expect(screen.getByTestId("aide-alternative").textContent).toMatch(/Fais autre chose/);
  });

  it("s'ouvre de lui-même quand un coup est refusé", () => {
    // Un enfant ne va pas chercher l'aide : c'est l'aide qui vient à lui.
    render(<AidePanel vue={vue()} refus="Le coût n'est pas payé. (R-9.2)" />);
    expect(screen.getByTestId("aide-bascule").getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByTestId("aide-refus")).toBeTruthy();
  });

  it("garde la raison du serveur même pour une règle qu'elle ne connaît pas", () => {
    // Pas de repli silencieux : une règle inconnue ne fait pas disparaître le message du moteur.
    render(<AidePanel vue={vue()} refus="Refus exotique. (R-42.7)" />);
    const bloc = screen.getByTestId("aide-refus");
    expect(within(bloc).getByText(/Refus exotique\./)).toBeTruthy();
    expect(within(bloc).getByText("Ce coup n'est pas possible")).toBeTruthy();
  });

  it("n'affiche aucun bloc de refus quand rien n'a été refusé", () => {
    render(<AidePanel vue={vue()} />);
    expect(screen.queryByTestId("aide-refus")).toBeNull();
  });
});

describe("AidePanel — proposer des coups quand le joueur hésite", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("ne propose rien avant le délai, puis appelle le joueur", () => {
    // On ne suggère pas tout de suite : une aide qui parle avant qu'on réfléchisse empêche
    // d'apprendre. Et elle n'ouvre pas le tiroir par-dessus le plateau — elle fait signe.
    render(<AidePanel vue={vue()} delaiSuggestionMs={12_000} />);
    expect(screen.queryByTestId("aide-hesitation")).toBeNull();

    act(() => vi.advanceTimersByTime(11_900));
    expect(screen.queryByTestId("aide-hesitation")).toBeNull();

    act(() => vi.advanceTimersByTime(200));
    expect(screen.getByTestId("aide-hesitation").textContent).toMatch(/Tu hésites \?/);
    expect(screen.getByTestId("aide-pastille")).toBeTruthy();
    // Le tiroir reste replié : on n'impose rien.
    expect(screen.getByTestId("aide-bascule").getAttribute("aria-expanded")).toBe("false");
  });

  it("ne parle pas d'hésitation quand ce n'est pas son tour", () => {
    render(<AidePanel vue={vue({ monTour: false })} delaiSuggestionMs={1_000} />);
    act(() => vi.advanceTimersByTime(5_000));
    expect(screen.queryByTestId("aide-hesitation")).toBeNull();
  });

  it("ne parle pas d'hésitation sur une partie terminée", () => {
    render(<AidePanel vue={vue({ terminee: true })} delaiSuggestionMs={1_000} />);
    act(() => vi.advanceTimersByTime(5_000));
    expect(screen.queryByTestId("aide-hesitation")).toBeNull();
  });

  it("remet le compteur à zéro quand le plateau change", () => {
    // Le minuteur mesure l'attente DU JOUEUR, pas l'âge de la page : un coup joué le relance.
    const { rerender } = render(<AidePanel vue={vue()} delaiSuggestionMs={10_000} />);
    act(() => vi.advanceTimersByTime(9_000));

    const apres = vue();
    apres.tour.numero = 4;
    rerender(<AidePanel vue={apres} delaiSuggestionMs={10_000} />);
    act(() => vi.advanceTimersByTime(9_000));
    expect(screen.queryByTestId("aide-hesitation")).toBeNull();

    act(() => vi.advanceTimersByTime(1_500));
    expect(screen.getByTestId("aide-hesitation")).toBeTruthy();
  });
});

describe("AidePanel — partie guidée, glossaire et objectif", () => {
  it("rappelle l'objectif même replié", () => {
    render(<AidePanel vue={vue()} />);
    expect(screen.getByTestId("aide-objectif").textContent).toMatch(/récompense/i);
    expect(screen.getByTestId("aide-bascule").getAttribute("aria-expanded")).toBe("false");
  });

  it("ouvre la partie guidée d'emblée pour une première partie", () => {
    render(<AidePanel vue={vue()} premierePartie />);
    expect(screen.getByTestId("aide-guide-consigne").textContent).toBe(ETAPES_GUIDE[0]?.consigne);
  });

  it("avance d'étape quand le joueur a fait ce qu'on lui demandait", () => {
    const { rerender } = render(<AidePanel vue={vue()} premierePartie />);
    expect(screen.getByTestId("aide-guide-consigne").textContent).toBe(ETAPES_GUIDE[0]?.consigne);

    // Il a posé son Actif : l'étape suivante prend la place, sans qu'on touche à l'aide.
    rerender(<AidePanel vue={vue({ monActif: pokemon() })} premierePartie />);
    expect(screen.getByTestId("aide-guide-consigne").textContent).toBe(ETAPES_GUIDE[1]?.consigne);
  });

  it("donne la définition d'un mot du jeu quand on le choisit", async () => {
    const utilisateur = userEvent.setup();
    render(<AidePanel vue={vue()} />);
    await utilisateur.click(screen.getByTestId("aide-bascule"));
    await utilisateur.click(screen.getByTestId("aide-onglet-mots"));

    expect(screen.queryByTestId("aide-mot-definition")).toBeNull();
    await utilisateur.click(screen.getByTestId("aide-mot-Actif"));
    expect(screen.getByTestId("aide-mot-definition").textContent).toMatch(/au milieu du plateau/);
  });
});
