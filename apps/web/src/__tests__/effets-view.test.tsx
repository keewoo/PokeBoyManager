import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EffetsView } from "@/app/jeu/effets/effets-view";
import * as navigation from "next/navigation";
import * as profileApi from "@/lib/api/profile";
import type { ProfileResponse } from "@/lib/api/profile";
import { SPECS } from "@/lib/game/anim-types";

vi.mock("next/navigation", () => ({ notFound: vi.fn() }));
vi.mock("@/lib/api/profile", () => ({ getProfile: vi.fn() }));

/**
 * La galerie d'effets (`/jeu/effets`, lot `j-anim-attaques-typees`) — l'écran qui permet à JF et à
 * Aymeric de **valider le rendu** des onze types sans réunir en partie un Pokémon de chaque type.
 *
 * **Le test qui mord sans le changement** : l'écran n'existait pas. Il vérifie surtout deux choses
 * qui font la valeur de cette page : elle montre bien **les onze** types (une galerie incomplète ne
 * vaudrait aucune validation), et elle est **fermée** à un compte sans droit d'accès au jeu (D11),
 * comme toutes les routes `/jeu`.
 */

const PROFIL: ProfileResponse = {
  email: "jf@example.fr",
  game_access: true,
} as ProfileResponse;

beforeEach(() => {
  vi.mocked(profileApi.getProfile).mockResolvedValue(PROFIL);
  vi.mocked(navigation.notFound).mockClear();
});

describe("EffetsView — la galerie des onze types", () => {
  it("montre une vignette par type, sans exception", async () => {
    render(<EffetsView />);
    await waitFor(() => expect(screen.getByTestId("fx-galerie")).toBeInTheDocument());
    for (const spec of Object.values(SPECS)) {
      expect(
        screen.getByTestId(`fx-demo-${spec.cle}`),
        `aucune vignette pour ${spec.libelle}`,
      ).toBeInTheDocument();
    }
  });

  it("joue par défaut une attaque moyenne, et chaque vignette porte son effet", async () => {
    render(<EffetsView />);
    await waitFor(() => expect(screen.getByTestId("fx-galerie")).toBeInTheDocument());
    // Un effet typé est rendu dans chaque vignette : la galerie montre le MÊME composant que le
    // plateau, donc si celui-ci ne rend rien, cette page ne rend rien non plus.
    expect(screen.getAllByTestId("fx-typee")).toHaveLength(Object.keys(SPECS).length);
  });

  it("une attaque ratée se montre aussi, et reste un effet (pas un écran vide)", async () => {
    render(<EffetsView />);
    await waitFor(() => expect(screen.getByTestId("fx-galerie")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("fx-situation-echec"));
    const couches = screen.getAllByTestId("fx-typee");
    expect(couches).toHaveLength(Object.keys(SPECS).length);
    expect(couches[0]).toHaveAttribute("data-palier", "echec");
  });

  it("la faiblesse et la résistance sont montrables, et se distinguent en attribut", async () => {
    render(<EffetsView />);
    await waitFor(() => expect(screen.getByTestId("fx-galerie")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("fx-situation-faiblesse"));
    expect(screen.getAllByTestId("fx-typee")[0]).toHaveAttribute("data-renforce", "");

    fireEvent.click(screen.getByTestId("fx-situation-resistance"));
    expect(screen.getAllByTestId("fx-typee")[0]).toHaveAttribute("data-attenue", "");
  });

  it("« rejouer » garde la situation choisie — on relance, on ne réinitialise pas", async () => {
    render(<EffetsView />);
    await waitFor(() => expect(screen.getByTestId("fx-galerie")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("fx-situation-faiblesse"));
    expect(screen.getByTestId("fx-situation-faiblesse")).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByTestId("fx-rejouer"));
    // Le piège qu'on évite : un « rejouer » qui retomberait sur la situation par défaut obligerait
    // à re-cliquer la faiblesse à chaque passage — et on ne regarderait jamais deux fois le même
    // effet, qui est tout l'objet de cette page.
    expect(screen.getByTestId("fx-situation-faiblesse")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getAllByTestId("fx-typee")[0]).toHaveAttribute("data-renforce", "");
  });

  it("les repères de la carte (dégâts, PV) restent affichés par-dessus l'effet", async () => {
    render(<EffetsView />);
    await waitFor(() => expect(screen.getByTestId("fx-galerie")).toBeInTheDocument());
    // C'est l'autre chose que JF doit pouvoir valider d'un coup d'œil : un effet qui cacherait le
    // chiffre des dégâts se verrait ici immédiatement, sur les onze types à la fois.
    const vignette = screen.getByTestId(`fx-demo-${SPECS.fire!.cle}`);
    expect(vignette.textContent).toContain("100");
    expect(vignette.textContent).toContain("120");
  });
});

describe("EffetsView — droit d'accès au jeu (D11)", () => {
  it("un compte sans accès au jeu reçoit une page inexistante", async () => {
    vi.mocked(profileApi.getProfile).mockResolvedValue({
      ...PROFIL,
      game_access: false,
    } as ProfileResponse);
    render(<EffetsView />);
    await waitFor(() => expect(navigation.notFound).toHaveBeenCalled());
  });

  it("un échec de lecture du profil n'est PAS un refus : la page reste, avec son message", async () => {
    // « Je n'ai pas pu savoir » et « tu n'as pas le droit » sont deux choses différentes. Confondre
    // les deux ferait disparaître la page au premier hoquet du réseau.
    vi.mocked(profileApi.getProfile).mockRejectedValue(new Error("réseau"));
    render(<EffetsView />);
    await waitFor(() => expect(screen.getByTestId("fx-galerie")).toBeInTheDocument());
    expect(navigation.notFound).not.toHaveBeenCalled();
  });
});
