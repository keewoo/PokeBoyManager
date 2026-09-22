"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { logout } from "@/lib/api/auth";
import { fetchDeckAlerts } from "@/lib/api/decks";
import { cn } from "@/lib/utils";

const DECKS_HREF = "/jeu/decks";

type NavLink = { href: string; label: string };

// Visiteur : présentation + Connexion/Inscription (jamais Collection/Ajouter/Profil, des
// pages qui lui sont interdites — `src/middleware.ts` les protège déjà, mais les montrer
// dans la nav promettait un accès qui n'existe pas). Connecté : l'inverse, jamais de
// proposition de créer un compte ou de se connecter à nouveau (mission `pbm-front-accueil`,
// point 3).
const VISITOR_LINKS: NavLink[] = [{ href: "/", label: "Présentation" }];
const SESSION_LINKS: NavLink[] = [
  { href: "/", label: "Tableau de bord" },
  { href: "/collection", label: "Collection" },
  { href: "/ajouter", label: "Ajouter" },
  { href: "/jeu/decks", label: "Decks" },
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

  // Badge d'alertes « à compléter » sur l'onglet Decks (mission `v7-decks-collection-sync` :
  // « notification au joueur, en-tête »). Best-effort : si l'appel échoue, on n'affiche pas de
  // badge plutôt que d'annoncer un « 0 » mensonger — l'absence de badge est honnête, pas un repli
  // qui masque une panne de donnée nominale (la liste des decks, elle, reste fiable côté page).
  const [unreadAlerts, setUnreadAlerts] = useState(0);
  useEffect(() => {
    if (!hasSession) {
      setUnreadAlerts(0);
      return;
    }
    let active = true;
    fetchDeckAlerts(true)
      .then((res) => {
        if (active) setUnreadAlerts(res.unread_count);
      })
      .catch(() => {
        if (active) setUnreadAlerts(0);
      });
    return () => {
      active = false;
    };
    // `pathname` en dépendance : après une vente (page Collection) puis retour, le badge se réévalue.
  }, [hasSession, pathname]);

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
    <div className="flex min-h-screen flex-col">
      {/* Charte : l'en-tête ne porte QUE le logotype. L'icône d'application est une pièce
          distincte — le logotype contient déjà son symbole, et les poser côte à côte ferait
          deux marques concurrentes dans le même bandeau. */}
      <header className="border-b border-[rgba(157,0,255,0.3)] bg-[rgba(10,16,72,0.72)] px-5 py-3 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <Link href="/" className="flex shrink-0 items-center gap-3" aria-label="PokéBoy — accueil">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/icons/icon-192.png"
              alt=""
              className="h-10 w-10 rounded-xl shadow-[0_0_0_1px_rgba(255,20,147,0.4),0_0_20px_rgba(157,0,255,0.55)]"
            />
            <span className="font-pixel text-[13px] text-gold [text-shadow:0_2px_0_#7A5B00] sm:text-sm">
              POKÉBOY
            </span>
          </Link>

          <button
            type="button"
            className="ml-auto grid h-11 w-11 shrink-0 place-items-center rounded-full border border-[rgba(157,0,255,0.65)] text-violet-clair sm:hidden"
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
            <nav className="flex flex-col gap-1.5 sm:ml-auto sm:flex-row sm:flex-wrap sm:items-center" aria-label="Navigation principale">
              {navLinks.map((link) => {
                const isActive = pathname === link.href;
                const showAlerts = link.href === DECKS_HREF && unreadAlerts > 0;
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    aria-current={isActive ? "page" : undefined}
                    className={cn(
                      // Charte : la navigation est en pilules ; l'onglet actif s'allume en or.
                      "inline-flex items-center gap-1.5 rounded-full border border-transparent px-4 py-2.5 font-heading text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground transition-colors hover:text-foreground",
                      isActive &&
                        "border-[rgba(255,215,0,0.75)] bg-[rgba(255,215,0,0.1)] font-bold text-gold"
                    )}
                  >
                    {link.label}
                    {showAlerts && (
                      <span
                        className="grid min-w-[1.25rem] place-items-center rounded-full bg-[#D6006E] px-1.5 py-0.5 text-[10px] font-bold leading-none text-white"
                        aria-label={`${unreadAlerts} deck(s) à compléter`}
                        data-testid="decks-alert-badge"
                      >
                        {unreadAlerts}
                      </span>
                    )}
                  </Link>
                );
              })}
            </nav>

            <div className="flex flex-wrap items-center gap-2 sm:gap-3">
              {hasSession ? (
                <button
                  type="button"
                  onClick={handleLogout}
                  disabled={isLoggingOut}
                  className="rounded-full border border-transparent px-4 py-2.5 font-heading text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground hover:text-foreground disabled:opacity-60"
                >
                  {isLoggingOut ? "Déconnexion…" : "Déconnexion"}
                </button>
              ) : (
                <>
                  <Link
                    href="/connexion"
                    className="rounded-full border border-[rgba(157,0,255,0.8)] px-5 py-2.5 font-heading text-xs font-semibold uppercase tracking-[0.08em] text-foreground shadow-[inset_0_0_18px_rgba(157,0,255,0.28)]"
                  >
                    Connexion
                  </Link>
                  <Link
                    href="/inscription"
                    className="rounded-full bg-[linear-gradient(180deg,#FFF0A0_0%,#FFD700_52%,#E0A800_100%)] px-5 py-2.5 font-heading text-xs font-extrabold uppercase tracking-[0.08em] text-primary-foreground shadow-[0_0_24px_rgba(255,215,0,0.45),inset_0_1px_0_rgba(255,255,255,0.7)]"
                  >
                    Inscription
                  </Link>
                </>
              )}
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-8">{children}</main>
    </div>
  );
}
