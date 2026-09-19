import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import MotDePasseOubliePage from "@/app/mot-de-passe-oublie/page";
import { forgotPassword } from "@/lib/api/auth";

vi.mock("@/lib/api/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/auth")>("@/lib/api/auth");
  return { ...actual, forgotPassword: vi.fn() };
});

describe("MotDePasseOubliePage", () => {
  beforeEach(() => {
    vi.mocked(forgotPassword).mockReset();
  });

  it("affiche le même écran de succès, e-mail connu ou non (anti-énumération)", async () => {
    vi.mocked(forgotPassword).mockResolvedValue({ message: "ok" });
    const user = userEvent.setup();
    render(<MotDePasseOubliePage />);

    await user.type(screen.getByLabelText(/e-mail/i), "inconnu@example.fr");
    await user.click(screen.getByRole("button", { name: /envoyer le lien/i }));

    await waitFor(() => expect(forgotPassword).toHaveBeenCalledWith("inconnu@example.fr"));
    const notice = await screen.findByText(/si un compte existe pour cette adresse/i);
    expect(notice.textContent).not.toMatch(/n'existe pas/i);
  });
});
