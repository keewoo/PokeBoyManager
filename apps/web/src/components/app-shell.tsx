"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { ThemeToggle } from "@/components/theme-toggle";
import { logout } from "@/lib/api/auth";
import { cn } from "@/lib/utils";

type NavLink = { href: string; label: string };

// Visiteur : présentation + Connexion/Inscription (jamais Collection/Ajouter/Profil, des pages
// qui lui sont interdites — `src/middleware.ts` les protège déjà, mais les montrer dans la nav
// promettait un accès qui n'existe pas). Connecté : l'inverse, jamais de proposition de créer un
// compte ou de se connecter à nouveau (mission `pbm-front-accueil`, point 3).
const VISITOR_LINKS: NavLink[] = [{ href: "/", label: "Présentation" }];
const SESSION_LINKS: NavLink[] = [
  { href: "/", label: "Tableau de bord" },
  { href: "/collection", label: "Collection" },
  { href: "/ajouter", label: "Ajouter" },
  { href: "/profil", label: "Profil" },
];

function MenuIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5" aria-hidden>
      <path strokeLinecap="round" d="M4 6h16M4 12h16M4 18h16" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5" aria-hidden>
      <path strokeLinecap="round" d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}

export function AppShell({
  children,
  hasSession = false,
}: {
  children: React.ReactNode;
  hasSession?: boolean;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const navLinks = hasSession ? SESSION_LINKS : VISITOR_LINKS;

  // L'état vient du serveur (cookie de session lu par `app/layout.tsx`, même source que la
  // garde de route `middleware.ts`) : jamais deviné côté client — le cookie est httpOnly. La
  // connexion (`connexion-form.tsx`) fait déjà `router.refresh()`, qui re-rend le layout et donc
  // cet en-tête ; la déconnexion ci-dessous fait de même (correctif `pbm-hotfix-fallback-ia-confiance`).
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
      <header className="border-b border-border bg-card px-5 py-3">
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2.5 font-pixel text-[11px] text-foreground">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-screen">
              <span className="h-3 w-3 rounded-full bg-primary" aria-hidden />
            </span>
            PokeBoyManager
          </Link>

          <button
            type="button"
            className="ml-auto grid h-9 w-9 shrink-0 place-items-center rounded-md border border-border text-foreground sm:hidden"
            aria-label={menuOpen ? "Fermer le menu" : "Ouvrir le menu"}
            aria-expanded={menuOpen}
            aria-controls="primary-nav"
            onClick={() => setMenuOpen((open) => !open)}
          >
            {menuOpen ? <CloseIcon /> : <MenuIcon />}
          </button>

          {/* Un seul jeu de liens dans le DOM : replié en panneau sous 640px (`menuOpen`),
              toujours affiché en ligne au-delà (`sm:flex` l'emporte sur `hidden`, voir
              e2e/responsive.spec.ts pour la vérification en navigateur réel). */}
          <div
            id="primary-nav"
            className={cn(
              "mt-3 w-full basis-full flex-col gap-3 sm:mt-0 sm:flex sm:w-auto sm:basis-auto sm:flex-row sm:items-center sm:gap-4",
              menuOpen ? "flex" : "hidden"
            )}
          >
            <nav className="flex flex-col gap-1 sm:flex-row sm:flex-wrap" aria-label="Navigation principale">
              {navLinks.map((link) => {
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

            <div className="flex flex-wrap items-center gap-3 sm:ml-auto">
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
                  <Link href="/connexion" className="text-sm font-medium text-muted-foreground hover:text-foreground">
                    Connexion
                  </Link>
                  <Link href="/inscription" className="text-sm font-medium text-muted-foreground hover:text-foreground">
                    Inscription
                  </Link>
                </>
              )}
              <ThemeToggle />
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-8">{children}</main>
    </div>
  );
}
