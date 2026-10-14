import type { Metadata } from "next";

import { NotificationsView } from "./notifications-view";

/** Titre d'onglet de l'écran des notifications du jeu. */
export const metadata: Metadata = {
  title: "Notifications",
};

/**
 * Écran des notifications (`/jeu/notifications`). La route est déjà protégée par session
 * (`src/middleware.ts`, préfixe `/jeu`) ; le droit d'accès au jeu (D11) est contrôlé dans
 * `NotificationsView`, qui rend une page inexistante à un compte non invité — le serveur, lui,
 * répond déjà 404 sur toutes les routes du jeu.
 */
export default function NotificationsPage() {
  return <NotificationsView />;
}
