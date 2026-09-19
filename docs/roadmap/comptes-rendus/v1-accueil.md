# Compte rendu — `v1-accueil`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v1-accueil`, branche
`roadmap/v1-accueil`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du prompt
(sections A/P/0/7 remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, fusion directe vers `origin/main`
(dépôt relais local `~/dev/pokeboy.git`, pas GitHub).

## Résumé

Page d'accueil publique (`/`) reproduisant l'écran « Accueil (visiteur) » de la maquette
(`docs/roadmap/ROADMAP.html`, onglet Maquette, fonction `V.accueil`) : accroche, démonstration
« photo → cartes → valeur », quatre étapes, panneau « Apporte ta propre IA », pied de page
légal. Trois pages légales en brouillon (`/mentions-legales`, `/confidentialite`,
`/conditions`) marquées explicitement « à relire par JF ». Métadonnées SEO et Open Graph
dédiées sur `/`.

**Écart majeur, à lire avant tout** : la redirection du visiteur connecté vers son tableau de
bord (mission §3.1) n'a **pas** été implémentée — voir « Écarts au plan ». Le score Lighthouse
≥ 90 (mission §3.3) n'a **pas** pu être mesuré — voir « Écarts au plan ».

## Livrables

- **`apps/web/src/app/page.tsx`** : hero (accroche, accroche H1, deux CTA `/inscription` et
  `/connexion`), `ScanDemo`, quatre étapes (photo → reconnaissance → valeur → histoire),
  panneau BYOK (Claude/Gemini/ChatGPT), `LegalFooter`. Métadonnées `title`/`description`/
  `openGraph`/`twitter` dédiées (reprennent l'accroche de la maquette).
- **`apps/web/src/components/scan-demo.tsx`** : démonstration visuelle statique (9
  emplacements numérotés, 2 marqués « suspects », compteurs détectées/identifiées/
  contrefaçons probables, valeur estimée) — équivalent du `.scanbox` de la maquette, en
  composants/tokens du design system (pas de couleur inventée).
- **`apps/web/src/components/legal-footer.tsx`** : liens vers les trois pages légales +
  mention de non-affiliation à Nintendo/Creatures/GAME FREAK/The Pokémon Company (risque §4).
- **Pages légales brouillons** : `apps/web/src/app/{mentions-legales,confidentialite,
  conditions}/page.tsx` — contenu réaliste mais avec champs `[à compléter]` explicites
  (éditeur, hébergeur, contact) et bandeau « Brouillon — à relire par JF avant mise en ligne »
  en tête de chaque page. Métadonnées `title`/`description` par page.
- **Tests** (TDD, voir Preuves) : `scan-demo.test.tsx`, `legal-footer.test.tsx`,
  `legal-pages.test.tsx`, `home-page.test.tsx`.

## Preuves (commandes lancées, résultats)

TDD réel — tests écrits et lancés **avant** l'implémentation :

```
$ pnpm --filter @pbm/web test -- --run   (avant l'implémentation)
FAIL src/__tests__/scan-demo.test.tsx      Failed to resolve import "@/components/scan-demo"
FAIL src/__tests__/legal-footer.test.tsx   Failed to resolve import "@/components/legal-footer"
FAIL src/__tests__/legal-pages.test.tsx    Failed to resolve import "@/app/mentions-legales/page"
FAIL src/__tests__/home-page.test.tsx      getByRole("link", {name: "Mentions légales"}) introuvable
Test Files  4 failed | 7 passed (11)   Tests  4 failed | 17 passed (21)
```

```
$ pnpm --filter @pbm/web test -- --run   (après l'implémentation)
✓ 11 fichiers de test, 29 tests
Test Files  11 passed (11)   Tests  29 passed (29)

$ pnpm --filter @pbm/web lint
$ eslint .          (exit 0)

$ pnpm --filter @pbm/web type-check
$ tsc --noEmit      (exit 0)

$ pnpm --filter @pbm/web build
✓ Compiled successfully · 12 routes (11 statiques + /carte/[id] dynamique)
  First Load JS partagé 102 kB, / = 106 kB
```

Vérification en conditions réelles (`next start`, port 3101) :

```
$ for r in / /mentions-legales /confidentialite /conditions; do
    curl -s -o /dev/null -w "%{http_code}" "http://localhost:3101$r"; done
200 200 200 200

$ curl -s http://localhost:3101/ | grep -oE '<title>[^<]*</title>|<meta property="og:[^"]*"'
<title>PokeBoyManager — Photographie ta collection, suis sa valeur</title>
<meta property="og:title" ...
<meta property="og:description" ...
<meta property="og:locale" content="fr_FR"
<meta property="og:type" content="website"

$ curl -s http://localhost:3101/ | grep -oE 'href="/mentions-legales"|href="/confidentialite"|href="/conditions"'
href="/mentions-legales"
href="/confidentialite"
href="/conditions"
```

Aucun secret : `git diff --stat` ne touche que du code front statique (page, composants,
tests) ; aucune clé, jeton, URL de service dans les fichiers modifiés.

## Choix techniques faits (autonomes, dans le cadre de `docs/ARCHITECTURE.md`)

- **`ScanDemo` sans props** : la démonstration est un contenu marketing statique (données
  d'exemple identiques à la maquette), pas un composant réutilisable avec des données réelles
  — pas de catalogue branché dans ce lot. Un composant paramétrable aurait été une abstraction
  sans second appelant.
- **Couleurs de `ScanDemo` sur fond `--screen`** : le fond `--screen` est sombre dans les deux
  thèmes (comme dans la maquette) ; le texte utilise `text-white/80` plutôt qu'un token de
  couleur de thème (`text-secondary` serait illisible en thème clair sur un fond toujours
  sombre) — cohérent avec la maquette qui fixe aussi une couleur claire (`#C9D1DD`) sur son
  `.scan-foot` indépendamment du thème du site.
- **Pages légales avec contenu réaliste mais incomplet** (éditeur, hébergeur, contact en
  `[à compléter]`) plutôt que des `EmptyState` : la mission demande des « brouillons à relire
  par JF », pas des pages vides ; un bandeau explicite en tête de chaque page évite toute
  ambiguïté sur leur statut.
- **`LegalFooter` posé uniquement sur `/`** et pas dans `AppShell` (site-wide) : la maquette ne
  montre la mention de non-affiliation et les liens légaux que sur l'écran d'accueil visiteur ;
  les autres routes restent hors périmètre de ce lot (stubs `EmptyState` du lot
  `v0-design-system`).

## Écarts au plan

- **Redirection du visiteur connecté (mission §3.1) non implémentée.** Aucun mécanisme de
  session n'existe encore dans le dépôt : `v1-auth` (comptes, connexion) n'est **pas** une
  dépendance déclarée de `v1-accueil` dans `roadmap.json`, et la vraie « Accueil connecté »
  (`v4-dashboard`) est un lot de jalon V4, bien plus tardif. Il n'existe donc aujourd'hui ni
  cookie de session côté front, ni route de tableau de bord vers laquelle rediriger. Construire
  une détection de session contre une API qui n'existe pas encore aurait été spéculatif. `/`
  sert donc uniquement le contenu visiteur pour l'instant — **reste à faire** une fois
  `v1-auth` et `v4-dashboard` livrés : un check de session (middleware Next.js ou layout
  serveur) qui redirige vers le tableau de bord si connecté.
- **Score Lighthouse ≥ 90 (mission §3.3) non mesuré.** Tentative réelle avec le binaire
  Chromium de Playwright déjà présent en cache sur la machine
  (`~/.cache/ms-playwright/chromium-1243`, laissé par un lot voisin) : `pnpm add -D
  playwright@1.63.0 lighthouse` a réutilisé le cache sans retélécharger le navigateur (~37 s,
  pas de téléchargement de Chromium). Mais le lancement échoue :
  ```
  error while loading shared libraries: libnspr4.so: cannot open shared object file
  ```
  `ldd` sur le binaire confirme **cinq** bibliothèques système absentes :
  `libnspr4.so`, `libnss3.so`, `libnssutil3.so`, `libsmime3.so`, `libasound.so.2`
  (`dpkg -l | grep nspr` : rien d'installé). Les poser exigerait `sudo apt-get install`, donc
  root — interdit sur cette machine (règle « jamais root », session `claude -p` qui de toute
  façon refuse `--dangerously-skip-permissions` sous root). Aucune tentative de contournement.
  `playwright`/`lighthouse` retirés (`pnpm remove`), `pnpm-lock.yaml` restauré à l'identique
  (`git checkout`, vérifié par `git diff` vide puis `pnpm install --frozen-lockfile`) : aucune
  trace dans le commit. **Ceci n'est pas spécifique à ce lot** : tout lot futur mesurant un
  score Lighthouse ou prenant une capture d'écran réelle (notamment `v5-e2e`) rencontrera le
  même blocage tant que ces cinq bibliothèques ne sont pas posées une fois, par un accès root
  légitime (JF, ou délégation à devAI). À défaut de mesure réelle, vérification textuelle
  complète (routes 200, structure HTML, balises SEO/OG) — voir « Preuves ».
- **Capture d'écran de conformité à la maquette (§6) non produite** — même blocage que
  ci-dessus (pas de Chromium fonctionnel). Vérification textuelle à la place : présence de
  l'accroche, des deux CTA avec les bons `href`, des quatre étapes avec les mêmes titres que la
  maquette, du panneau BYOK avec les trois badges fournisseurs, du pied de page légal — voir
  tests et « Preuves ».
- **Test d'accès croisé (§6) sans objet** : aucune route utilisateur, aucune session, aucune
  donnée dans ce lot (confirmé par la grille du prompt lui-même : « securite : sans objet »).
- **`fleet-run` non utilisé** : conformément au CONTEXTE D'EXÉCUTION, tout tourne ici même sur
  chimera.

## Reste à faire (pour les lots suivants)

- Redirection visiteur connecté → tableau de bord, une fois `v1-auth` (session) et
  `v4-dashboard` (route) livrés.
- Mesure réelle du score Lighthouse et capture d'écran de conformité à la maquette, une fois
  les bibliothèques système de Chromium posées (accès root ponctuel nécessaire) — ou déléguées
  à une machine qui les a déjà (devAI).
- Compléter les pages légales (éditeur, hébergeur, contact) avant mise en ligne — actuellement
  des champs `[à compléter]` explicites.

## Décisions provisoires utilisées

D3, D4, D5, D6, D7 — telles que rappelées dans le CONTEXTE D'EXÉCUTION (aucune n'affecte
directement ce lot, purement front/contenu public). D2/D8 hors périmètre, confirmé (aucun
déploiement UAT/PROD depuis ce lot).
