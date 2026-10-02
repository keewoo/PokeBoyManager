import type { Metadata } from "next";

import { PartieView } from "./partie-view";

export const metadata: Metadata = {
  title: "Partie",
};

/**
 * Le plateau d'une partie (`/jeu/parties/{id}`, lot `j-plateau-layout`). La route est déjà protégée
 * par session (`src/middleware.ts`, préfixe `/jeu`) ; le droit d'accès au jeu (D11) et la
 * participation à CETTE partie sont contrôlés dans `PartieView` — le serveur, lui, répond déjà 404
 * sur une partie dont le joueur n'est pas participant.
 *
 * `params` est asynchrone (Next 15) : on l'attend ici pour passer l'identifiant au composant client.
 */
export default async function PartiePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <PartieView gameId={id} />;
}
