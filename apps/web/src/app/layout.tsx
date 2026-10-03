import type { Metadata, Viewport } from "next";
import { cookies, headers } from "next/headers";
import { exo2, jetbrainsMono, pressStart2P, roboto } from "./fonts";
import { ThemeProvider } from "@/lib/theme-provider";
import { AppShell } from "@/components/app-shell";
import { getSessionCookieName } from "@/lib/config";
import "./globals.css";

// Charte PokéBoy : Roboto pour tout ce qui se lit longtemps, Exo 2 pour les titres de
// section, les onglets, les étiquettes et les chiffres. Press Start 2P reste réservée aux
// titres de niveau 1, courts — au-delà de trois mots elle devient illisible. Les quatre
// familles sont embarquées dans le dépôt et servies par `next/font/local` (voir `./fonts.ts`),
// jamais téléchargées depuis Google au build — un flux `next/font/google` incomplet cassait
// `next build` par intermittence (lot `fix-ci-fiabilite`).

// `metadataBase` est l'origine qui absolutise `opengraph-image` : sans elle, Next avertit à la
// construction et sert une URL relative, que les aperçus (réseaux sociaux, messageries) ne savent
// pas résoudre. Surchargeable par `NEXT_PUBLIC_SITE_URL` pour l'UAT ou une préproduction.
/**
 * Métadonnées globales lues par Next pour le `<head>` de chaque page : titre
 * (gabarit `%s · PokéBoy`), description, nom d'application et cartes Open Graph.
 * `metadataBase` absolutise les images d'aperçu ; les pages la complètent via
 * leur propre `metadata`, elles ne la remplacent pas.
 */
export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "https://pokeboy.lol"),
  title: {
    default: "PokéBoy — collectionneurs de légendes",
    template: "%s · PokéBoy",
  },
  description:
    "Gérez votre collection de cartes Pokémon : reconnaissance par photo, cote du marché, decks et échanges.",
  applicationName: "PokéBoy",
  appleWebApp: {
    capable: true,
    title: "PokéBoy",
    statusBarStyle: "black-translucent",
  },
  openGraph: {
    type: "website",
    siteName: "PokéBoy",
    locale: "fr_FR",
    title: "PokéBoy — collectionneurs de légendes",
    description:
      "Gérez votre collection de cartes Pokémon : reconnaissance par photo, cote du marché, decks et échanges.",
  },
};

// Couleur de la barre d'adresse sur mobile et de l'écran de lancement en PWA : le bleu nuit
// de la charte (#050A30), dans les deux thèmes — le fond du produit est sombre par nature.
/**
 * Viewport Next : fixe la couleur de la barre d'adresse mobile et de l'écran de
 * lancement PWA au bleu nuit de la charte, identique dans les deux thèmes.
 */
export const viewport: Viewport = {
  themeColor: "#050A30",
};

const NO_FLASH_THEME_SCRIPT = `
(function () {
  try {
    var stored = window.localStorage.getItem("pbm-theme");
    var theme = stored === "light" || stored === "dark"
      ? stored
      : (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", theme);
  } catch (e) {}
})();
`;

/**
 * Layout racine de l'application : `<html lang="fr">`, polices de la charte, thème (clair/sombre
 * sans flash via un script inline portant le nonce CSP de la requête) et app-shell commune.
 * Lit le cookie de session côté serveur pour que la navigation d'`AppShell` connaisse l'état
 * connecté/visiteur, et le re-rend après connexion/déconnexion (`router.refresh()`), ce qui garde
 * l'en-tête aligné sur l'état réel.
 */
export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Posé par `src/middleware.ts` (mission `v5-securite` point 2) : attache ce script inline au
  // nonce de la CSP de cette requête précise, seul moyen de l'autoriser sans `'unsafe-inline'`
  // sur `script-src`.
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  // Même source de vérité que la garde de route (`middleware.ts`) et la page d'accueil
  // (`app/page.tsx`) : la présence du cookie de session, lu côté serveur (il est httpOnly).
  // La nav de `AppShell` a besoin de savoir si un visiteur est connecté, pas seulement l'accueil
  // (mission `pbm-front-accueil`, point 3). `router.refresh()` après connexion/déconnexion re-rend
  // ce layout — l'en-tête suit toujours l'état réel (correctif `pbm-hotfix-fallback-ia-confiance`).
  const hasSession = (await cookies()).has(getSessionCookieName());

  return (
    <html lang="fr" suppressHydrationWarning>
      <head>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: NO_FLASH_THEME_SCRIPT }} />
      </head>
      <body
        className={`${roboto.variable} ${exo2.variable} ${jetbrainsMono.variable} ${pressStart2P.variable} font-sans antialiased`}
      >
        <ThemeProvider>
          <AppShell hasSession={hasSession}>{children}</AppShell>
        </ThemeProvider>
      </body>
    </html>
  );
}
