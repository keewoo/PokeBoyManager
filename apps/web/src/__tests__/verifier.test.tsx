import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import VerifierPage from "@/app/verifier/page";
import { verifyEmail } from "@/lib/api/auth";

let searchParamsValue = "";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(searchParamsValue),
}));

vi.mock("@/lib/api/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/auth")>("@/lib/api/auth");
  return { ...actual, verifyEmail: vi.fn() };
});

describe("VerifierPage", () => {
  beforeEach(() => {
    vi.mocked(verifyEmail).mockReset();
    searchParamsValue = "";
  });

  it("sans jeton dans l'URL, affiche directement une erreur", async () => {
    render(<VerifierPage />);
    expect(await screen.findByText(/lien de vérification est invalide/i)).toBeInTheDocument();
    expect(verifyEmail).not.toHaveBeenCalled();
  });

  it("avec un jeton valide, confirme la vérification", async () => {
    searchParamsValue = "token=abc123";
    vi.mocked(verifyEmail).mockResolvedValue({ message: "ok" });
    render(<VerifierPage />);

    expect(await screen.findByText(/adresse e-mail est vérifiée/i)).toBeInTheDocument();
    expect(verifyEmail).toHaveBeenCalledWith("abc123");
  });

  it("avec un jeton expiré, affiche le message du serveur", async () => {
    searchParamsValue = "token=expired";
    const { ApiError } = await import("@/lib/api/auth");
    vi.mocked(verifyEmail).mockRejectedValue(new ApiError(400, "Ce lien a expiré."));
    render(<VerifierPage />);

    expect(await screen.findByText("Ce lien a expiré.")).toBeInTheDocument();
  });
});
