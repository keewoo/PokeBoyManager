import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AideClePage from "@/app/profil/aide-cle/page";

describe("Page d'aide « Ajouter ta clé IA »", () => {
  it("affiche le titre et l'usage de la clé en une phrase", () => {
    render(<AideClePage />);
    expect(
      screen.getByRole("heading", { level: 1, name: "Ajouter ta clé IA" })
    ).toBeInTheDocument();
    expect(screen.getByText(/reconnaître tes cartes sur tes photos/i)).toBeInTheDocument();
  });

  it("présente un parcours pour chacun des trois fournisseurs", () => {
    render(<AideClePage />);
    expect(screen.getByRole("heading", { level: 3, name: "Claude · Anthropic" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Gemini · Google" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "ChatGPT · OpenAI" })).toBeInTheDocument();
  });

  it("pointe chaque console par un lien externe valide", () => {
    render(<AideClePage />);
    expect(screen.getByRole("link", { name: /console\.anthropic\.com/ })).toHaveAttribute(
      "href",
      "https://console.anthropic.com/settings/keys"
    );
    expect(screen.getByRole("link", { name: /aistudio\.google\.com/ })).toHaveAttribute(
      "href",
      "https://aistudio.google.com/app/apikey"
    );
    expect(screen.getByRole("link", { name: /platform\.openai\.com/ })).toHaveAttribute(
      "href",
      "https://platform.openai.com/api-keys"
    );
  });

  it("donne nos vrais chiffres de coût et rappelle qui facture", () => {
    render(<AideClePage />);
    expect(screen.getByText(/environ 0,05\s?€/)).toBeInTheDocument();
    expect(screen.getByText(/22 169 fiches/)).toBeInTheDocument();
    expect(screen.getByText(/27,32\s?€/)).toBeInTheDocument();
    expect(screen.getByText(/facturé par ton fournisseur/i)).toBeInTheDocument();
  });

  it("renvoie vers la politique de confidentialité", () => {
    render(<AideClePage />);
    expect(screen.getByRole("link", { name: /politique de confidentialité/i })).toHaveAttribute(
      "href",
      "/confidentialite"
    );
  });

  it("reprend le message exact affiché par le site pour chaque panne", () => {
    render(<AideClePage />);
    // Messages copiés de `apps/api/src/pbm_api/ai/providers.py` et `.../ai/errors.py`.
    expect(screen.getByText(/« Clé refusée par le fournisseur\. »/)).toBeInTheDocument();
    expect(screen.getByText(/« Clé invalide ou révoquée par le fournisseur\. »/)).toBeInTheDocument();
    expect(screen.getByText(/« Quota dépassé chez le fournisseur\. »/)).toBeInTheDocument();
    expect(screen.getByText(/« Fournisseur surchargé — réessayez plus tard\. »/)).toBeInTheDocument();
    expect(screen.getByText(/« Fournisseur injoignable — réessayez plus tard\. »/)).toBeInTheDocument();
  });

  it("rappelle que PokéBoy reste utilisable sans clé", () => {
    render(<AideClePage />);
    const section = screen.getByRole("heading", { level: 2, name: /Et sans clé/ }).parentElement;
    expect(section).not.toBeNull();
    expect(within(section as HTMLElement).getByText(/à la main par la\s+recherche/i)).toBeInTheDocument();
  });
});
