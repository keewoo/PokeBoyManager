import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import InscriptionPage from "@/app/inscription/page";
import { registerAccount } from "@/lib/api/auth";

vi.mock("@/lib/api/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/auth")>("@/lib/api/auth");
  return { ...actual, registerAccount: vi.fn() };
});

describe("InscriptionPage", () => {
  beforeEach(() => {
    vi.mocked(registerAccount).mockReset();
  });

  it("refuse la soumission sans e-mail, mot de passe ni acceptation des CGU", async () => {
    const user = userEvent.setup();
    render(<InscriptionPage />);

    await user.click(screen.getByRole("button", { name: /créer mon espace/i }));

    expect(await screen.findByText(/adresse e-mail invalide|l'e-mail est requis/i)).toBeInTheDocument();
    expect(screen.getByText(/au moins 10 caractères/i)).toBeInTheDocument();
    expect(screen.getByText(/tu dois accepter les conditions/i)).toBeInTheDocument();
    expect(registerAccount).not.toHaveBeenCalled();
  });

  it("envoie l'inscription puis affiche l'écran « vérifie ta boîte mail »", async () => {
    vi.mocked(registerAccount).mockResolvedValue({ message: "ok" });
    const user = userEvent.setup();
    render(<InscriptionPage />);

    await user.type(screen.getByLabelText(/e-mail/i), "dresseur@example.fr");
    await user.type(screen.getByLabelText(/mot de passe/i), "un-mot-de-passe-solide");
    await user.click(screen.getByLabelText(/j'accepte les conditions/i));
    await user.click(screen.getByRole("button", { name: /créer mon espace/i }));

    await waitFor(() => expect(registerAccount).toHaveBeenCalledWith("dresseur@example.fr", "un-mot-de-passe-solide"));
    expect(await screen.findByText(/vérifie ta boîte mail/i)).toBeInTheDocument();
  });

  it("affiche l'erreur du serveur sans faire disparaître le formulaire", async () => {
    const { ApiError } = await import("@/lib/api/auth");
    vi.mocked(registerAccount).mockRejectedValue(new ApiError(400, "Le mot de passe doit contenir au moins 10 caractères."));
    const user = userEvent.setup();
    render(<InscriptionPage />);

    await user.type(screen.getByLabelText(/e-mail/i), "dresseur@example.fr");
    await user.type(screen.getByLabelText(/mot de passe/i), "xxxxxxxxxxxxx");
    await user.click(screen.getByLabelText(/j'accepte les conditions/i));
    await user.click(screen.getByRole("button", { name: /créer mon espace/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/au moins 10 caractères/i);
  });
});
