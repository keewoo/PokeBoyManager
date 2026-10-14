import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CardZoom } from "@/components/game/card-zoom";
import { ZonePublique } from "@/components/game/zone-consultation";
import type { VueCarte } from "@/lib/game/plateau";

/**
 * Le clavier des surcouches de jeu (lot `j-accessibilite-jeu`).
 *
 * Aucun de ces tests ne passe avant ce lot : les quatre surcouches du jeu n'avaient **aucune**
 * gestion du clavier. Au clavier seul, une zone ouverte était un cul-de-sac — rien ne la fermait,
 * et le Tab continuait de parcourir le plateau *derrière* elle. Le critère d'acceptation du lot est
 * qu'une partie complète se joue au clavier seul : ces trois comportements en sont la base.
 */

function carte(ref: string): VueCarte {
  return { instance_id: `i-${ref}`, ref };
}

describe("surcouches de jeu : Échap, piège du focus, restitution", () => {
  it("Échap ferme la carte agrandie", () => {
    const onClose = vi.fn();
    render(<CardZoom carte={carte("pikachu")} onClose={onClose} />);
    expect(screen.getByTestId("card-zoom")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("une touche quelconque ne ferme rien", () => {
    // Garde contre l'excès inverse : un écouteur trop large fermerait la surcouche dès qu'un
    // joueur tape, par exemple dans le champ de recherche d'une fenêtre de décision.
    const onClose = vi.fn();
    render(<CardZoom carte={carte("rondoudou")} onClose={onClose} />);
    fireEvent.keyDown(document, { key: "a" });
    fireEvent.keyDown(document, { key: "Enter" });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("Échap ferme le panneau d'une zone publique, et le focus revient sur la pile", () => {
    render(<ZonePublique titre="défausse" cartes={[carte("roucool")]} />);
    const pile = screen.getByTestId("zone-publique-défausse");
    pile.focus();
    fireEvent.click(pile);

    const panneau = screen.getByTestId("zone-contenu-défausse");
    expect(panneau).toBeInTheDocument();
    // Le focus est entré dans le panneau : c'est le premier contrôle, « Fermer ».
    expect(document.activeElement).toBe(screen.getByTestId("zone-fermer-défausse"));

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("zone-contenu-défausse")).not.toBeInTheDocument();
    // Et il est revenu d'où il venait : sans ça, il retomberait sur le `<body>` et le joueur
    // devrait retraverser tout le plateau au Tab.
    expect(document.activeElement).toBe(pile);
  });

  it("le Tab reste dans le panneau modal (il ne repart pas dans le plateau)", () => {
    render(<ZonePublique titre="défausse" cartes={[carte("roucool")]} />);
    fireEvent.click(screen.getByTestId("zone-publique-défausse"));
    const fermer = screen.getByTestId("zone-fermer-défausse");
    expect(document.activeElement).toBe(fermer);

    // Un seul élément focusable : le Tab boucle donc sur lui-même plutôt que de sortir.
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(fermer);
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(fermer);
  });

  it("le zoom de carte ne piège PAS le Tab (surcouche non modale)", () => {
    // Il s'ouvre au survol ou au focus d'une carte et laisse le plateau autoritaire derrière :
    // en sortir au clavier est le comportement attendu. Un piège ici bloquerait le jeu.
    render(
      <>
        <button type="button" data-testid="dehors">
          ailleurs
        </button>
        <CardZoom carte={carte("pikachu")} onClose={() => {}} />
      </>,
    );
    const dehors = screen.getByTestId("dehors");
    dehors.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(dehors);
  });
});
