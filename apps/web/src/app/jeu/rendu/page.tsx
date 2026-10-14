import type { Metadata } from "next";

import { RenduView } from "./rendu-view";

/** Titre d'onglet de l'écran « Mes cartes en jeu ». */
export const metadata: Metadata = {
  title: "Mes cartes en jeu",
};

/**
 * Écran de rendu des cartes (`/jeu/rendu`, lot `j-rendu-carte`). La route est déjà protégée par
 * session (`src/middleware.ts`, préfixe `/jeu`) ; le droit d'accès au jeu (D11) est contrôlé dans
 * `RenduView`, qui rend une page inexistante à un compte non invité.
 */
export default function RenduPage() {
  return <RenduView />;
}
