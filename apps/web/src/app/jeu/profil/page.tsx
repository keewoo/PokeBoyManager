import type { Metadata } from "next";

import { ProfilJeuView } from "./profil-view";

/** Titre d'onglet de l'écran « Mon profil de joueur ». */
export const metadata: Metadata = {
  title: "Mon profil de joueur",
};

/**
 * Vitrine du profil de joueur (`/jeu/profil`, lot `j-profil-jeu`). La route est déjà protégée par
 * session (`src/middleware.ts`, préfixe `/jeu`) ; le droit d'accès au jeu (D11) est contrôlé dans
 * `ProfilJeuView`, qui rend une page inexistante à un compte non invité.
 */
export default function ProfilJeuPage() {
  return <ProfilJeuView />;
}
