import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FenetreDecision } from "./fenetre-decision";
import { ApiError } from "@/lib/api/client";
import type { VueDemande, VueOptionCarte, VueJoueur, VuePartie } from "@/lib/game/plateau";

function joueur(id: string, cestMoi: boolean): VueJoueur {
  return {
    id,
    actif: null,
    banc: [],
    defausse: [],
    zone_perdue: [],
    pioche_nombre: 0,
    recompenses_nombre: 6,
    ...(cestMoi ? { main: [] } : { main_nombre: 0 }),
  };
}

function demande(over: Partial<VueDemande> = {}): VueDemande {
  return {
    id: "d0",
    destinataire: "moi",
    categorie: "cartes",
    libelle: "Choisis des cartes",
    regle: "R-9.3",
    obligatoire: true,
    minimum: 1,
    maximum: 2,
    source: { libelle: "Professeur Sylvestre" },
    delai_ms: 30000,
    temps_restant_ms: 30000,
    options: ["c1", "c2", "c3"],
    options_cartes: [
      { id: "c1", ref: "r1", nom: "Dracaufeu", type: "fire" },
      { id: "c2", ref: "r2", nom: "Bulbizarre", type: "grass" },
      { id: "c3", ref: "r3", nom: "Salamèche", type: "fire" },
    ],
    ...over,
  };
}

