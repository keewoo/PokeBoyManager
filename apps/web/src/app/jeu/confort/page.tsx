import type { Metadata } from "next";

import { ConfortView } from "./confort-view";

/** Titre d'onglet de l'écran « Confort de jeu ». */
export const metadata: Metadata = {
  title: "Confort de jeu",
};

/**
 * Écran de confort et d'accessibilité (`/jeu/confort`, lot `j-accessibilite-jeu`). La route est déjà
 * protégée par session (`src/middleware.ts`, préfixe `/jeu`) ; le droit d'accès au jeu (D11) est
 * contrôlé dans `ConfortView`, qui rend une page inexistante à un compte non invité.
 */
export default function ConfortPage() {
  return <ConfortView />;
}
