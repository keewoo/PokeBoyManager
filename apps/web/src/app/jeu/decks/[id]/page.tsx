import type { Metadata } from "next";

import { DeckBuilderView } from "./deck-builder-view";

export const metadata: Metadata = {
  title: "Constructeur de deck",
};

export default async function DeckBuilderPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <DeckBuilderView deckId={id} />;
}
