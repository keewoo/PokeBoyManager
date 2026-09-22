import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RarityBadge } from "@/components/rarity-badge";

describe("RarityBadge", () => {
  it("applique le style doré pour une rareté élevée", () => {
    render(<RarityBadge rarity="ultra-rare" />);
    expect(screen.getByText("Ultra rare")).toHaveClass("text-gold-foreground");
  });

  it("n'applique pas le style doré pour une carte commune", () => {
    render(<RarityBadge rarity="commune" />);
    expect(screen.getByText("Commune")).not.toHaveClass("text-gold-foreground");
  });
});
