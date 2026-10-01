# Polices embarquées

Servies par `next/font/local` (voir `../fonts.ts`), plus jamais téléchargées depuis Google au
build. Mise en place par le lot `fix-ci-fiabilite` (01/10/2026), après trois échecs de CI dus à
`next/font/google` qui tirait ces polices depuis `fonts.googleapis.com` pendant `next build`.

Chaque `.woff2` réunit les sous-ensembles **latin + latin-ext** (découpe `pyftsubset` de la police
amont de Google Fonts, axe `wght` complet conservé pour les familles variables).

| Fichier | Famille | Type | Source amont | Licence |
|---|---|---|---|---|
| `roboto.woff2` | Roboto | variable (wght 100–900, wdth) | `google/fonts` `ofl/roboto/Roboto[wdth,wght].ttf` | OFL 1.1 — `LICENSE-Roboto-OFL.txt` |
| `exo2.woff2` | Exo 2 | variable (wght 100–900) | `ofl/exo2/Exo2[wght].ttf` | OFL 1.1 — `LICENSE-Exo2-OFL.txt` |
| `jetbrains-mono.woff2` | JetBrains Mono | variable (wght 100–800) | `ofl/jetbrainsmono/JetBrainsMono[wght].ttf` | OFL 1.1 — `LICENSE-JetBrainsMono-OFL.txt` |
| `press-start-2p.woff2` | Press Start 2P | statique (400) | `ofl/pressstart2p/PressStart2P-Regular.ttf` | OFL 1.1 — `LICENSE-PressStart2P-OFL.txt` |

**Roboto est sous OFL 1.1**, pas Apache-2.0 : Google a relicencié Roboto en OFL en 2024 (le dépôt
`google/fonts` le sert désormais depuis `ofl/roboto/`, plus `apache/`). La licence embarquée ici
est donc celle qui gouverne réellement ces octets.