function vuePartie(d: VueDemande | undefined, pour = "moi"): VuePartie {
  return {
    schema_version: 3,
    pour,
    joueurs: [joueur("moi", pour === "moi"), joueur("adv", pour === "adv")],
    tour: {
      joueur_actif: "moi",
      numero: 1,
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
    demande: d,
  };
}

const T0 = () => 1_000_000;

describe("FenetreDecision — regard", () => {
  it("ne rend rien quand aucune décision n'est en attente", () => {
    const { container } = render(<FenetreDecision vue={vuePartie(undefined)} maintenant={T0} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("montre la modale quand c'est à moi de décider", () => {
    render(<FenetreDecision vue={vuePartie(demande())} maintenant={T0} />);
    expect(screen.getByTestId("fenetre-decision")).toBeInTheDocument();
    expect(screen.getByText(/Professeur Sylvestre/)).toBeInTheDocument();
  });

  it("montre une bannière d'attente, des deux côtés, quand c'est à l'adversaire de décider", () => {
    // Regard du joueur en attente : la demande vise l'adversaire.
    render(<FenetreDecision vue={vuePartie(demande({ destinataire: "adv" }), "moi")} maintenant={T0} />);
    expect(screen.getByTestId("attente-adverse")).toBeInTheDocument();
    expect(screen.queryByTestId("fenetre-decision")).toBeNull();
    expect(screen.getByText(/adversaire réfléchit/i)).toBeInTheDocument();
  });

  it("l'adversaire, lui, voit bien la modale de SA décision (explicite des deux côtés)", () => {
    render(<FenetreDecision vue={vuePartie(demande({ destinataire: "adv" }), "adv")} maintenant={T0} />);
    expect(screen.getByTestId("fenetre-decision")).toBeInTheDocument();
  });
});

describe("FenetreDecision — rendu générique par catégorie (aucun code par carte)", () => {
  it("cartes : liste cliquable + recherche", () => {
    render(<FenetreDecision vue={vuePartie(demande({ categorie: "cartes" }))} maintenant={T0} />);
    expect(screen.getByTestId("decision-recherche")).toBeInTheDocument();
    expect(screen.getByTestId("option-c1")).toBeInTheDocument();
  });

  it("carte : un seul choix (sélectionner une autre remplace)", () => {
    render(<FenetreDecision vue={vuePartie(demande({ categorie: "carte", minimum: 1, maximum: 1 }))} maintenant={T0} />);
    fireEvent.click(screen.getByTestId("option-c1"));
    expect(screen.getByTestId("option-c1")).toHaveAttribute("data-choisi", "oui");
    fireEvent.click(screen.getByTestId("option-c2"));
    expect(screen.getByTestId("option-c1")).toHaveAttribute("data-choisi", "non");
    expect(screen.getByTestId("option-c2")).toHaveAttribute("data-choisi", "oui");
  });

  it("ordre : liste ordonnable, la réponse est la permutation", () => {
    render(<FenetreDecision vue={vuePartie(demande({ categorie: "ordre", minimum: 3, maximum: 3 }))} maintenant={T0} />);
    expect(screen.getByTestId("decision-ordre")).toBeInTheDocument();
    expect(screen.getByTestId("ordre-descendre-c1")).toBeInTheDocument();
  });

  it("oui_non : deux boutons", () => {
    render(
      <FenetreDecision
        vue={vuePartie(demande({ categorie: "oui_non", options: ["oui", "non"], options_cartes: undefined, minimum: 1, maximum: 1 }))}
        maintenant={T0}
      />,
    );
    expect(screen.getByTestId("option-oui")).toBeInTheDocument();
    expect(screen.getByTestId("option-non")).toBeInTheDocument();
  });

  it("type : une puce par type", () => {
    render(
      <FenetreDecision
        vue={vuePartie(demande({ categorie: "type", options: ["fire", "water"], options_cartes: undefined, minimum: 1, maximum: 1 }))}
        maintenant={T0}
      />,
    );
    expect(screen.getByTestId("option-fire")).toBeInTheDocument();
    expect(screen.getByTestId("option-water")).toBeInTheDocument();
  });

  it("nombre : un pas à pas borné", () => {
    render(
      <FenetreDecision
        vue={vuePartie(demande({ categorie: "nombre", options: [], options_cartes: undefined, minimum: 1, maximum: 3 }))}
        maintenant={T0}
      />,
    );
    expect(screen.getByTestId("nombre-valeur").textContent).toBe("1");
    fireEvent.click(screen.getByTestId("nombre-plus"));
    expect(screen.getByTestId("nombre-valeur").textContent).toBe("2");
    fireEvent.click(screen.getByTestId("nombre-plus"));
    fireEvent.click(screen.getByTestId("nombre-plus")); // bloqué au maximum
    expect(screen.getByTestId("nombre-valeur").textContent).toBe("3");
  });
});

describe("FenetreDecision — recherche dans un grand ensemble", () => {
  it("retrouve une carte précise dans une pioche de soixante", () => {
    const options: VueOptionCarte[] = Array.from({ length: 60 }, (_, i) => ({
      id: `k${i}`,
      ref: `r${i}`,
      nom: i === 42 ? "Ronflex" : `Carte ${i}`,
      type: i % 2 === 0 ? "fire" : "water",
    }));
    render(
      <FenetreDecision
        vue={vuePartie(demande({ categorie: "carte", minimum: 1, maximum: 1, options: options.map((o) => o.id), options_cartes: options }))}
        maintenant={T0}
      />,
    );
    fireEvent.change(screen.getByTestId("decision-recherche"), { target: { value: "ronflex" } });
    expect(screen.getByTestId("option-k42")).toBeInTheDocument();
    expect(screen.queryByTestId("option-k0")).toBeNull();
  });
});

describe("FenetreDecision — compte à rebours et réponse par défaut", () => {
  it("affiche le temps restant (serveur) et ce qui se jouera à l'expiration", () => {
    render(
      <FenetreDecision
        vue={vuePartie(demande({ categorie: "carte", minimum: 1, maximum: 1, temps_restant_ms: 12000 }))}
        maintenant={T0}
      />,
    );
    expect(screen.getByTestId("decision-compteur").textContent).toContain("0:12");
    // Réponse par défaut d'une carte obligatoire : la PREMIÈRE option, nommée (pas un id brut).
    expect(screen.getByTestId("decision-defaut").textContent).toContain("Dracaufeu");
  });

  it("reprend le temps RESTANT après un F5 (pas le délai initial remis à neuf)", () => {
    // Après une reprise, le serveur renvoie temps_restant_ms déjà entamé (ex. 5 s sur 30).
    render(
      <FenetreDecision
        vue={vuePartie(demande({ categorie: "carte", minimum: 1, maximum: 1, delai_ms: 30000, temps_restant_ms: 5000 }))}
        maintenant={T0}
      />,
    );
    expect(screen.getByTestId("decision-compteur").textContent).toContain("0:05");
  });
});

describe("FenetreDecision — soumission", () => {
  it("valide et appelle onRepondre avec l'id de la demande et le choix", async () => {
    const onRepondre = vi.fn().mockResolvedValue(undefined);
    render(<FenetreDecision vue={vuePartie(demande({ categorie: "cartes", minimum: 1, maximum: 2 }))} onRepondre={onRepondre} maintenant={T0} />);
    expect(screen.getByTestId("decision-valider")).toBeDisabled(); // rien de choisi
    fireEvent.click(screen.getByTestId("option-c2"));
    expect(screen.getByTestId("decision-valider")).toBeEnabled();
    fireEvent.click(screen.getByTestId("decision-valider"));
    await waitFor(() => expect(onRepondre).toHaveBeenCalledWith("d0", ["c2"]));
  });

  it("annuler avant de valider efface le choix", () => {
    render(<FenetreDecision vue={vuePartie(demande({ categorie: "cartes" }))} onRepondre={vi.fn()} maintenant={T0} />);
    fireEvent.click(screen.getByTestId("option-c1"));
    expect(screen.getByTestId("decision-valider")).toBeEnabled();
    fireEvent.click(screen.getByTestId("decision-annuler"));
    expect(screen.getByTestId("option-c1")).toHaveAttribute("data-choisi", "non");
    expect(screen.getByTestId("decision-valider")).toBeDisabled();
  });

  it("une demande FACULTATIVE peut être passée (réponse vide = abandon)", async () => {
    const onRepondre = vi.fn().mockResolvedValue(undefined);
    render(<FenetreDecision vue={vuePartie(demande({ categorie: "cartes", obligatoire: false }))} onRepondre={onRepondre} maintenant={T0} />);
    fireEvent.click(screen.getByTestId("decision-passer"));
    await waitFor(() => expect(onRepondre).toHaveBeenCalledWith("d0", []));
  });

  it("un refus serveur (422) montre la raison du moteur, telle quelle", async () => {
    const onRepondre = vi.fn().mockRejectedValue(new ApiError(422, "R-9.3 : cette carte n'est pas un choix valide."));
    render(<FenetreDecision vue={vuePartie(demande({ categorie: "carte", minimum: 1, maximum: 1 }))} onRepondre={onRepondre} maintenant={T0} />);
    fireEvent.click(screen.getByTestId("option-c1"));
    fireEvent.click(screen.getByTestId("decision-valider"));
    await waitFor(() => expect(screen.getByTestId("decision-erreur").textContent).toContain("R-9.3"));
  });
});

describe("FenetreDecision — demande imbriquée (une demande en remplace une autre)", () => {
  it("repart d'une sélection vierge quand une nouvelle demande arrive", () => {
    const { rerender } = render(
      <FenetreDecision vue={vuePartie(demande({ id: "d0", categorie: "cartes" }))} onRepondre={vi.fn()} maintenant={T0} />,
    );
    fireEvent.click(screen.getByTestId("option-c1"));
    expect(screen.getByTestId("option-c1")).toHaveAttribute("data-choisi", "oui");
    // Une seconde demande (imbriquée) remplace la première : la sélection ne doit pas être traînée.
    rerender(
      <FenetreDecision
        vue={vuePartie(demande({ id: "d1", categorie: "cartes", libelle: "Choisis encore" }))}
        onRepondre={vi.fn()}
        maintenant={T0}
      />,
    );
    expect(screen.getByText(/Choisis encore/)).toBeInTheDocument();
    expect(screen.getByTestId("option-c1")).toHaveAttribute("data-choisi", "non");
  });
});
