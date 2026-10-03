# doc-web — documentation de `apps/web`

Lot **hors plan**, demandé par JF le 02/10/2026 (« faudra bien documenter tout le code »).
Objectif : donner un commentaire de documentation (`/** … */`) à **chaque export** de
`apps/web/src` (composant, hook, fonction, constante, type/interface), sans **aucun**
changement de comportement. Base : `main` à `ac6b95b`.

## Couverture — avant / après

Mesurée par `scripts/doc-coverage.py` (non versionné), qui compte les déclarations exportées
(`export (const|function|class|type|interface|enum) …`) des fichiers `.ts/.tsx` non-test de
`apps/web/src` et vérifie la présence d'un bloc `/** */` immédiatement au-dessus.

| | Exports | Documentés | Couverture |
|---|---|---|---|
| **Avant** | 429 | 95 | **22 %** |
| **Après** | 429 | 429 | **100 %** |

> La fiche `docs/CODE.md` citait « ~7 % » : ce chiffre comptait plus étroitement (composants,
> hooks, fonctions et constantes « métier », hors types/interfaces et hors exports déjà munis
> d'un commentaire `//`). Les deux mesures racontent la même chose : la quasi-totalité du front
> était sans documentation de tête. Après ce lot, **tout export** en a une, types compris.

- **109 fichiers** touchés, **807 lignes ajoutées, 0 supprimée**, **~340 blocs `/** */`** insérés.
- Les 4 derniers exports (`HomeContent`, `metadata`/`viewport` de `layout.tsx`, `TRADUCTEURS`
  de `journal.ts`) portaient déjà une prose `//` riche : un bloc `/** */` concis a été ajouté
  **au-dessus de la déclaration** (sous la prose existante, qu'il n'efface pas) pour que Graphify
  rattache le bon nœud au symbole.

## Preuve « que des commentaires » — règle d'or tenue mécaniquement

La règle d'or du lot (aucun changement de comportement) est prouvée, pas affirmée :

1. **`git diff --numstat` : 0 ligne supprimée** sur les 109 fichiers.
2. **`git diff -U0` tokenisé** : chaque ligne **ajoutée** est une ligne de commentaire
   (`/**`, ` * …`, `*/`, ou `//` préexistant conservé) ; **0 ligne de code ajoutée**, **0 ligne
   supprimée**. Verdict du contrôle : **PUR**.
3. **Intégrité des directives** : `"use client"` reste la 1re instruction de chacun des 37
   fichiers clients (aucun commentaire inséré avant elle).

Un diff strictement additif de commentaires ne peut pas changer le comportement. Les quatre
chaînes de qualité le confirment néanmoins, lancées sur le worktree après documentation :

| Contrôle | Résultat |
|---|---|
| `tsc --noEmit` (type-check) | ✅ exit 0 |
| `eslint .` (lint) | ✅ 0 erreur (1 *warning* préexistant dans un test non touché, `game-realtime.test.ts`) |
| `vitest run` (tests) | ✅ **53 fichiers, 259 tests** verts |
| `next build` (build) | ✅ build complet, table des routes émise |

## Méthode

Documentation répartie par répertoire sur des sous-sessions (lib/api, lib, composants ui/jeu/
dashboard/landing/auth/profil, écrans `app/*`), chacune contrainte à **n'insérer que des blocs
`/** */`** au-dessus des exports, puis contrôle mécanique central (points 1–3 ci-dessus) et
chaîne de qualité complète. Style maison respecté (`docs/CODE.md` § « Documenter le code ») :
en français, le *pourquoi* et la provenance des données, ce que l'interface **ne fait pas**
(la décision reste côté serveur), et pour un écran la maquette reproduite (`docs/UI-UX.md`).

## Limites

- `scripts/doc-coverage.py` (outil de mesure) n'est pas versionné : il reste dans le worktree
  pour une reprise éventuelle. Sa logique est décrite ci-dessus.
- Les symboles **non exportés** (helpers internes, sous-composants) n'étaient pas dans le
  périmètre ; beaucoup portent déjà un commentaire de conception.
