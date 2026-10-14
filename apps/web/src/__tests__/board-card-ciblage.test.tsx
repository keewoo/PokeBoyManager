/**
 * `BoardCard` — choisir une cible au clic doit rester possible (lot `j-e2e-deux-navigateurs`).
 *
 * Non-régression d'un défaut qui rendait le ciblage **impossible à la souris**. `CardZoom` est une
 * surcouche plein écran (`fixed inset-0 z-50`) qui se referme au clic ; elle s'ouvrait au survol
 * (`onMouseEnter` → `onPeek`). Comme un joueur à la souris doit passer sur la carte pour la
 * cliquer, le zoom s'ouvrait toujours **avant** le clic, et le clic atterrissait sur la surcouche
 * au lieu de choisir la cible — alors que la barre d'actions annonce « Touche ce coup puis une
 * cible ». Rien ne l'exerçait : le réducteur (`lib/game/interactions.ts`) est pur, l'e2e du plateau
 * ne mesurait que la mise en page, et au doigt il faut un **maintien long** pour zoomer.
 *
 * La règle posée : une carte **illuminée** (cible d'un coup en cours) ne zoome pas au survol. Le
 * zoom reste disponible partout ailleurs.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BoardCard } from "@/components/game/board-card";
import type { VueCarte } from "@/lib/game/plateau";

const CARTE: VueCarte = { instance_id: "j1:d1", ref: "e2epartie-1" };

describe("BoardCard — ciblage à la souris", () => {
  it("n'ouvre pas le zoom au survol d'une cible illuminée, et le clic choisit la cible", () => {
    const onPeek = vi.fn();
    const onActiver = vi.fn();
    render(
      <BoardCard
        carte={CARTE}
        etiquette="Mon actif"
        illumine
        onPeek={onPeek}
        onActiver={onActiver}
      />,
    );

    const carte = screen.getByRole("button", { name: /Mon actif/ });

    // Les trois ouvertures du zoom doivent rester fermées : un vrai clic à la souris fait
    // *survol* puis *appui* — et l'appui met la carte au focus (`tabIndex=0`). Il suffit que
    // l'une des trois ouvre la surcouche pour que le `mouseup` tombe sur elle et qu'aucun
    // `click` n'atteigne la carte.
    fireEvent.mouseEnter(carte);
    expect(
      onPeek,
      "une cible illuminée ne doit pas zoomer au survol : la surcouche avalerait le clic",
    ).not.toHaveBeenCalled();

    fireEvent.focus(carte);
    expect(
      onPeek,
      "ni au focus : l'appui de la souris met la carte au focus avant le relâchement",
    ).not.toHaveBeenCalled();

    fireEvent.pointerDown(carte);
    expect(onPeek, "ni au maintien long").not.toHaveBeenCalled();

    fireEvent.click(carte);
    expect(onActiver, "le clic sur une cible illuminée doit la choisir").toHaveBeenCalledTimes(1);
  });

  it("ouvre toujours le zoom au survol d'une carte qui n'est pas une cible", () => {
    const onPeek = vi.fn();
    render(<BoardCard carte={CARTE} etiquette="Actif adverse" onPeek={onPeek} />);

    fireEvent.mouseEnter(screen.getByRole("button", { name: /Actif adverse/ }));
    expect(onPeek, "hors ciblage, le zoom au survol reste la règle").toHaveBeenCalledWith(CARTE);
  });
});
