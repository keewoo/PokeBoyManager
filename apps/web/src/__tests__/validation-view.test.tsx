import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ValidationView } from "@/app/ajouter/validation/validation-view";
import { confirmAll, confirmDetection, getUpload, subscribeToUploadEvents } from "@/lib/api/validation";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
}));

vi.mock("@/lib/api/validation", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/validation")>(
    "@/lib/api/validation"
  );
  return {
    ...actual,
    getUpload: vi.fn(),
    confirmDetection: vi.fn(),
    rejectDetection: vi.fn(),
    confirmAll: vi.fn(),
    subscribeToUploadEvents: vi.fn(),
  };
});

const UPLOAD_ID = "11111111-1111-1111-1111-111111111111";
const DETECTION_ID = "22222222-2222-2222-2222-222222222222";
const CARD_ID = "33333333-3333-3333-3333-333333333333";

function uploadDetail(overrides: Partial<Awaited<ReturnType<typeof getUpload>>> = {}) {
  return {
    upload_id: UPLOAD_ID,
    status: "processed",
    job_status: "succeeded" as const,
    job_error: null,
    detections: [
      {
        id: DETECTION_ID,
        reading_order: 0,
        status: "pending" as const,
        crop_url: `/uploads/${UPLOAD_ID}/detections/${DETECTION_ID}/crop`,
        extraction: {
          name: "Sarmuraï",
          name_confidence: 0.95,
          number: "1",
          number_confidence: 0.95,
          total: 198,
          total_confidence: 0.9,
          set_code: null,
          set_code_confidence: 0,
          language: "fr",
          language_confidence: 0.9,
          hp: 60,
          hp_confidence: 0.8,
          card_type: "Pokémon",
          card_type_confidence: 0.7,
          variant: "normal",
          variant_confidence: 0.6,
        },
        candidates: [
          {
            card_id: CARD_ID,
            set_id: "set-1",
            name: "Sarmuraï",
            number: "1",
            set_name: "Écarlate et Violet",
            set_code: "sv01",
            catalog_score: 1,
            combined_score: 0.95,
            preselected: true,
          },
        ],
        condition: null,
        identification_method: "ia" as const,
      },
    ],
    ...overrides,
  };
}

describe("ValidationView", () => {
  beforeEach(() => {
    vi.mocked(getUpload).mockReset();
    vi.mocked(confirmDetection).mockReset();
    vi.mocked(confirmAll).mockReset();
    vi.mocked(subscribeToUploadEvents).mockReset();
    vi.mocked(subscribeToUploadEvents).mockReturnValue(() => {});
    push.mockReset();
  });

  it("affiche la carte détectée avec son candidat présélectionné", async () => {
    vi.mocked(getUpload).mockResolvedValue(uploadDetail());

    render(<ValidationView uploadIds={[UPLOAD_ID]} />);

    expect((await screen.findAllByText(/Sarmuraï/)).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /valider/i })).toBeInTheDocument();
  });

  it("valide la carte active au clic sur « Valider » et envoie le candidat sélectionné", async () => {
    vi.mocked(getUpload).mockResolvedValue(uploadDetail());
    vi.mocked(confirmDetection).mockResolvedValue({
      detection_id: DETECTION_ID,
      status: "validated",
      collection_item_ids: ["item-1"],
    });

    const user = userEvent.setup();
    render(<ValidationView uploadIds={[UPLOAD_ID]} />);
    await screen.findAllByText(/Sarmuraï/);

    await user.click(screen.getByRole("button", { name: /valider/i }));

    await waitFor(() =>
      expect(confirmDetection).toHaveBeenCalledWith(
        DETECTION_ID,
        expect.objectContaining({ card_id: CARD_ID, language: "fr", variant: "normal", quantity: 1 })
      )
    );
    expect(await screen.findByText("validée")).toBeInTheDocument();
  });

  it("valide la carte active au clavier avec Entrée", async () => {
    vi.mocked(getUpload).mockResolvedValue(uploadDetail());
    vi.mocked(confirmDetection).mockResolvedValue({
      detection_id: DETECTION_ID,
      status: "validated",
      collection_item_ids: ["item-1"],
    });

    const user = userEvent.setup();
    render(<ValidationView uploadIds={[UPLOAD_ID]} />);
    await screen.findAllByText(/Sarmuraï/);

    await user.keyboard("{Enter}");

    await waitFor(() => expect(confirmDetection).toHaveBeenCalledWith(DETECTION_ID, expect.anything()));
  });

  it("« Tout ajouter » confirme chaque envoi puis va vers la collection", async () => {
    vi.mocked(getUpload).mockResolvedValue(uploadDetail());
    vi.mocked(confirmAll).mockResolvedValue({
      upload_id: UPLOAD_ID,
      confirmed: [DETECTION_ID],
      skipped: [],
    });

    const user = userEvent.setup();
    render(<ValidationView uploadIds={[UPLOAD_ID]} />);
    await screen.findAllByText(/Sarmuraï/);

    await user.click(screen.getByRole("button", { name: /ajouter les 1 carte/i }));

    await waitFor(() => expect(confirmAll).toHaveBeenCalledWith(UPLOAD_ID));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/collection"));
  });

  it("affiche le message du fournisseur IA quand le job de reconnaissance échoue sans détection (régression pbm-hotfix-reconnaissance)", async () => {
    vi.mocked(getUpload).mockResolvedValue(
      uploadDetail({
        job_status: "failed",
        job_error:
          "Le fournisseur IA a refusé la requête (400) : output_config.format.schema: For " +
          "'number' type, properties maximum, minimum are not supported",
        detections: [],
      })
    );

    render(<ValidationView uploadIds={[UPLOAD_ID]} />);

    expect(await screen.findByText(/La reconnaissance a échoué/)).toBeInTheDocument();
    expect(
      await screen.findByText(/properties maximum, minimum are not supported/)
    ).toBeInTheDocument();
    // Jamais l'écran "rien à valider" qui a fait perdre du temps de diagnostic en PROD : il
    // laisse croire qu'aucune photo n'a été envoyée, alors que la reconnaissance a réellement
    // été tentée et a échoué.
    expect(screen.queryByText("Rien à valider")).not.toBeInTheDocument();
  });
});
