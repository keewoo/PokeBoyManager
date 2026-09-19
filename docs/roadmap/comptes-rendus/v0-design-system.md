# Compte rendu — `v0-design-system`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v0-design-system`, branche
`roadmap/v0-design-system`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du prompt
(sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, fusion directe vers `origin/main`
(dépôt relais local, pas GitHub).

## Résumé

Design system livré dans `apps/web` : jetons de couleur clair/sombre et typographies repris de
l'identité propre de la maquette (`.mk` dans `docs/roadmap/ROADMAP.html`, onglet « Maquette du
site »), briques `shadcn/ui` minimales (`cn()`, `Button`, `Badge`), six composants métier
(`AppShell`, `CardTile`, `ValueDelta`, `RarityBadge`, `ConditionBadge`, `EmptyState`), les sept
routes vides demandées, et une page interne `/design` servant de recette visuelle.

## Livrables

- **Jetons** (`apps/web/src/app/globals.css`) : `--background`, `--foreground`, `--card`,
  `--primary` (rouge), `--secondary`, `--muted`, `--border`, `--gold*` (rareté),
  `--success*` (hausse), `--danger*` (baisse, contrefaçon), `--ring`, `--radius` — valeurs claires
  et thème `[data-theme="dark"]` copiées telles quelles depuis les variables `--m-*` de la
  maquette (aucune couleur inventée). Bascule de thème sans flash (script inline dans `<head>`
  avant hydratation) + `ThemeProvider`/`useTheme` (`src/lib/theme-provider.tsx`, écrit à la main,
  pas de dépendance `next-themes`) et bouton `ThemeToggle`.
- **Typographies** (`next/font/google`, variables CSS) : Bricolage Grotesque (titres),
  Instrument Sans (texte courant), JetBrains Mono (valeurs numériques/prix), Press Start 2P
  (logo uniquement) — même mapping que la maquette.
- **`shadcn/ui` posé à la main, pas via le CLI** (voir Écarts) : `components.json`,
  `src/lib/utils.ts` (`cn` = `clsx` + `tailwind-merge`), `src/components/ui/button.tsx` et
  `badge.tsx` (`class-variance-authority`, `@radix-ui/react-slot` pour `asChild`) — code
  identique aux primitives shadcn standard.
- **Composants métier** (`src/components/`) : `AppShell` (nav + logo + bascule thème + lien
  Connexion/Inscription, actif via `usePathname`), `CardTile` (vignette carte, image ou espace
  réservé, badges rareté/état, prix + `ValueDelta`), `ValueDelta` (variation signée,
  `data-variant="up|down|flat"`), `RarityBadge` (6 paliers, doré à partir de « rare holo »),
  `ConditionBadge` (6 états, vert/neutre/rouge), `EmptyState` (titre, description, action
  lien ou bouton).
- **Routes** : `/`, `/inscription`, `/connexion`, `/ajouter`, `/collection`, `/carte/[id]`,
  `/profil` — toutes rendues via `AppShell` + `EmptyState` avec un message explicite du lot qui
  les remplira (pas de contenu fonctionnel, hors périmètre ici).
- **`/design`** : nuancier des jetons, échantillons typographiques, variantes `Button`/`Badge`,
  toutes les valeurs de `RarityBadge`/`ConditionBadge`, `ValueDelta` (hausse/baisse/neutre),
  grille de `CardTile` (4 exemples), `EmptyState`.

## Preuves (commandes lancées, résultats)

```
$ pnpm --filter @pbm/web lint
$ eslint .          (exit 0, aucune sortie)

$ pnpm --filter @pbm/web type-check
$ tsc --noEmit      (exit 0, aucune sortie)

$ pnpm --filter @pbm/web test
✓ src/__tests__/config.test.ts (2 tests)
✓ src/__tests__/rarity-badge.test.tsx (2 tests)
✓ src/__tests__/condition-badge.test.tsx (2 tests)
✓ src/__tests__/value-delta.test.tsx (3 tests)
✓ src/__tests__/empty-state.test.tsx (4 tests)
✓ src/__tests__/card-tile.test.tsx (2 tests)
✓ src/__tests__/app-shell.test.tsx (2 tests)
Test Files  7 passed (7) · Tests  17 passed (17)

$ pnpm --filter @pbm/web build
✓ Compiled successfully · 9 routes générées (8 statiques + /carte/[id] dynamique),
  First Load JS partagé 102 kB
```

