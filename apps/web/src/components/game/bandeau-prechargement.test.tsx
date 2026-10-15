import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BandeauPrechargement } from "@/components/game/bandeau-prechargement";
import type { VueCarte, VueJoueur, VuePartie, VuePokemon } from "@/lib/game/plateau";

/**
 * La barre de pré-chargement (lot `j-assets-pipeline`).
 *
 * La propriété la plus importante n'est pas visuelle : le bandeau doit être **hors flux**. La page
 * `/jeu/parties/{id}` n'admet aucun défilement (e2e `plateau-responsive`), et un élément ajouté en
 * flux normal décale le plateau — un défaut qu'aucun test unitaire ne verrait et qui ferait échouer
 * le job e2e. D'où la garde explicite ci-dessous.
 */

function carte(url: string): VueCarte {
  return {
    instance_id: `i-${url}`,
    ref: "r",
    rendu: { origine: "photo", url, url_zoom: `${url}&zoom` },
  };
}

function pokemon(...cartes: VueCarte[]): VuePokemon {
  return {
    cartes,
    energies: [],
    outil: null,
    compteurs_degats: 0,
    etats_speciaux: [],
    orientation: "debout",
  };
}

function joueur(id: string, surcharges: Partial<VueJoueur> = {}): VueJoueur {
  return {
    id,
    actif: null,
    banc: [],
    defausse: [],
    zone_perdue: [],
    pioche_nombre: 40,
    recompenses_nombre: 6,
    ...surcharges,
  };
}

function vueAvec(urls: string[]): VuePartie {
  return {
    schema_version: 1,
    pour: "j1",
    joueurs: [joueur("j1", { main: urls.map(carte) }), joueur("j2")],
    tour: {
      joueur_actif: "j1",
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
  };
}

/** Un chargeur qu'on débloque à la main : sans ça, tout finirait avant le premier rendu. */
function chargeurTenu() {
  const relachements: Array<(ok: boolean) => void> = [];
  return {
    charger: () => new Promise<boolean>((resoudre) => relachements.push(resoudre)),
    relacherUne: (ok = true) => relachements.shift()?.(ok),
    enAttente: () => relachements.length,
  };
}

describe("BandeauPrechargement", () => {
  it("n'affiche rien quand il n'y a aucune image à charger", () => {
    render(<BandeauPrechargement vue={null} />);
    expect(screen.queryByTestId("prechargement-bandeau")).toBeNull();
  });

  it("annonce une progression honnête, comptée sur les images arrivées", async () => {
    const tenu = chargeurTenu();
    render(<BandeauPrechargement vue={vueAvec(["/a", "/b", "/c", "/d"])} charger={tenu.charger} />);

    await waitFor(() => expect(screen.getByTestId("prechargement-bandeau")).toBeTruthy());
    expect(screen.getByTestId("prechargement-compte").textContent).toBe("0/4");
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("0");

    tenu.relacherUne();
    await waitFor(() =>
      expect(screen.getByTestId("prechargement-compte").textContent).toBe("1/4"),
    );
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("25");
  });

  it("une image manquante fait avancer la barre : elle doit pouvoir finir", async () => {
    const tenu = chargeurTenu();
    render(<BandeauPrechargement vue={vueAvec(["/a", "/b"])} charger={tenu.charger} />);
    await waitFor(() => expect(screen.getByTestId("prechargement-bandeau")).toBeTruthy());

    tenu.relacherUne(false); // échec : l'écran retombera sur `url_repli`
    await waitFor(() =>
      expect(screen.getByTestId("prechargement-compte").textContent).toBe("1/2"),
    );
  });

  it("s'efface dès qu'il n'a plus rien à dire", async () => {
    const tenu = chargeurTenu();
    render(<BandeauPrechargement vue={vueAvec(["/a", "/b"])} charger={tenu.charger} />);
    await waitFor(() => expect(screen.getByTestId("prechargement-bandeau")).toBeTruthy());

    tenu.relacherUne();
    tenu.relacherUne();
    await waitFor(() => expect(screen.queryByTestId("prechargement-bandeau")).toBeNull());
  });

  it("est HORS FLUX : la page de partie n'admet aucun défilement", async () => {
    const tenu = chargeurTenu();
    render(<BandeauPrechargement vue={vueAvec(["/a"])} charger={tenu.charger} />);
    const bandeau = await waitFor(() => screen.getByTestId("prechargement-bandeau"));
    // `fixed` et non `relative`/`static` : en flux normal il décalerait le plateau, et c'est le
    // job e2e `plateau-responsive` qui tomberait — pas ce test-ci.
    expect(bandeau.className).toContain("fixed");
    // Et il ne vole aucun clic au plateau : la carte dessous reste saisissable.
    expect(bandeau.className).toContain("pointer-events-none");
  });

  it("est annoncé au lecteur d'écran sans l'interrompre", async () => {
    const tenu = chargeurTenu();
    render(<BandeauPrechargement vue={vueAvec(["/a", "/b"])} charger={tenu.charger} />);
    const barre = await waitFor(() => screen.getByRole("progressbar"));
    expect(barre.getAttribute("aria-live")).toBe("polite");
    expect(barre.getAttribute("aria-label")).toBeTruthy();
    expect(barre.getAttribute("aria-valuetext")).toContain("image");
  });
});
