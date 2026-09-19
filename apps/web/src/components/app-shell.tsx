"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { ThemeToggle } from "@/components/theme-toggle";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { href: "/", label: "Accueil" },
  { href: "/collection", label: "Collection" },
  { href: "/ajouter", label: "Ajouter" },
  { href: "/profil", label: "Profil" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

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
          {NAV_LINKS.map((link) => {
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
          <Link href="/connexion" className="text-sm font-medium text-muted-foreground hover:text-foreground">
            Connexion
          </Link>
          <Link href="/inscription" className="text-sm font-medium text-muted-foreground hover:text-foreground">
            Inscription
          </Link>
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-8">{children}</main>
    </div>
  );
}
