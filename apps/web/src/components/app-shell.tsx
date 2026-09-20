"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { ThemeToggle } from "@/components/theme-toggle";
import { logout } from "@/lib/api/auth";
import { cn } from "@/lib/utils";

// Liens réservés aux connectés : les proposer à un visiteur (« Profil » sur la page d'accueil
// sans session) l'envoyait sur la garde de route, qui le renvoyait vers /connexion — le menu
// mentait sur l'état réel (correctif `pbm-hotfix-fallback-ia-confiance`).
const NAV_LINKS = [
  { href: "/", label: "Accueil", requiresSession: false },
  { href: "/collection", label: "Collection", requiresSession: true },
  { href: "/ajouter", label: "Ajouter", requiresSession: true },
  { href: "/profil", label: "Profil", requiresSession: true },
];

export function AppShell({
  hasSession = false,
  children,
}: {
  hasSession?: boolean;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  // L'état vient du serveur (cookie de session lu par `app/layout.tsx`, même source que la
  // garde de route `middleware.ts`) : jamais deviné côté client — le cookie est httpOnly. La
  // connexion (`connexion-form.tsx`) fait déjà `router.refresh()`, qui re-rend le layout et
  // donc cet en-tête ; la déconnexion ci-dessous fait de même.
  async function handleLogout() {
    if (isLoggingOut) return;
    setIsLoggingOut(true);
    try {
      await logout();
    } finally {
      setIsLoggingOut(false);
      router.push("/");
      router.refresh();
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="flex flex-wrap items-center gap-3 border-b border-border bg-card px-5 py-3">
        <Link href="/" className="flex items-center gap-2.5 font-pixel text-[11px] text-foreground">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-screen">
            <span className="h-3 w-3 rounded-full bg-primary" aria-hidden />
          </span>
          PokeBoyManager
        </Link>

        <nav className="ml-2 flex flex-wrap gap-1" aria-label="Navigation principale">
          {NAV_LINKS.filter((link) => hasSession || !link.requiresSession).map((link) => {
            const isActive = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "rounded-md px-2.5 py-1.5 text-sm font-medium text-muted-foreground hover:text-foreground",
                  isActive && "bg-secondary font-semibold text-foreground"
                )}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-3">
          {hasSession ? (
            <button
              type="button"
              onClick={handleLogout}
              disabled={isLoggingOut}
              className="text-sm font-medium text-muted-foreground hover:text-foreground disabled:opacity-60"
            >
              {isLoggingOut ? "Déconnexion…" : "Déconnexion"}
            </button>
          ) : (
            <>
              <Link
                href="/connexion"
                className="text-sm font-medium text-muted-foreground hover:text-foreground"
              >
                Connexion
              </Link>
              <Link
                href="/inscription"
                className="text-sm font-medium text-muted-foreground hover:text-foreground"
              >
                Inscription
              </Link>
            </>
          )}
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-8">{children}</main>
    </div>
  );
}
