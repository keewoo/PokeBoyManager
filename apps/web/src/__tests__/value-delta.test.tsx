import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ValueDelta } from "@/components/value-delta";

describe("ValueDelta", () => {
  it("affiche une hausse avec un signe plus et la variante haute", () => {
    render(<ValueDelta value={12.3} />);
    const el = screen.getByText("+12,3 %");
    expect(el).toHaveAttribute("data-variant", "up");
  });

  it("affiche une baisse avec un signe moins et la variante basse", () => {
    render(<ValueDelta value={-4.25} />);
    const el = screen.getByText("-4,3 %");
    expect(el).toHaveAttribute("data-variant", "down");
  });

  it("affiche une valeur neutre sans signe", () => {
    render(<ValueDelta value={0} />);
    const el = screen.getByText("0,0 %");
    expect(el).toHaveAttribute("data-variant", "flat");
  });
});
