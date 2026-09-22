import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConditionBadge } from "@/components/condition-badge";

describe("ConditionBadge", () => {
  it("applique le style positif pour un état mint", () => {
    render(<ConditionBadge condition="mint" />);
    expect(screen.getByText("Mint")).toHaveClass("text-success-foreground");
  });

  it("applique le style d'alerte pour une carte abîmée", () => {
    render(<ConditionBadge condition="abime" />);
    expect(screen.getByText("Abîmée")).toHaveClass("text-danger-foreground");
  });
});
