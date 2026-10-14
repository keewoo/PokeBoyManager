import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { CoucheAnimation, useFileAnimations } from "@/components/game/animation-layer";
import { ConfortProvider, useConfort } from "@/lib/confort-provider";
import { CLE_CONFORT, CONFORT_DEFAUT } from "@/lib/game/confort";
import type { CoupAnimation } from "@/lib/game/animations";

/**
 * Le fournisseur de confort (lot `j-accessibilite-jeu`) : ce qu'il applique au document, ce qu'il
 * retient, et **ce qu'il coupe**.
 *
 * Le test qui compte est le dernier : le réglage « ne pas animer » doit réellement empêcher la
 * couche d'animation de rendre quoi que ce soit. C'est le critère d'acceptation « chaque animation
 * est coupable, globalement ». Avant ce lot, seul `prefers-reduced-motion` le pouvait — un réglage
 * que tout le monde ne sait pas trouver, et qu'un enfant sur le téléphone d'un parent ne touchera
 * pas.
 *
 * Aucun appel réseau n'est simulé : `avecSession={false}` (un visiteur) n'interroge pas le serveur,
 * et le cache local suffit à poser l'état de départ. C'est aussi ce qui prouve que le cache **sert**
 * à quelque chose.
 */

function Sonde() {
  const { confort } = useConfort();
  return <output data-testid="sonde">{JSON.stringify(confort)}</output>;
}

/** Monte la file d'animations dans le fournisseur et rend ce que la couche dessine. */
function PlateauAnime({ coups }: { coups: CoupAnimation[] }) {
  const etat = useFileAnimations({ coups, pour: "a", cle: "partie" });
  return (
    <>
      <output data-testid="mode">{etat.mode}</output>
      <CoucheAnimation animation={etat.animation} duree={etat.duree} />
    </>
  );
}

const COUPS: CoupAnimation[] = [
  { numero: 1, evenements: [{ type: "degats", donnees: { cible: "i-1", joueur: "a" } }] },
];

describe("fournisseur de confort", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute("data-anim");
    document.documentElement.removeAttribute("data-texte");
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it("pose sur <html> les attributs que le CSS interprète", async () => {
    await act(async () => {
      render(
        <ConfortProvider>
          <Sonde />
        </ConfortProvider>,
      );
    });
    expect(document.documentElement.getAttribute("data-anim")).toBe("completes");
    expect(document.documentElement.getAttribute("data-texte")).toBe("normale");
  });

  it("reprend le cache local au montage (c'est ce qui évite le clignotement)", async () => {
    window.localStorage.setItem(
      CLE_CONFORT,
      JSON.stringify({ animations: "reduites", taille_texte: "tres_grande", temps_rallonge: true }),
    );
    await act(async () => {
      render(
        <ConfortProvider>
          <Sonde />
        </ConfortProvider>,
      );
    });
    expect(screen.getByTestId("sonde")).toHaveTextContent('"animations":"reduites"');
    expect(document.documentElement.getAttribute("data-texte")).toBe("tres_grande");
  });

  it("un cache corrompu ne bloque pas le jeu : on repart des défauts", async () => {
    window.localStorage.setItem(CLE_CONFORT, "{ ceci n'est pas du JSON");
    await act(async () => {
      render(
        <ConfortProvider>
          <Sonde />
        </ConfortProvider>,
      );
    });
    expect(screen.getByTestId("sonde")).toHaveTextContent(JSON.stringify(CONFORT_DEFAUT));
  });

  it("hors fournisseur, les défauts s'appliquent (aucune exception)", () => {
    // Volontaire, contrairement à `useTheme` : un composant de jeu doit pouvoir se rendre dans un
    // test, un replay ou une capture sans qu'on monte un fournisseur de préférences.
    render(<Sonde />);
    expect(screen.getByTestId("sonde")).toHaveTextContent(JSON.stringify(CONFORT_DEFAUT));
  });

  it("le réglage « ne pas animer » empêche la couche de rendre quoi que ce soit", async () => {
    window.localStorage.setItem(CLE_CONFORT, JSON.stringify({ animations: "reduites" }));
    await act(async () => {
      render(
        <ConfortProvider>
          <PlateauAnime coups={COUPS} />
        </ConfortProvider>,
      );
    });
    expect(screen.getByTestId("mode")).toHaveTextContent("reduit");
    expect(screen.queryByTestId("anim-couche")).toBeNull();
  });

  it("sans ce réglage, la même animation est bien rendue (le test précédent prouve autre chose)", async () => {
    await act(async () => {
      render(
        <ConfortProvider>
          <PlateauAnime coups={COUPS} />
        </ConfortProvider>,
      );
    });
    expect(screen.getByTestId("mode")).toHaveTextContent("normal");
    expect(screen.getByTestId("anim-couche")).toBeInTheDocument();
  });
});
