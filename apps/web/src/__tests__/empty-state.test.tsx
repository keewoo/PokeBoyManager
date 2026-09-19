import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EmptyState } from "@/components/empty-state";

describe("EmptyState", () => {
  it("affiche le titre et la description", () => {
    render(<EmptyState title="Collection vide" description="Ajoute ta première carte." />);
    expect(screen.getByText("Collection vide")).toBeInTheDocument();
    expect(screen.getByText("Ajoute ta première carte.")).toBeInTheDocument();
  });

  it("n'affiche aucune action quand aucune n'est fournie", () => {
    render(<EmptyState title="Collection vide" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("affiche un lien d'action quand un href est fourni", () => {
    render(<EmptyState title="Collection vide" action={{ label: "Ajouter une carte", href: "/ajouter" }} />);
    const link = screen.getByRole("link", { name: "Ajouter une carte" });
    expect(link).toHaveAttribute("href", "/ajouter");
  });

  it("appelle onClick quand l'action est un bouton", async () => {
    const onClick = vi.fn();
    render(<EmptyState title="Collection vide" action={{ label: "Réessayer", onClick }} />);
    screen.getByRole("button", { name: "Réessayer" }).click();
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
