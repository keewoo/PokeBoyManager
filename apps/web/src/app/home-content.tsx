import { DashboardView } from "@/components/dashboard/dashboard-view";
import { LandingPage } from "@/components/landing/landing-page";
import type { FeaturedCard } from "@/lib/api/featured-cards";

// Séparé de `page.tsx` (Server Component, `next/headers`) pour rester testable en dehors du
// runtime Next.js — même patron que `middleware.ts`, qui isole sa logique pure de la glu du
// framework (voir `src/__tests__/middleware.test.ts`). `featuredCards` est récupéré une seule
// fois par `page.tsx` (seul point de récupération serveur de l'accueil) : `LandingPage` et ses
// enfants restent des composants synchrones, testables avec `@testing-library/react`.
export function HomeContent({
  hasSession,
  featuredCards,
}: {
  hasSession: boolean;
  featuredCards: FeaturedCard[];
}) {
  return hasSession ? <DashboardView /> : <LandingPage featuredCards={featuredCards} />;
}
