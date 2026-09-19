import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import ProfilPage from "@/app/profil/page";

vi.mock("@/lib/api/profile", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/profile")>("@/lib/api/profile");
  return {
    ...actual,
    getProfile: vi.fn(),
    updatePseudo: vi.fn(),
    requestEmailChange: vi.fn(),
    listSessions: vi.fn(),
    changePassword: vi.fn(),
    revokeSession: vi.fn(),
    uploadAvatar: vi.fn(),
    deleteAccount: vi.fn(),
  };
});

vi.mock("@/lib/api/ai-keys", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/ai-keys")>("@/lib/api/ai-keys");
  return {
    ...actual,
    listAiKeys: vi.fn(),
    getAiSettings: vi.fn(),
    getAiUsage: vi.fn(),
    upsertAiKey: vi.fn(),
    testAiKey: vi.fn(),
    deleteAiKey: vi.fn(),
    setDefaultProvider: vi.fn(),
  };
});

const PROFILE = {
  id: "u1",
  email: "dresseur@example.fr",
  email_verified: true,
  pending_email: null,
  pseudo: "dresseur_jf",
  has_avatar: false,
};

const SESSION = {
  id: "s1",
  user_agent: "Firefox · Linux",
  ip_address: "127.0.0.1",
  created_at: new Date().toISOString(),
  current: true,
};

describe("ProfilPage", () => {
  beforeEach(async () => {
    const profileApi = await import("@/lib/api/profile");
    const aiApi = await import("@/lib/api/ai-keys");

    vi.mocked(profileApi.getProfile).mockReset().mockResolvedValue(PROFILE);
    vi.mocked(profileApi.listSessions).mockReset().mockResolvedValue([SESSION]);
    vi.mocked(profileApi.updatePseudo).mockReset();
    vi.mocked(profileApi.requestEmailChange).mockReset();
    vi.mocked(profileApi.changePassword).mockReset();

    vi.mocked(aiApi.listAiKeys).mockReset().mockResolvedValue([]);
    vi.mocked(aiApi.getAiSettings).mockReset().mockResolvedValue({
      default_provider: null,
      default_model: null,
    });
    vi.mocked(aiApi.getAiUsage).mockReset().mockResolvedValue([]);
  });

  it("charge le profil et affiche l'onglet Identité par défaut", async () => {
    render(<ProfilPage />);

    expect(await screen.findByDisplayValue("dresseur_jf")).toBeInTheDocument();
    expect(screen.getByDisplayValue("dresseur@example.fr")).toBeInTheDocument();
  });

  it("enregistre un nouveau pseudo via PATCH /me", async () => {
    const profileApi = await import("@/lib/api/profile");
    vi.mocked(profileApi.updatePseudo).mockResolvedValue({ ...PROFILE, pseudo: "sacha" });
    const user = userEvent.setup();
    render(<ProfilPage />);

    const pseudoInput = await screen.findByDisplayValue("dresseur_jf");
    await user.clear(pseudoInput);
    await user.type(pseudoInput, "sacha");
    await user.click(screen.getByRole("button", { name: /enregistrer/i }));

    await waitFor(() => expect(profileApi.updatePseudo).toHaveBeenCalledWith("sacha"));
  });

  it("passe à l'onglet Sécurité et liste les sessions actives", async () => {
    const user = userEvent.setup();
    render(<ProfilPage />);

    await screen.findByDisplayValue("dresseur_jf");
    await user.click(screen.getByRole("button", { name: "Sécurité" }));

    expect(await screen.findByText("Firefox · Linux")).toBeInTheDocument();
    expect(screen.getByText("actuelle")).toBeInTheDocument();
  });

  it("passe à l'onglet Mon IA et affiche les trois fournisseurs", async () => {
    const user = userEvent.setup();
    render(<ProfilPage />);

    await screen.findByDisplayValue("dresseur_jf");
    await user.click(screen.getByRole("button", { name: "Mon IA" }));

    expect(await screen.findByText("Claude · Anthropic")).toBeInTheDocument();
    expect(screen.getByText("Gemini · Google")).toBeInTheDocument();
    expect(screen.getByText("ChatGPT · OpenAI")).toBeInTheDocument();
  });

  it("passe à l'onglet Mes données et demande le mot de passe avant suppression", async () => {
    const user = userEvent.setup();
    render(<ProfilPage />);

    await screen.findByDisplayValue("dresseur_jf");
    await user.click(screen.getByRole("button", { name: "Mes données" }));

    await user.click(screen.getByRole("button", { name: "Supprimer mon compte" }));
    expect(screen.getByLabelText(/mot de passe/i)).toBeInTheDocument();
  });
});
