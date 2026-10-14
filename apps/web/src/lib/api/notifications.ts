import { apiGet, apiJson } from "@/lib/api/client";

// Contrats miroir de `apps/api/src/pbm_api/routers/notifications.py` (lot `j-notifications-jeu`).
// Rien de secret n'y transite : une notification est un **libellé**, pas une vue de partie — elle
// porte un genre, la partie concernée et un contexte d'affichage, jamais une main ni une pioche.
//
// Il n'existe volontairement **aucune fonction d'émission** : les notifications naissent d'un
// événement du jeu (invitation, appariement, coup, reconnexion), jamais d'une demande du client.
// Si ce fichier gagnait un `createNotification`, n'importe qui pourrait se fabriquer une sonnerie
// — ou en fabriquer une à l'autre, en contournant ses réglages et les plafonds.

/** Quelqu'un vous invite à jouer. Seul genre sans partie, et seul genre relayé par e-mail. */
export const NOTIF_INVITATION_RECUE = "invitation_recue";
/** La file d'attente vous a trouvé un adversaire : la partie existe. */
export const NOTIF_ADVERSAIRE_TROUVE = "adversaire_trouve";
/** C'est à vous de jouer. */
export const NOTIF_TON_TOUR = "ton_tour";
/** Votre budget de temps descend sous la minute. */
export const NOTIF_TEMPS_BIENTOT_ECOULE = "temps_bientot_ecoule";
/** L'adversaire déconnecté est revenu : les horloges reprennent. */
export const NOTIF_ADVERSAIRE_REVENU = "adversaire_revenu";
/** La partie s'est terminée par forfait (abandon ou désertion) : vous avez gagné. */
export const NOTIF_PARTIE_FORFAIT = "partie_forfait";

/**
 * Une notification telle que le serveur la sert. `silencieuse` dit « arrivée pendant le silence
 * nocturne » : on l'affiche dans la liste **sans** la sonner ni l'animer — c'est la différence
 * entre « tu l'as manquée » et « on ne t'a pas réveillé ».
 */
export type Notification = {
  id: string;
  genre: string;
  game_id: string | null;
  donnees: Record<string, unknown>;
  silencieuse: boolean;
  created_at: string;
  lue_at: string | null;
};

/** La liste et le compte des non lues — le second alimente le badge de la navigation. */
export type ListeNotifications = {
  notifications: Notification[];
  nb_non_lues: number;
};

/**
 * Les réglages du compte, plus ce qui est **imposé** par le produit. `plafond_par_partie` et
 * `plafond_par_genre` ne se règlent pas (ce sont des garde-fous contre le harcèlement) : ils sont
 * publiés pour que l'écran puisse expliquer pourquoi une notification n'est pas arrivée.
 */
export type ReglagesNotifications = {
  genres_connus: string[];
  genres_desactives: string[];
  silence_actif: boolean;
  silence_debut: string;
  silence_fin: string;
  fuseau: string;
  relais_email_invitation: boolean;
  relais_push: boolean;
  plafond_par_partie: number;
  plafond_par_genre: Record<string, number>;
};

/** Modification **partielle** des réglages : seuls les champs fournis changent côté serveur. */
export type PatchReglagesNotifications = Partial<
  Pick<
    ReglagesNotifications,
    | "genres_desactives"
    | "silence_actif"
    | "silence_debut"
    | "silence_fin"
    | "fuseau"
    | "relais_email_invitation"
    | "relais_push"
  >
>;

/** Mes notifications, les plus récentes d'abord, et le compte de mes non lues. */
export function listNotifications(nonLues = false): Promise<ListeNotifications> {
  return apiGet<ListeNotifications>(`/jeu/notifications${nonLues ? "?non_lues=true" : ""}`);
}

/** Marque une de mes notifications comme lue (celle d'un autre compte répond 404). */
export function markNotificationRead(notificationId: string): Promise<Notification> {
  return apiJson<Notification>("POST", `/jeu/notifications/${notificationId}/lue`);
}

