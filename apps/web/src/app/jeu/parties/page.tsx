import type { Metadata } from "next";

import { MesPartiesView } from "./mes-parties-view";

/** Titre d'onglet de l'écran « Mes parties ». */
export const metadata: Metadata = {
  title: "Mes parties",
};

/**
 * Écran « Mes parties » (`/jeu/parties`) — historique et statistiques (lot `j-stats-joueur`).
 *
 * La route est déjà protégée par session (`src/middleware.ts`, préfixe `/jeu`) ; le droit d'accès
 * au jeu (D11) est contrôlé dans `MesPartiesView`, qui rend une page inexistante à un compte non
 * invité — le serveur, lui, répond déjà 404 sur toutes les routes du jeu.
 *
 * Ne masque pas `/jeu/parties/[id]` : Next.js sert le segment dynamique pour tout identifiant, et
 * cette page pour le chemin exact.
 */
export default function MesPartiesPage() {
  return <MesPartiesView />;
}
