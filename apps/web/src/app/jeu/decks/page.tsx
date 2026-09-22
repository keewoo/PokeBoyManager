import type { Metadata } from "next";

import { DecksListView } from "./decks-list-view";

export const metadata: Metadata = {
  title: "Mes decks",
};

export default function DecksPage() {
  return <DecksListView />;
}
