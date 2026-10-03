import type { Metadata } from "next";
import { cookies } from "next/headers";

import { getSessionCookieName } from "@/lib/config";
import { getFeaturedCards } from "@/lib/api/featured-cards";

import { HomeContent } from "./home-content";

const TITLE = "PokéBoy — Photographie ta collection, suis sa valeur";
const DESCRIPTION =
  "Photographie ton classeur de cartes Pokémon : l'IA de ton choix identifie chaque carte et PokéBoy suit sa valeur jour après jour. Espace privé, ta clé IA reste à toi.";

/**
 * Métadonnées de l'accueil (titre, description, Open Graph, Twitter) : elles décrivent la landing
 * visiteur, premier point d'entrée référencé et partagé. Fixes, car rendues aussi pour un visiteur
 * connecté — le titre orienté « découverte » reste acceptable et évite une génération dynamique.
 */
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

/**
 * Route `/` (Server Component). Lit le cookie de session côté serveur (jamais un état client après
 * montage, pour éviter un flash de l'accueil visiteur) et délègue l'affichage à `HomeContent` :
 * tableau de bord si connecté, landing sinon. Seul point de récupération serveur de l'accueil —
 * les cartes vedettes (`getFeaturedCards`) ne sont chargées que pour un visiteur, le tableau de
 * bord ne les montrant pas.
 */
export default async function HomePage() {
  const cookieStore = await cookies();
  const hasSession = cookieStore.has(getSessionCookieName());
  // Inutile pour un visiteur déjà connecté (le tableau de bord ne montre pas cette
  // démonstration) : ne récupérer les neuf cartes que lorsqu'elles seront réellement affichées.
  const featuredCards = hasSession ? [] : await getFeaturedCards();
  return <HomeContent hasSession={hasSession} featuredCards={featuredCards} />;
}
