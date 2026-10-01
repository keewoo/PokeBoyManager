# Compte rendu — `j-tests-regles`

**Batterie de cas de règles : la table qui dit si le moteur a raison.**
Palier 8 · piste Qualité & exploitation · couloir J-MOT (devAI) · jalon J1.

## Résumé

Le moteur `pbm_game` avait, depuis `j-regles-reference`, une table **documentaire**
(`cas-de-regles.yaml`) qui nomme pour chaque règle un cas qui la vérifie — mais sans état
d'entrée ni résultat : rien n'était **exécuté**. Ce lot livre la **batterie exécutable** : des
cas écrits en données (état de départ, action ou appel de fonction, résultat attendu, règle
`R-x.y` citée) **rejoués contre le vrai moteur** en CI, un rapport de couverture par règle, et une
garde qui **fait échouer la CI** si une règle du corpus n'a aucun cas.

Un cas se lit et s'écrit **sans toucher au code du moteur** : l'exécuteur est le seul code, les cas
sont des YAML. C'est ce qui permettra de modifier le moteur dans six mois sans tout casser en
silence.

## Livrables

- **Paquet `pbm_game.cas`** (pur, sans E/S, réutilisable par `j-simulation-bots`) :
  - `constructeur.py` — `construire(spec)` : une description concise d'un état → un `EtatPartie`
    réel + sa table `fiches` (PV/récompenses, D9) ; `trouver_graine` : une graine qui produit des
    pile ou face voulus (cas déterministes).
  - `executeur.py` — `executer(cas)` : rejoue un cas contre le moteur et vérifie l'attendu, ou
    lève `EchecCas`. 9 opérations : `appliquer` (actions journalisées), `degats`, `compteurs`,
    `etat`, `recompenses`, `cout`, `legalite`, `invariants`, `rng`.
  - `couverture.py` — `rapport(...)` : quelles règles ont un cas, lesquelles n'en ont aucun, et le
    contrôle des exceptions (périmées, hors corpus).
- **210 cas exécutables** dans `docs/jeu/cas-executables/*.yaml` (dégâts 37, états 28, checkup 16,
  ko-récompenses 30, machine-tour 26, banc 21, coût 16, légalité 16, invariants 12, rng 8).
- **`docs/jeu/couverture-exceptions.yaml`** — 15 règles non exécutables au J1 (méta sur le corpus,
  mécaniques non implémentées), **chacune justifiée**.
- **Tests CI** (job `game`, exécutés par `pytest`) :
  - `test_cas_executables.py` — exécute les 210 cas, exige ≥ 200, et **se mord lui-même** (un
    attendu faux, une opération inconnue, une erreur attendue absente font échouer l'exécuteur).
  - `test_couverture_regles.py` — **la garde** : aucune règle sans cas ni exception ; aucune
    exception périmée ou hors corpus ; chaque exception justifiée ; plancher de 90 règles couvertes
    en exécutable.
- **Doc** : `docs/jeu/CAS-EXECUTABLES.md` (format des cas et de l'exécuteur) ; renvois mis à jour
  dans `REGLES.md` et `cas-de-regles.yaml`.

## Preuves

- `cd apps/game && UV_PYTHON=3.12 uv run ruff check .` → *All checks passed!*
- `UV_PYTHON=3.12 uv run pytest -q` → **551 passed** (dont les 210 cas de la batterie + la garde
  de couverture + les auto-tests de l'exécuteur + les suites existantes du moteur).
- Couverture : **137 règles définies**, **100 couvertes par un cas exécutable**, 119 par l'union
  exécutable+documentaire, les 18 restantes par 15 exceptions justifiées → **0 règle sans cas**,
  **0 exception périmée**, **0 exception hors corpus**.
- La CI GitHub (job `game`) fait foi : elle exécute `ruff check .` + `pytest -q` dans `apps/game`,
  qui collecte les deux nouveaux fichiers de test. Aucune dépendance ajoutée (pyyaml était déjà une
  dépendance de dev) → `uv.lock` inchangé.

## Critères d'acceptation

- [x] Au moins 200 cas verts, tous rattachés à une règle du corpus → **210 cas, 100 règles**.
- [x] Aucune règle du corpus sans cas (ou exception écrite et justifiée) → garde verte, 15
  exceptions justifiées pour les mécaniques non implémentées au J1.
- [x] Un cas se lit et s'écrit sans toucher au code du moteur → YAML déclaratif, format documenté.
- [x] Un test qui échoue sans le changement et passe avec → les cas rougissent si le moteur
  change ; `test_executeur_mord_sur_un_attendu_faux` prouve que l'exécuteur n'est pas complaisant.
- [x] CI GitHub Actions verte sur la PR (elle fait foi).

## Écarts au plan

- La table documentaire `cas-de-regles.yaml` **n'a pas été transformée** en cas exécutables :
  elle reste un **plan de couverture** (un cas = une règle nommée), et les cas exécutables vivent à
  part. C'est plus propre — la table reste lisible d'un coup d'œil pour la couverture, les cas
  exécutables portent le détail — et les deux ensembles sont traités par la même garde.
- Les cas exécutables couvrent **100 des 137 règles**. Les 37 non couvertes en exécutable le sont
  par la table documentaire (R-5.4/5.5, évolution R-7.2/7.3, cartes particulières R-15.x…) ou,
  pour 15 d'entre elles, par une **exception justifiée** (règles méta R-1.x, mise en place/mulligan
  R-4.6/R-16.9, évolution R-7.1/7.4, Supporter R-17.4, effets de cartes R-9.3/R-12.3/R-15.11/R-17.10,
  Outil garanti par construction R-3.7, phase principale libre R-5.3). Un effet non implémenté
  n'est jamais « testé » pour de faux (D9).

## Reste à faire (lots suivants)

- Quand une mécanique aujourd'hui en exception arrive (évolution, Supporter, effets de cartes,
  mise en place/mulligan), **retirer sa ligne de `couverture-exceptions.yaml` et ajouter ses cas** :
  la garde refuse une exception périmée, ce qui force à le faire.
- `j-simulation-bots` (débloqué par ce lot) peut réutiliser `pbm_game.cas.construire` pour fabriquer
  des états de départ et `executer` pour vérifier des invariants au fil des parties.
- Tout lot de moteur doit désormais **ajouter ses cas** : une mécanique nouvelle sans cas de règle
  est un lot inachevé (consigne portée dans `CAS-EXECUTABLES.md`).
