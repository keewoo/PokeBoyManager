import localFont from "next/font/local";

// Polices embarquées dans le dépôt et servies par `next/font/local` (lot `fix-ci-fiabilite`).
//
// Pourquoi : `next/font/google` télécharge les polices depuis `fonts.googleapis.com` AU MOMENT DU
// BUILD. La moindre réponse incomplète de Google y cassait `next build`
// (`TypeError: Cannot read properties of null (reading '1')` dans `nextFontGoogleFontLoader`),
// de façon intermittente — trois échecs de CI sur un arbre identique à une branche verte le
// 01/10/2026. En embarquant les fichiers, le build ne dépend plus d'aucun réseau.
//
// Fidélité : mêmes familles, mêmes graisses utiles, mêmes styles et MÊMES variables CSS qu'avant
// (`--font-roboto`, `--font-exo2`, `--font-jetbrains-mono`, `--font-press-start`, lues par
// `globals.css`). Les trois familles variables sont embarquées sur toute leur plage d'axe `wght`
// (une seule police couvre 400/500/700 pour Roboto, 500/600/700/800 pour Exo 2, etc.) ; Press
// Start 2P est statique (400). Sous-ensembles latin + latin-ext réunis en un fichier par famille
// (découpe fonttools sur la police amont). Fichiers `.woff2` et licences : `./fonts/`
// (voir `./fonts/README.md`).

/** Police de texte Roboto (variable 100-900), exposée via `--font-roboto`. */
export const roboto = localFont({
  src: "./fonts/roboto.woff2",
  weight: "100 900",
  style: "normal",
  display: "swap",
  variable: "--font-roboto",
});

/** Police de titres Exo 2 (variable 100-900), exposée via `--font-exo2`. */
export const exo2 = localFont({
  src: "./fonts/exo2.woff2",
  weight: "100 900",
  style: "normal",
  display: "swap",
  variable: "--font-exo2",
});

/** Police à chasse fixe JetBrains Mono (variable 100-800), exposée via `--font-jetbrains-mono`. */
export const jetbrainsMono = localFont({
  src: "./fonts/jetbrains-mono.woff2",
  weight: "100 800",
  style: "normal",
  display: "swap",
  variable: "--font-jetbrains-mono",
});

/** Police d'accent rétro Press Start 2P (statique 400), exposée via `--font-press-start`. */
export const pressStart2P = localFont({
  src: "./fonts/press-start-2p.woff2",
  weight: "400",
  style: "normal",
  display: "swap",
  variable: "--font-press-start",
});
