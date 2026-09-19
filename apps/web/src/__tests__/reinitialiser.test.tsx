import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import ReinitialiserPage from "@/app/reinitialiser/page";
import { resetPassword } from "@/lib/api/auth";

let searchParamsValue = "";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(searchParamsValue),
}));

vi.mock("@/lib/api/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/auth")>("@/lib/api/auth");
  return { ...actual, resetPassword: vi.fn() };
});

describe("ReinitialiserPage", () => {
  beforeEach(() => {
    vi.mocked(resetPassword).mockReset();
    searchParamsValue = "";
  });

  it("sans jeton dans l'URL, n'affiche pas de formulaire", async () => {
    render(<ReinitialiserPage />);
    expect(await screen.findByText(/lien de réinitialisation est invalide/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/nouveau mot de passe/i)).not.toBeInTheDocument();
  });

  it("avec un jeton, soumet le nouveau mot de passe et confirme", async () => {
    searchParamsValue = "token=abc123";
    vi.mocked(resetPassword).mockResolvedValue({ message: "ok" });
    const user = userEvent.setup();
    render(<ReinitialiserPage />);

    await user.type(screen.getByLabelText(/nouveau mot de passe/i), "un-nouveau-mot-de-passe");
    await user.click(screen.getByRole("button", { name: /changer le mot de passe/i }));

    await waitFor(() =>
      expect(resetPassword).toHaveBeenCalledWith("abc123", "un-nouveau-mot-de-passe")
    );
    expect(await screen.findByText(/mot de passe a été changé/i)).toBeInTheDocument();
  });
});
