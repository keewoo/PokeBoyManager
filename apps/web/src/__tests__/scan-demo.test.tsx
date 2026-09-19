import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScanDemo } from "@/components/scan-demo";

describe("ScanDemo", () => {
  it("affiche les neuf emplacements numérotés de la démonstration", () => {
    render(<ScanDemo />);
    for (let n = 1; n <= 9; n += 1) {
      expect(screen.getByText(String(n))).toBeInTheDocument();
    }
  });

  it("résume la détection et signale les contrefaçons probables", () => {
    render(<ScanDemo />);
    expect(screen.getByText(/9 cartes détectées/)).toBeInTheDocument();
    expect(screen.getByText(/7 identifiées/)).toBeInTheDocument();
    expect(screen.getByText(/2 contrefaçons probables/)).toBeInTheDocument();
  });

  it("affiche une valeur estimée en euros", () => {
    render(<ScanDemo />);
    expect(screen.getByText(/valeur estimée/i)).toBeInTheDocument();
  });
});
