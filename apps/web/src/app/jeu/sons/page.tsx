import type { Metadata } from "next";

import { SonsView } from "./sons-view";

/** Titre d'onglet de l'écran « Les sons du jeu ». */
export const metadata: Metadata = {
  title: "Les sons du jeu",
};

/**
 * Écran des sons (`/jeu/sons`, lot `j-son`). La route est déjà protégée par session
 * (`src/middleware.ts`, préfixe `/jeu`) ; le droit d'accès au jeu (D11) est contrôlé dans
 * {@link SonsView}, qui rend une page inexistante à un compte non invité.
 */
export default function SonsPage() {
  return <SonsView />;
}