/** Marque toutes mes notifications comme lues et rend la liste à jour. */
export function markAllNotificationsRead(): Promise<ListeNotifications> {
  return apiJson<ListeNotifications>("POST", "/jeu/notifications/lues");
}

/** Mes réglages de notification (les défauts si je n'y ai jamais touché). */
export function getNotificationSettings(): Promise<ReglagesNotifications> {
  return apiGet<ReglagesNotifications>("/jeu/notifications/reglages");
}

/** Modifie mes réglages (partiellement) et rend l'état complet qui en résulte. */
export function updateNotificationSettings(
  patch: PatchReglagesNotifications
): Promise<ReglagesNotifications> {
  return apiJson<ReglagesNotifications>("PATCH", "/jeu/notifications/reglages", patch);
}

// Libellés d'interrupteur, par genre. Un genre inconnu de cette table est **affiché quand même**
// (sous son identifiant) : mieux vaut un libellé brut qu'un réglage invisible — un interrupteur
// manquant est un réglage que le joueur ne peut pas atteindre.
const LIBELLES_GENRE: Record<string, string> = {
  [NOTIF_INVITATION_RECUE]: "Invitation reçue",
  [NOTIF_ADVERSAIRE_TROUVE]: "Adversaire trouvé",
  [NOTIF_TON_TOUR]: "C'est ton tour",
  [NOTIF_TEMPS_BIENTOT_ECOULE]: "Il te reste une minute",
  [NOTIF_ADVERSAIRE_REVENU]: "L'adversaire est revenu",
  [NOTIF_PARTIE_FORFAIT]: "Partie terminée par forfait",
};

/** Le nom lisible d'un genre, pour l'étiquette de son interrupteur. */
export function libelleGenre(genre: string): string {
  return LIBELLES_GENRE[genre] ?? genre;
}

function pseudoDe(notification: Notification): string {
  const pseudo = notification.donnees?.pseudo;
  return typeof pseudo === "string" && pseudo.length > 0 ? pseudo : "Un joueur";
}

/**
 * La **phrase** d'une notification, fabriquée ici et pas côté serveur.
 *
 * Le serveur stocke un genre et un contexte (`donnees`), jamais un texte : une phrase changerait
 * de formulation — ou de langue — sans migration, et une base pleine de phrases figées est une
 * base qu'on ne peut plus reformuler. L'écran est le bon endroit pour le dire.
 */
export function phraseNotification(notification: Notification): string {
  switch (notification.genre) {
    case NOTIF_INVITATION_RECUE:
      return `${pseudoDe(notification)} t'invite à jouer.`;
    case NOTIF_ADVERSAIRE_TROUVE:
      return `Adversaire trouvé : ${pseudoDe(notification)}. La partie t'attend !`;
    case NOTIF_TON_TOUR:
      return "C'est ton tour de jouer.";
    case NOTIF_TEMPS_BIENTOT_ECOULE: {
      const budget = notification.donnees?.budget_s;
      const secondes = typeof budget === "number" ? budget : null;
      return secondes === null
        ? "Il te reste moins d'une minute : à toi de jouer !"
        : `Il te reste ${secondes} secondes : à toi de jouer !`;
    }
    case NOTIF_ADVERSAIRE_REVENU:
      return `${pseudoDe(notification)} est revenu : la partie reprend.`;
    case NOTIF_PARTIE_FORFAIT:
      return notification.donnees?.raison === "desertion"
        ? "Ton adversaire n'est pas revenu : tu gagnes par forfait."
        : "Ton adversaire a abandonné : tu gagnes la partie.";
    default:
      // Un genre que cette version de l'écran ne connaît pas (serveur plus récent) : on le montre
      // tel quel plutôt que de le masquer. Une notification invisible serait une notification
      // perdue — et le joueur n'aurait aucun moyen de savoir qu'il lui manque quelque chose.
      return `Nouvelle notification (${notification.genre}).`;
  }
}
