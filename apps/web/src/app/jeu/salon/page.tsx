import type { Metadata } from "next";

import { SalonView } from "./salon-view";

/** Titre d'onglet du salon de jeu. */
export const metadata: Metadata = {
  title: "Salon de jeu",
};

/**
 * Point d'entrée du jeu (`/jeu/salon`). La route est déjà protégée par session (`src/middleware.ts`,
 * préfixe `/jeu`) ; le droit d'accès au jeu (D11) est contrôlé dans `SalonView`, qui rend une page
 * inexistante à un compte non invité — le serveur, lui, répond déjà 404 sur toutes les routes du
 * jeu.
 */
export default function SalonPage() {
  return <SalonView />;
}
