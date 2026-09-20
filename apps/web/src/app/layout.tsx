import type { Metadata } from "next";
import { cookies, headers } from "next/headers";
import {
  Bricolage_Grotesque,
  Instrument_Sans,
  JetBrains_Mono,
  Press_Start_2P,
} from "next/font/google";
import { ThemeProvider } from "@/lib/theme-provider";
import { AppShell } from "@/components/app-shell";
import { getSessionCookieName } from "@/lib/config";
import "./globals.css";

const instrumentSans = Instrument_Sans({
  subsets: ["latin"],
  variable: "--font-instrument-sans",
});

const bricolageGrotesque = Bricolage_Grotesque({
  subsets: ["latin"],
  variable: "--font-bricolage",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
});

const pressStart2P = Press_Start_2P({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-press-start",
});

export const metadata: Metadata = {
  title: "PokeBoyManager",
  description: "Gestion de collection de cartes Pokémon",
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
        className={`${instrumentSans.variable} ${bricolageGrotesque.variable} ${jetbrainsMono.variable} ${pressStart2P.variable} font-sans antialiased`}
      >
        <ThemeProvider>
          <AppShell hasSession={hasSession}>{children}</AppShell>
        </ThemeProvider>
      </body>
    </html>
  );
}
