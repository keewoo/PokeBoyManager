import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CoucheAnimation, useFileAnimations } from "./animation-layer";
import { EFFETS, type CoupAnimation } from "@/lib/game/animations";

/** La durée nominale de l'effet « dégâts », lue dans le registre (et non recopiée ici). */
const DUREE_DEGATS = EFFETS.degats?.duree ?? 0;

/**
 * Le branchement du socle d'animation (lot `j-anim-socle`) : le crochet et la couche.
 *
 * Ce que ces tests prouvent, et qu'aucun test pur ne peut prouver :
 *
 * - l'animation **se saute** et **se jette** depuis l'écran (critère 1) ;
 * - `prefers-reduced-motion` ne rend **aucun** effet, et la file se vide quand même (rien ne
 *   disparaît, rien ne bloque) ;
 * - un onglet passé en arrière-plan **vide** la file au lieu de la laisser figée (le risque nommé
 *   par le lot) ;
 * - une reprise qui livre vingt coups d'un bloc affiche **un résumé**, pas vingt animations.
 */

/** Pose la réponse de `matchMedia` pour `prefers-reduced-motion`. */
function poserReducedMotion(matches: boolean) {
  const faux = (query: string) => ({
    matches: query.includes("prefers-reduced-motion") ? matches : false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
  window.matchMedia = faux as unknown as typeof window.matchMedia;
}

/** Fait croire au document qu'il est caché (jsdom n'expose pas de bascule). */
function cacherOnglet(cache: boolean) {
  Object.defineProperty(document, "visibilityState", {
    value: cache ? "hidden" : "visible",
    configurable: true,
  });
}

function coups(n: number, type = "degats"): CoupAnimation[] {
  return Array.from({ length: n }, (_, i) => ({
    numero: i + 1,
    evenements: [{ type, donnees: { cible: `i-${i}`, joueur: "a" } }],
  }));
}

/** Monte le crochet dans un composant témoin qui expose son état, pour le piloter depuis le test. */
function Temoin({ liste, pour = "a" }: { liste: CoupAnimation[]; pour?: string }) {
  const anim = useFileAnimations({ coups: liste, pour, cle: "g1" });
  return (
    <div>
      <span data-testid="mode">{anim.mode}</span>
      <span data-testid="attente">{anim.enAttente}</span>
      <span data-testid="effet">{anim.animation?.effet ?? "aucun"}</span>
      <span data-testid="duree">{anim.duree}</span>
      <button type="button" data-testid="t-sauter" onClick={anim.sauter}>
        sauter
      </button>
      <button type="button" data-testid="t-vider" onClick={anim.vider}>
        vider
      </button>
      <button type="button" data-testid="t-accelere" onClick={anim.basculerAccelere}>
        accélérer
      </button>
    </div>
  );
}

describe("useFileAnimations — le temps, et rien d'autre", () => {
  beforeEach(() => {
    poserReducedMotion(false);
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("joue les coups un par un, par minuterie — jamais plus d'un effet à la fois", () => {
    render(<Temoin liste={coups(3)} />);
    expect(screen.getByTestId("effet").textContent).toBe("impact");
    expect(screen.getByTestId("duree").textContent).toBe(String(DUREE_DEGATS));
    expect(screen.getByTestId("attente").textContent).toBe("2");

    // Une minuterie par animation : chaque `act` laisse React reposer la suivante.
    act(() => {
      vi.advanceTimersByTime(DUREE_DEGATS);
    });
    expect(screen.getByTestId("attente").textContent).toBe("1");

    act(() => {
      vi.advanceTimersByTime(DUREE_DEGATS);
    });
    expect(screen.getByTestId("attente").textContent).toBe("0");
    expect(screen.getByTestId("effet").textContent).toBe("impact");

    act(() => {
      vi.advanceTimersByTime(DUREE_DEGATS);
    });
    expect(screen.getByTestId("effet").textContent).toBe("aucun");
  });

  it("le mode accéléré divise la durée restante, sans rien perdre", () => {
    render(<Temoin liste={coups(2)} />);
    fireEvent.click(screen.getByTestId("t-accelere"));
    expect(screen.getByTestId("mode").textContent).toBe("accelere");
    const accelere = Number(screen.getByTestId("duree").textContent);
    expect(accelere).toBeLessThan(DUREE_DEGATS);

    act(() => {
      vi.advanceTimersByTime(accelere);
    });
    expect(screen.getByTestId("attente").textContent).toBe("0");
    act(() => {
      vi.advanceTimersByTime(accelere);
    });
    // Les deux animations ont tenu dans la moitié de la durée nominale d'une seule.
    expect(screen.getByTestId("effet").textContent).toBe("aucun");
  });

  it("« sauter » enchaîne, « vider » n'en laisse aucune en vol", () => {
    render(<Temoin liste={coups(3)} />);
    fireEvent.click(screen.getByTestId("t-sauter"));
    expect(screen.getByTestId("attente").textContent).toBe("1");
    fireEvent.click(screen.getByTestId("t-vider"));
    expect(screen.getByTestId("effet").textContent).toBe("aucun");
    expect(screen.getByTestId("attente").textContent).toBe("0");
  });

  it("onglet en arrière-plan : la file se VIDE, elle ne reste pas figée en vol", () => {
    render(<Temoin liste={coups(4)} />);
    expect(screen.getByTestId("effet").textContent).toBe("impact");

    cacherOnglet(true);
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(screen.getByTestId("effet").textContent).toBe("aucun");
    expect(screen.getByTestId("attente").textContent).toBe("0");
    cacherOnglet(false);
  });

  it("reprise après coupure : vingt coups d'un bloc donnent un résumé, pas vingt animations", () => {
    render(<Temoin liste={coups(20)} />);
    // Un résumé en cours + les deux dernières animations conservées.
    expect(screen.getByTestId("effet").textContent).toBe("rattrapage");
    expect(screen.getByTestId("attente").textContent).toBe("2");
  });

  it("attend le destinataire de la vue plutôt que de deviner un camp", () => {
    render(<Temoin liste={coups(2)} pour="" />);
    expect(screen.getByTestId("effet").textContent).toBe("aucun");
  });
});

describe("useFileAnimations — prefers-reduced-motion", () => {
  beforeEach(() => {
    poserReducedMotion(true);
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("ne rend AUCUN effet, et vide tout de même la file (rien ne bloque, rien ne disparaît)", () => {
    render(<Temoin liste={coups(5)} />);
    expect(screen.getByTestId("mode").textContent).toBe("reduit");
    expect(screen.getByTestId("effet").textContent).toBe("aucun");
    act(() => {
      vi.advanceTimersByTime(0);
    });
    expect(screen.getByTestId("attente").textContent).toBe("0");
  });
});

describe("CoucheAnimation — hors du flux, sans capture de clic", () => {
  const anim = {
    cle: "1:0",
    numero: 1,
    rang: 0,
    type: "degats",
    effet: "impact",
    duree: 420,
    cible: "i-pika",
    camp: "moi" as const,
    resume: false,
    nombre: 1,
    typage: null,
  };

  it("ne rend rien sans animation, ni pour une animation sans effet", () => {
    const { container, rerender } = render(<CoucheAnimation animation={null} duree={0} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<CoucheAnimation animation={{ ...anim, effet: null, duree: 0 }} duree={0} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("se dessine en position absolue, sans événement de pointeur, et masquée aux lecteurs d'écran", () => {
    render(<CoucheAnimation animation={anim} duree={420} />);
    const couche = screen.getByTestId("anim-couche");
    expect(couche.className).toContain("pointer-events-none");
    expect(couche.className).toContain("absolute");
    expect(couche).toHaveAttribute("aria-hidden", "true");
    expect(couche).toHaveAttribute("data-effet", "impact");
    expect(couche).toHaveAttribute("data-cible", "i-pika");
    expect(couche.getAttribute("style")).toContain("420ms");
  });

  it("offre de passer l'animation, et dit combien attendent derrière", () => {
    const onSauter = vi.fn();
    render(<CoucheAnimation animation={anim} duree={420} enAttente={3} onSauter={onSauter} />);
    const bouton = screen.getByTestId("anim-sauter");
    expect(bouton.textContent).toContain("3");
    fireEvent.click(bouton);
    expect(onSauter).toHaveBeenCalledTimes(1);
  });

  it("une animation de résumé annonce le nombre de coups rattrapés", () => {
    render(
      <CoucheAnimation
        animation={{ ...anim, effet: "rattrapage", resume: true, nombre: 18, type: "rattrapage" }}
        duree={450}
      />,
    );
    expect(screen.getByTestId("anim-pastille").textContent).toContain("18 coups rejoués");
  });
});