Preuve « le test échoue sans le changement, passe avec » (§6) — TDD réel, pas une mutation
a posteriori : les 6 fichiers de test des composants ont été écrits et lancés **avant**
d'écrire les composants.

```
$ pnpm --filter @pbm/web test   (avant l'implémentation)
FAIL src/__tests__/value-delta.test.tsx    Failed to resolve import "@/components/value-delta"
FAIL src/__tests__/rarity-badge.test.tsx   Failed to resolve import "@/components/rarity-badge"
FAIL src/__tests__/condition-badge.test.tsx …
FAIL src/__tests__/empty-state.test.tsx …
FAIL src/__tests__/card-tile.test.tsx …
FAIL src/__tests__/app-shell.test.tsx …
Test Files  6 failed | 1 passed (7)   Tests  2 passed (2)

$ pnpm --filter @pbm/web test   (après l'implémentation)
Test Files  7 passed (7)   Tests  17 passed (17)
```

Au passage, un défaut d'environnement de test a été corrigé : `window.matchMedia` n'existe pas
en jsdom, ce qui faisait échouer `AppShell`/`ThemeProvider` (`TypeError: window.matchMedia is
not a function`). Polyfill minimal ajouté dans `apps/web/vitest.setup.ts`.

Routes vérifiées en conditions réelles (`pnpm dev`, port 3000) :

```
$ for r in / /inscription /connexion /ajouter /collection /carte/1 /profil /design; do
    curl -s -o /dev/null -w "%{http_code}" "http://localhost:3000$r"; done
200 200 200 200 200 200 200 200

$ curl -s http://localhost:3000/design | grep -oE 'data-slot="[a-z-]+"' | sort -u
badge, button, card-tile, condition-badge, empty-state, rarity-badge, value-delta

$ curl -s http://localhost:3000/collection | grep -oE '<a [^>]*aria-current="page"[^>]*>[^<]*</a>'
<a aria-current="page" class="… bg-secondary font-semibold text-foreground" href="/collection">Collection</a>

$ curl -s http://localhost:3000/carte/42 | grep -o "« 42 »"
« 42 »   (paramètre dynamique bien reçu par la page serveur)
```

Aucun secret : `git diff --stat` ne touche que du code front statique ; aucune clé, jeton ou
URL de service n'apparaît dans les fichiers modifiés.

## Choix techniques faits (autonomes, dans le cadre de `docs/ARCHITECTURE.md`)

- **`shadcn/ui` posé à la main plutôt que via `pnpm dlx shadcn@latest init`** : le CLI attend un
  registre (`ui.shadcn.com`) et un mode interactif, incompatibles avec une session `-p` et avec
  la contrainte réseau de chimera. Le résultat est identique (mêmes fichiers, mêmes
  dépendances : `class-variance-authority`, `@radix-ui/react-slot`, `clsx`, `tailwind-merge`) —
  seul l'outillage de génération change. `components.json` documente le choix (style
  `new-york`, `cssVariables: true`) pour que les lots suivants puissent utiliser le CLI
  normalement s'ils le souhaitent.
- **`next-themes` évité, `ThemeProvider` écrit à la main** (~35 lignes) : un besoin
  clair/sombre à deux valeurs ne justifie pas une dépendance supplémentaire ; le script anti-flash
  dans `<head>` reprend le même principe que celui déjà validé dans `ROADMAP.html`
  (`data-theme` posé avant hydratation).
