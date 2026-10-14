import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { NotificationsView } from "@/app/jeu/notifications/notifications-view";
import * as notificationsApi from "@/lib/api/notifications";
import type { Notification, ReglagesNotifications } from "@/lib/api/notifications";
import * as profileApi from "@/lib/api/profile";
import type { ProfileResponse } from "@/lib/api/profile";
import * as navigation from "next/navigation";

// On préserve les constantes de genre et les fabricants de phrase (`phraseNotification`,
// `libelleGenre`) : l'écran les utilise pour composer ses libellés, les remplacer ne testerait
// plus rien d'utile. Seuls les appels réseau sont substitués.
vi.mock("next/navigation", () => ({
  notFound: vi.fn(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));
vi.mock("@/lib/api/profile", () => ({ getProfile: vi.fn() }));
vi.mock("@/lib/api/notifications", async (orig) => ({
  ...(await orig<typeof notificationsApi>()),
  listNotifications: vi.fn(),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  getNotificationSettings: vi.fn(),
  updateNotificationSettings: vi.fn(),
}));

const profile = vi.mocked(profileApi);
const api = vi.mocked(notificationsApi);
const notFound = vi.mocked(navigation.notFound);

function makeProfile(gameAccess: boolean): ProfileResponse {
  return {
    id: "u-1",
    email: "joueur@example.com",
    pseudo: "joueur",
    game_access: gameAccess,
  } as unknown as ProfileResponse;
}

function makeNotification(partial: Partial<Notification> = {}): Notification {
  return {
    id: "n-1",
    genre: notificationsApi.NOTIF_INVITATION_RECUE,
    game_id: null,
    donnees: { pseudo: "alice" },
    silencieuse: false,
    created_at: "2026-10-13T12:00:00Z",
    lue_at: null,
    ...partial,
  };
}

function makeReglages(partial: Partial<ReglagesNotifications> = {}): ReglagesNotifications {
  return {
    genres_connus: [
      notificationsApi.NOTIF_INVITATION_RECUE,
      notificationsApi.NOTIF_TON_TOUR,
    ],
    genres_desactives: [],
    silence_actif: true,
    silence_debut: "21:00:00",
    silence_fin: "07:00:00",
    fuseau: "Europe/Paris",
    relais_email_invitation: true,
    relais_push: true,
    plafond_par_partie: 10,
    plafond_par_genre: { [notificationsApi.NOTIF_TON_TOUR]: 4 },
    ...partial,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  profile.getProfile.mockResolvedValue(makeProfile(true));
  api.listNotifications.mockResolvedValue({ notifications: [], nb_non_lues: 0 });
  api.getNotificationSettings.mockResolvedValue(makeReglages());
});

describe("NotificationsView", () => {
  it("rend une page inexistante à un compte sans accès au jeu (D11)", async () => {
    profile.getProfile.mockResolvedValue(makeProfile(false));
    render(<NotificationsView />);
    await waitFor(() => expect(notFound).toHaveBeenCalled());
  });

  it("affiche la phrase de chaque notification reçue", async () => {
    api.listNotifications.mockResolvedValue({
      notifications: [
        makeNotification(),
        makeNotification({
          id: "n-2",
          genre: notificationsApi.NOTIF_TON_TOUR,
          game_id: "g-1",
          donnees: {},
        }),
      ],
      nb_non_lues: 2,
    });
    render(<NotificationsView />);
    expect(await screen.findByText("alice t'invite à jouer.")).toBeInTheDocument();
    expect(screen.getByText("C'est ton tour de jouer.")).toBeInTheDocument();
  });

  it("dit qu'une notification est arrivée pendant le silence nocturne", async () => {
    // Sans cette mention, le joueur croirait à une panne alors qu'il a demandé le silence.
    api.listNotifications.mockResolvedValue({
      notifications: [makeNotification({ silencieuse: true })],
      nb_non_lues: 1,
    });
    render(<NotificationsView />);
    expect(await screen.findByText(/silence nocturne/)).toBeInTheDocument();
  });

  it("annonce l'absence de notification sans prétendre à une erreur", async () => {
    render(<NotificationsView />);
    expect(await screen.findByText("Rien à signaler")).toBeInTheDocument();
  });

  it("dit que le chargement a échoué plutôt que d'afficher une liste vide", async () => {
    // Un écran vide muet ferait passer une panne pour « rien de neuf » — le repli interdit.
    api.listNotifications.mockRejectedValue(new Error("réseau coupé"));
    render(<NotificationsView />);
    expect(await screen.findByText(/Chargement impossible/)).toBeInTheDocument();
  });

  it("marque une notification lue et recharge", async () => {
    api.listNotifications.mockResolvedValue({
      notifications: [makeNotification()],
      nb_non_lues: 1,
    });
    api.markNotificationRead.mockResolvedValue(makeNotification({ lue_at: "2026-10-13T13:00:00Z" }));
    render(<NotificationsView />);
    await userEvent.click(await screen.findByRole("button", { name: "Marquer comme lue" }));
    await waitFor(() => expect(api.markNotificationRead).toHaveBeenCalledWith("n-1"));
  });

  it("marque tout lu en un geste", async () => {
    api.listNotifications.mockResolvedValue({
      notifications: [makeNotification()],
      nb_non_lues: 1,
    });
    api.markAllNotificationsRead.mockResolvedValue({ notifications: [], nb_non_lues: 0 });
    render(<NotificationsView />);
    await userEvent.click(await screen.findByRole("button", { name: "Tout marquer comme lu" }));
    await waitFor(() => expect(api.markAllNotificationsRead).toHaveBeenCalled());
  });

  it("offre un interrupteur par type, et ne coupe que celui-là", async () => {
    // Le critère « chaque type est désactivable séparément », vu de l'écran : décocher
    // « C'est ton tour » n'envoie que ce genre dans `genres_desactives`.
    api.updateNotificationSettings.mockResolvedValue(
      makeReglages({ genres_desactives: [notificationsApi.NOTIF_TON_TOUR] })
    );
    render(<NotificationsView />);
    const interrupteur = await screen.findByLabelText("C'est ton tour");
    expect(interrupteur).toBeChecked();
    await userEvent.click(interrupteur);
    await waitFor(() =>
      expect(api.updateNotificationSettings).toHaveBeenCalledWith({
        genres_desactives: [notificationsApi.NOTIF_TON_TOUR],
      })
    );
    expect(await screen.findByLabelText("C'est ton tour")).not.toBeChecked();
    expect(screen.getByLabelText("Invitation reçue")).toBeChecked();
  });

  it("coche les interrupteurs selon ce que le serveur dit être coupé", async () => {
    api.getNotificationSettings.mockResolvedValue(
      makeReglages({ genres_desactives: [notificationsApi.NOTIF_INVITATION_RECUE] })
    );
    render(<NotificationsView />);
    expect(await screen.findByLabelText("Invitation reçue")).not.toBeChecked();
    expect(screen.getByLabelText("C'est ton tour")).toBeChecked();
  });

  it("règle le silence nocturne et affiche le plafond imposé", async () => {
    api.updateNotificationSettings.mockResolvedValue(makeReglages({ silence_actif: false }));
    render(<NotificationsView />);
    expect(await screen.findByTestId("plafond-partie")).toHaveTextContent("10");
    await userEvent.click(screen.getByLabelText("Silence nocturne"));
    await waitFor(() =>
      expect(api.updateNotificationSettings).toHaveBeenCalledWith({ silence_actif: false })
    );
  });

  it("coupe le relais e-mail de l'invitation sans toucher au reste", async () => {
    api.updateNotificationSettings.mockResolvedValue(
      makeReglages({ relais_email_invitation: false })
    );
    render(<NotificationsView />);
    await userEvent.click(await screen.findByLabelText("E-mail pour une invitation"));
    await waitFor(() =>
      expect(api.updateNotificationSettings).toHaveBeenCalledWith({
        relais_email_invitation: false,
      })
    );
  });

  it("dit qu'un réglage n'a pas été enregistré quand le serveur refuse", async () => {
    api.updateNotificationSettings.mockRejectedValue(new Error("refus"));
    render(<NotificationsView />);
    await userEvent.click(await screen.findByLabelText("Silence nocturne"));
    expect(await screen.findByText(/Réglage non enregistré/)).toBeInTheDocument();
  });
});

describe("phraseNotification", () => {
  it("nomme le genre inconnu plutôt que de masquer la notification", () => {
    // Un serveur plus récent peut servir un genre que cette version ignore : la montrer telle
    // quelle vaut mieux qu'une notification invisible, que le joueur ne saurait pas lui manquer.
    const phrase = notificationsApi.phraseNotification(
      makeNotification({ genre: "sonnerie_future" })
    );
    expect(phrase).toContain("sonnerie_future");
  });

  it("distingue l'abandon de la désertion dans la fin par forfait", () => {
    const desertion = notificationsApi.phraseNotification(
      makeNotification({ genre: notificationsApi.NOTIF_PARTIE_FORFAIT, donnees: { raison: "desertion" } })
    );
    const abandon = notificationsApi.phraseNotification(
      makeNotification({ genre: notificationsApi.NOTIF_PARTIE_FORFAIT, donnees: { raison: "abandon" } })
    );
    expect(desertion).toContain("n'est pas revenu");
    expect(abandon).toContain("abandonné");
  });

  it("se passe d'un pseudo manquant sans afficher « undefined »", () => {
    const phrase = notificationsApi.phraseNotification(
      makeNotification({ genre: notificationsApi.NOTIF_ADVERSAIRE_TROUVE, donnees: {} })
    );
    expect(phrase).toContain("Un joueur");
    expect(phrase).not.toContain("undefined");
  });

  it("annonce les secondes restantes quand le serveur les donne", () => {
    const phrase = notificationsApi.phraseNotification(
      makeNotification({
        genre: notificationsApi.NOTIF_TEMPS_BIENTOT_ECOULE,
        donnees: { budget_s: 42 },
      })
    );
    expect(phrase).toContain("42");
  });
});
