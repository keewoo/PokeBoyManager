import { DashboardView } from "@/components/dashboard/dashboard-view";
import { LandingPage } from "@/components/landing/landing-page";
import type { FeaturedCard } from "@/lib/api/featured-cards";

// Séparé de `page.tsx` (Server Component, `next/headers`) pour rester testable en dehors du
// runtime Next.js — même patron que `middleware.ts`, qui isole sa logique pure de la glu du
// framework (voir `src/__tests__/middleware.test.ts`). `featuredCards` est récupéré une seule
// fois par `page.tsx` (seul point de récupération serveur de l'accueil) : `LandingPage` et ses
// enfants restent des composants synchrones, testables avec `@testing-library/react`.
/**
 * Aiguille l'accueil selon l'état de session : `DashboardView` pour un visiteur
 * connecté, sinon la vitrine `LandingPage`. Composant synchrone et pur — il ne
 * décide de rien et ne récupère aucune donnée lui-même : `hasSession` et
 * `featuredCards` lui sont fournis par le Server Component `page.tsx`.
 */
export function HomeContent({
  hasSession,
  featuredCards,
}: {
  hasSession: boolean;
  featuredCards: FeaturedCard[];
}) {
  return hasSession ? <DashboardView /> : <LandingPage featuredCards={featuredCards} />;
}
