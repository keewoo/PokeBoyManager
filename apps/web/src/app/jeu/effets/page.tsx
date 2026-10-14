import type { Metadata } from "next";

import { EffetsView } from "./effets-view";

/** Titre d'onglet de la galerie d'effets. */
export const metadata: Metadata = {
  title: "Les effets d'attaque",
};

/**
 * Galerie des effets d'attaque typés (`/jeu/effets`, lot `j-anim-attaques-typees`).
 *
 * Elle existe pour que JF et Aymeric puissent **valider le rendu** des onze types sans avoir à
 * réunir en partie un Pokémon de chaque type avec la bonne faiblesse et un pile ou face perdu. La
 * route est déjà protégée par session (`src/middleware.ts`, préfixe `/jeu`) ; le droit d'accès au
 * jeu (D11) est contrôlé dans `EffetsView`, qui rend une page inexistante à un compte non invité.
 */
export default function EffetsPage() {
  return <EffetsView />;
}