- **`lucide-react` évité** : aucune icône n'était strictement nécessaire pour les six
  composants demandés (deux icônes soleil/lune en SVG inline pour `ThemeToggle` suffisent) —
  économise un téléchargement sur un réseau à ~250 Ko/s pour un gain nul à ce stade.
- **Images de carte en `<img>` simple, pas `next/image`** : la vraie source (TCGdex) n'est pas
  encore connue/autorisée dans `next.config.ts` (`images.remotePatterns`) — ce sera au lot qui
  branche le catalogue de le faire ; `CardTile` reste fonctionnel avec un espace réservé
  (« Image à venir ») en attendant.
- **`ValueDelta` sans icône flèche** : une flèche à côté du texte cassait
  `getByText("+12,3 %")` (Testing Library matche le texte propre d'un nœud, pas un mélange
  icône+texte) ; la couleur (`text-success`/`text-danger`) et l'attribut `data-variant` suffisent
  à distinguer hausse/baisse/neutre, y compris pour les tests et l'accessibilité par lecteur
  d'écran (pas de sens porté uniquement par une forme).
- **Formatage manuel du pourcentage** (`toFixed(1)` + remplacement du point par une virgule)
  plutôt que `Intl.NumberFormat("fr-FR")` : évite une dépendance au comportement exact de
  l'espace insécable/format ICU de l'environnement d'exécution (Node vs navigateurs), pour un
  rendu déterministe en test comme en production.

## Écarts au plan

- **Capture d'écran de la maquette non produite** (§6 : « conformité à l'écran de la maquette,
  capture jointe au compte rendu »). Tentative réelle : `playwright` installé
  (13 s, taille normale), mais le téléchargement du binaire Chromium plafonnait à ~100 Ko/s
  (mesuré : 2,3 Mo en 20 s) — plusieurs dizaines de Mo restants, soit ~20-25 min de plus,
  contraire à la règle machine « chimera : réseau ~250 Ko/s, pas de gros téléchargement
  inutile ». Téléchargement interrompu, `playwright` retiré (`pnpm remove`, aucune trace dans
  `pnpm-lock.yaml`). À la place : vérification textuelle complète (8 routes en 200, présence
  des 6 `data-slot` sur `/design`, `aria-current` correct sur la nav, jetons de couleur copiés
  1:1 depuis les variables `--m-*` de la maquette) — voir « Preuves » ci-dessus. **Reste à
  faire** : une vraie capture, à produire soit depuis une machine avec un accès réseau correct
  (devAI), soit une fois que `v5-e2e` (Playwright, explicitement de son périmètre selon
  `docs/ARCHITECTURE.md`) aura le navigateur déjà installé sur chimera.
- **Test d'accès croisé (§6) sans objet** : confirmé par la grille du prompt lui-même
  (« securite : sans objet — aucune donnée ») ; aucune route utilisateur, aucune session,
  aucune donnée dans ce lot. S'appliquera à partir de `v1-auth`.
- **`fleet-run` non utilisé** : conformément au CONTEXTE D'EXÉCUTION, tout tourne « ici même sur
  chimera ».
- **Aucune clé IA réelle utilisée** : rien dans ce lot n'appelle un fournisseur IA.

## Reste à faire (pour les lots suivants)

- Contenu fonctionnel des sept routes (accueil, auth, ajout, collection, fiche, profil) —
  chacune reste un `EmptyState` volontairement provisoire.
- Capture d'écran réelle de conformité à la maquette (cf. écart ci-dessus).
- Brancher les images officielles du catalogue dans `CardTile` (`next/image` +
  `images.remotePatterns` une fois la source connue).
- Étendre `shadcn/ui` (autres primitives : `Input`, `Select`, `Dialog`…) au fur et à mesure des
  besoins des lots de pages.

## Décisions provisoires utilisées

D3, D4, D5, D6, D7 — telles que rappelées dans le CONTEXTE D'EXÉCUTION du prompt (aucune
n'affecte directement ce lot, purement front/design). D2/D8 hors périmètre, confirmé.
