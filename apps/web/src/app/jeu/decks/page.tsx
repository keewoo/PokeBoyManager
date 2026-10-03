import type { Metadata } from "next";

import { DecksListView } from "./decks-list-view";

/** Titre d'onglet de la liste des decks. */
export const metadata: Metadata = {
  title: "Mes decks",
};

/** Page de la liste des decks (`/jeu/decks`) : délègue tout au composant client `DecksListView`. */
export default function DecksPage() {
  return <DecksListView />;
}
