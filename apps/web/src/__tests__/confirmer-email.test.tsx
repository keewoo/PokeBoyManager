import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import ConfirmerEmailPage from "@/app/confirmer-email/page";
import { confirmEmailChange } from "@/lib/api/profile";

let searchParamsValue = "";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(searchParamsValue),
}));

vi.mock("@/lib/api/profile", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/profile")>("@/lib/api/profile");
  return { ...actual, confirmEmailChange: vi.fn() };
});

describe("ConfirmerEmailPage", () => {
  beforeEach(() => {
    vi.mocked(confirmEmailChange).mockReset();
    searchParamsValue = "";
  });

  it("sans jeton dans l'URL, affiche directement une erreur", async () => {
    render(<ConfirmerEmailPage />);
    expect(await screen.findByText(/lien de confirmation est invalide/i)).toBeInTheDocument();
    expect(confirmEmailChange).not.toHaveBeenCalled();
  });

  it("avec un jeton valide, confirme le changement d'adresse", async () => {
    searchParamsValue = "token=abc123";
    vi.mocked(confirmEmailChange).mockResolvedValue({ message: "ok" });
    render(<ConfirmerEmailPage />);

    expect(await screen.findByText(/nouvelle adresse e-mail est confirmée/i)).toBeInTheDocument();
    expect(confirmEmailChange).toHaveBeenCalledWith("abc123");
  });

  it("avec un jeton expiré, affiche le message du serveur", async () => {
    searchParamsValue = "token=expired";
    const { ApiError } = await import("@/lib/api/client");
    vi.mocked(confirmEmailChange).mockRejectedValue(new ApiError(400, "Ce lien a expiré."));
    render(<ConfirmerEmailPage />);

    expect(await screen.findByText("Ce lien a expiré.")).toBeInTheDocument();
  });
});
