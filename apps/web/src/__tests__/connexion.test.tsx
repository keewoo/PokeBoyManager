import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import ConnexionPage from "@/app/connexion/page";
import { login } from "@/lib/api/auth";

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
  useSearchParams: () => new URLSearchParams(searchParamsValue),
}));

let searchParamsValue = "";

vi.mock("@/lib/api/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/auth")>("@/lib/api/auth");
  return { ...actual, login: vi.fn() };
});

describe("ConnexionPage", () => {
  beforeEach(() => {
    vi.mocked(login).mockReset();
    push.mockReset();
    refresh.mockReset();
    searchParamsValue = "";
  });

  it("affiche un message générique quand les identifiants sont refusés", async () => {
    const { ApiError } = await import("@/lib/api/auth");
    vi.mocked(login).mockRejectedValue(new ApiError(401, "E-mail ou mot de passe incorrect."));
    const user = userEvent.setup();
    render(<ConnexionPage />);

    await user.type(screen.getByLabelText(/e-mail/i), "dresseur@example.fr");
    await user.type(screen.getByLabelText(/mot de passe/i), "un-mot-de-passe");
    await user.click(screen.getByRole("button", { name: /se connecter/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("E-mail ou mot de passe incorrect.");
    // Le message ne doit jamais révéler si l'e-mail existe ou non (anti-énumération).
    expect(alert.textContent).not.toMatch(/n'existe pas/i);
    expect(push).not.toHaveBeenCalled();
  });

  it("redirige vers /next après une connexion réussie", async () => {
    searchParamsValue = "next=/collection";
    vi.mocked(login).mockResolvedValue({ id: "1", email: "dresseur@example.fr", email_verified: true });
    const user = userEvent.setup();
    render(<ConnexionPage />);

    await user.type(screen.getByLabelText(/e-mail/i), "dresseur@example.fr");
    await user.type(screen.getByLabelText(/mot de passe/i), "un-mot-de-passe");
    await user.click(screen.getByRole("button", { name: /se connecter/i }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/collection"));
  });

  it("ignore une URL absolue dans `next` (protection open-redirect)", async () => {
    searchParamsValue = "next=" + encodeURIComponent("https://evil.example/phish");
    vi.mocked(login).mockResolvedValue({ id: "1", email: "dresseur@example.fr", email_verified: true });
    const user = userEvent.setup();
    render(<ConnexionPage />);

    await user.type(screen.getByLabelText(/e-mail/i), "dresseur@example.fr");
    await user.type(screen.getByLabelText(/mot de passe/i), "un-mot-de-passe");
    await user.click(screen.getByRole("button", { name: /se connecter/i }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/"));
  });
});
