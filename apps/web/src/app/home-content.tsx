import { DashboardView } from "@/components/dashboard/dashboard-view";
import { LandingPage } from "@/components/landing/landing-page";

// Séparé de `page.tsx` (Server Component, `next/headers`) pour rester testable en dehors du
// runtime Next.js — même patron que `middleware.ts`, qui isole sa logique pure de la glu du
// framework (voir `src/__tests__/middleware.test.ts`).
export function HomeContent({ hasSession }: { hasSession: boolean }) {
  return hasSession ? <DashboardView /> : <LandingPage />;
}
