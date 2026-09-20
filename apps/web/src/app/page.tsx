import type { Metadata } from "next";
import { cookies } from "next/headers";

import { getSessionCookieName } from "@/lib/config";
import { getFeaturedCards } from "@/lib/api/featured-cards";

import { HomeContent } from "./home-content";

const TITLE = "PokeBoyManager — Photographie ta collection, suis sa valeur";
const DESCRIPTION =
  "Photographie ton classeur de cartes Pokémon : l'IA de ton choix identifie chaque carte et PokeBoyManager suit sa valeur jour après jour. Espace privé, ta clé IA reste à toi.";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    type: "website",
    locale: "fr_FR",
  },
  twitter: {
    card: "summary",
    title: TITLE,
    description: DESCRIPTION,
  },
};

export default async function HomePage() {
  const cookieStore = await cookies();
  const hasSession = cookieStore.has(getSessionCookieName());
  // Inutile pour un visiteur déjà connecté (le tableau de bord ne montre pas cette
  // démonstration) : ne récupérer les neuf cartes que lorsqu'elles seront réellement affichées.
  const featuredCards = hasSession ? [] : await getFeaturedCards();
  return <HomeContent hasSession={hasSession} featuredCards={featuredCards} />;
}
