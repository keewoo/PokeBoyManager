import type { Metadata } from "next";

import { DeckBuilderView } from "./deck-builder-view";

/** Titre d'onglet de l'écran constructeur de deck. */
export const metadata: Metadata = {
  title: "Constructeur de deck",
};

/**
 * Page serveur du constructeur de deck (`/jeu/decks/{id}`). Attend `params` (asynchrone en
 * Next 15) et passe l'identifiant au composant client `DeckBuilderView`, qui porte toute
 * l'interaction.
 */
export default async function DeckBuilderPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <DeckBuilderView deckId={id} />;
}
