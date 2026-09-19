import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AjouterPage from "@/app/ajouter/page";
import { ApiError, completeUpload, createUploads, hasAnyAiKey, putRawBytes } from "@/lib/api/uploads";

vi.mock("@/lib/api/uploads", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/uploads")>("@/lib/api/uploads");
  return {
    ...actual,
    hasAnyAiKey: vi.fn(),
    createUploads: vi.fn(),
    putRawBytes: vi.fn(),
    completeUpload: vi.fn(),
  };
});

function jpegFile(name = "carte.jpg", sizeBytes = 1024): File {
  const file = new File(["x".repeat(Math.min(sizeBytes, 1024))], name, { type: "image/jpeg" });
  Object.defineProperty(file, "size", { value: sizeBytes });
  return file;
}

describe("Page /ajouter", () => {
  beforeEach(() => {
    vi.mocked(hasAnyAiKey).mockReset();
    vi.mocked(createUploads).mockReset();
    vi.mocked(putRawBytes).mockReset();
    vi.mocked(completeUpload).mockReset();
  });

  it("affiche un message et un lien vers le profil sans clé IA configurée (D4)", async () => {
    vi.mocked(hasAnyAiKey).mockResolvedValue(false);
    render(<AjouterPage />);

    expect(await screen.findByText(/aucune clé ia n.est configurée/i)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /configurer une clé/i });
    expect(link).toHaveAttribute("href", "/profil");
    expect(screen.queryByText(/glisse tes photos ici/i)).not.toBeInTheDocument();
  });

  it("affiche la zone de dépôt conforme à la maquette quand une clé IA existe", async () => {
    vi.mocked(hasAnyAiKey).mockResolvedValue(true);
    render(<AjouterPage />);

    expect(await screen.findByText(/glisse tes photos ici/i)).toBeInTheDocument();
    expect(screen.getByText(/jpeg, png, heic/i)).toBeInTheDocument();
    expect(screen.getByText(/20 mo max par photo/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /choisir des fichiers/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /prendre une photo/i })).toBeInTheDocument();
  });

  it("ajoute une photo valide et affiche une estimation avant envoi", async () => {
    vi.mocked(hasAnyAiKey).mockResolvedValue(true);
    const user = userEvent.setup();
    render(<AjouterPage />);
    await screen.findByText(/glisse tes photos ici/i);

    const input = screen.getByLabelText("Choisir des fichiers");
    await user.upload(input, jpegFile("classeur-page-1.jpg"));

    expect(await screen.findByText("classeur-page-1.jpg")).toBeInTheDocument();
    expect(screen.getByText(/≈ 1 carte/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /lancer la reconnaissance/i })).toBeInTheDocument();
  });

  it("rejette côté client un fichier au-delà de 20 Mo", async () => {
    vi.mocked(hasAnyAiKey).mockResolvedValue(true);
    const user = userEvent.setup();
    render(<AjouterPage />);
    await screen.findByText(/glisse tes photos ici/i);

    const input = screen.getByLabelText("Choisir des fichiers");
    await user.upload(input, jpegFile("trop-lourde.jpg", 21 * 1024 * 1024));

    expect(await screen.findByText(/dépasse 20 mo/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /lancer la reconnaissance/i })).not.toBeInTheDocument();
  });

  it("rejette côté client un type de fichier non accepté", async () => {
    vi.mocked(hasAnyAiKey).mockResolvedValue(true);
    const user = userEvent.setup();
    render(<AjouterPage />);
    await screen.findByText(/glisse tes photos ici/i);

    const gif = new File(["x"], "animation.gif", { type: "image/gif" });
    const input = screen.getByLabelText("Choisir des fichiers");
    await user.upload(input, gif);

    expect(await screen.findByText(/format non accepté/i)).toBeInTheDocument();
  });

  it("envoie la photo (cible d'envoi, octets, complétion) et affiche « Envoyée »", async () => {
    vi.mocked(hasAnyAiKey).mockResolvedValue(true);
    vi.mocked(createUploads).mockResolvedValue([
      { upload_id: "11111111-1111-1111-1111-111111111111", method: "PUT", url: "https://s3.example/x", headers: {} },
    ]);
    vi.mocked(putRawBytes).mockResolvedValue(undefined);
    vi.mocked(completeUpload).mockResolvedValue({
      upload_id: "11111111-1111-1111-1111-111111111111",
      status: "processed",
      content_type: "image/jpeg",
      size_bytes: 1024,
      recognition_enabled: true,
      job_id: "job-1",
    });

    const user = userEvent.setup();
    render(<AjouterPage />);
    await screen.findByText(/glisse tes photos ici/i);

    const input = screen.getByLabelText("Choisir des fichiers");
    await user.upload(input, jpegFile("classeur-page-1.jpg"));
    await user.click(screen.getByRole("button", { name: /lancer la reconnaissance/i }));

    await waitFor(() => expect(putRawBytes).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(completeUpload).toHaveBeenCalledWith("11111111-1111-1111-1111-111111111111"));
    expect(await screen.findByText(/envoyée/i)).toBeInTheDocument();
  });

  it("affiche une erreur par photo si l'envoi échoue", async () => {
    vi.mocked(hasAnyAiKey).mockResolvedValue(true);
    vi.mocked(createUploads).mockResolvedValue([
      { upload_id: "22222222-2222-2222-2222-222222222222", method: "PUT", url: "https://s3.example/x", headers: {} },
    ]);
    vi.mocked(putRawBytes).mockRejectedValue(new ApiError(413, "Photo trop volumineuse."));

    const user = userEvent.setup();
    render(<AjouterPage />);
    await screen.findByText(/glisse tes photos ici/i);

    const input = screen.getByLabelText("Choisir des fichiers");
    await user.upload(input, jpegFile("classeur-page-1.jpg"));
    await user.click(screen.getByRole("button", { name: /lancer la reconnaissance/i }));

    expect(await screen.findByText(/photo trop volumineuse/i)).toBeInTheDocument();
  });
});
