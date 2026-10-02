import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ZoneCachee, ZonePublique } from "./zone-consultation";
import type { VueCarte } from "@/lib/game/plateau";

const CARTES: VueCarte[] = [
  { instance_id: "d1", ref: "set-1-dracaufeu" },
  { instance_id: "d2", ref: "set-2-energie" },
];

describe("ZonePublique — consultable", () => {
  it("montre le compteur et ouvre la liste des cartes au clic", () => {
    render(<ZonePublique titre="ma défausse" cartes={CARTES} />);
    const bouton = screen.getByTestId("zone-publique-ma défausse");
    expect(bouton).toHaveTextContent("2");
    expect(screen.queryByTestId("zone-contenu-ma défausse")).toBeNull();
    fireEvent.click(bouton);
    const contenu = screen.getByTestId("zone-contenu-ma défausse");
    expect(contenu).toBeInTheDocument();
    expect(screen.getByText("set-1-dracaufeu")).toBeInTheDocument();
    expect(screen.getByText("set-2-energie")).toBeInTheDocument();
  });

  it("dit « vide » quand il n'y a rien à consulter (jamais un panneau muet)", () => {
    render(<ZonePublique titre="ma défausse" cartes={[]} />);
    fireEvent.click(screen.getByTestId("zone-publique-ma défausse"));
    expect(screen.getByText(/zone vide/i)).toBeInTheDocument();
  });
});

describe("ZoneCachee — compteur seulement", () => {
  it("affiche le nombre sans aucun moyen d'en voir le contenu", () => {
    render(<ZoneCachee titre="pioche" nombre={41} />);
    const zone = screen.getByTestId("zone-cachee-pioche");
    expect(zone).toHaveTextContent("41");
    // Une zone cachée n'est pas un bouton : son contenu n'existe pas côté client.
    expect(zone.tagName).toBe("DIV");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
