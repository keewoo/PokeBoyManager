# Compte rendu — `fix-marqueur-stades`

**Type** : correctif hors plan, ouvert dans la nuit du 01→02/10/2026 sur ordre de JF.
**Branche** : `roadmap/fix-marqueur-stades`, créée depuis **`b0df8ae`** (la release en PROD), pas
depuis `main` (qui porte déjà d'autres lots à ne pas livrer avec ce correctif).
**Machine** : worktree et validation sur **chimera** (`~/dev/wt-fix-marqueur-stades`).

## Le défaut (constaté en PROD le 01/10 à 23h50, release `20261001-234045`)

**564 cartes** de la base PROD portaient `cards.rule_marker` = `Stage1` / `Stage2` (sans espace).
L'import ne reconnaissait comme stades ordinaires que `stage 1` / `stage 2`
(`ORDINARY_STAGES`, comparaison en minuscules uniquement) : `Stage1`/`Stage2` étaient donc recopiés
dans `rule_marker` comme s'ils portaient une règle spéciale. Conséquences en cascade :

- `normalized_prize_marker` (`catalog/prize_marker.py`) ne reconnaissait pas `Stage1`/`Stage2` et
  les rangeait en `inconnu` → la fiche « En jeu » affichait « Récompenses non déterminées » au lieu
  de **1**, et le moteur les aurait refusées (R-15.22) ;
- `decks/stats.py` (`if c.rule_marker …`) les comptait comme cartes à Rule Box.

Le catalogue de chimera (`pbm_catalogue_ref`) ne portait pas ces valeurs `Stage1`/`Stage2` (il a
`stage`/`suffix` propres), d'où le trou : la preuve chiffrée « 0 inconnu » du lot
`fix-marqueur-recompenses` ne pouvait pas voir ce cas.

## Le correctif

### 1. Une seule normalisation des stades, partagée

Ajout dans `catalog/prize_marker.py` (module pur, déjà importé par l'import et par la migration de
remplissage) de **`is_ordinary_stage(value)`** : compare sans casse **et sans espaces ni tirets**
(`_RE_STAGE_SEP = re.compile(r"[\s-]+")`), contre l'ensemble normalisé
`{base, basic, niveau1, niveau2, stage1, stage2}`. Donc `Stage1` = `stage 1` = `Stage-1`,
`Basic`/`Base`, `Niveau 1`/`Niveau 2`.

- `catalog/import_service._rule_marker` : `ORDINARY_STAGES` (set littéral) supprimé, remplacé par
  `not is_ordinary_stage(stage)` → un stade ordinaire ne finit **jamais** dans `rule_marker`.
- `catalog/prize_marker.normalized_prize_marker` : la branche « Pokémon ordinaire » reconnaît
  désormais aussi `is_ordinary_stage(rm)` → un stade ordinaire mal rangé donne `ordinaire`, jamais
  `inconnu`. (Placé en fin de classification : aucune Rule Box réelle ne peut être captée par là.)

Une seule définition de « stade ordinaire », donc l'import et la classification ne peuvent plus
diverger comme ils l'ont fait.

### 2. Migration de correction des données (additive, rejouable)

`migrations/versions/a3f9c2e5b1d4_fix_marqueur_stades.py` (down_revision `e7c2a9f14b63`, le head en
PROD — head alembic resté **unique**). Pour chaque ligne `cards` dont `rule_marker` est un stade
ordinaire : `rule_marker` → NULL et `prize_marker` **recalculé** par la même fonction pure sur le
`rule_marker` vidé. Elle ne touche à **rien d'autre** (une vraie Rule Box reste intacte). La
décision par ligne est factorisée dans `prize_marker.corrected_stage_row` — la **même** fonction
que teste la suite, sans base. `downgrade()` est un no-op **explicite** (le libellé brut `Stage1`
n'est pas reconstituable depuis NULL ; migration additive, pas annulable). Rejouable : un 2ᵉ
passage ne trouve plus aucun stade dans `rule_marker`.

### 3. Tests (échouent sans le correctif)

`tests/test_prize_marker.py` :
- `test_ordinary_stage_in_rule_marker_is_ordinary` : `Stage1`, `Stage2`, `Stage 1`, `stage-2`,
  `Basic`, `Niveau 1`, `Niveau 2`, `Base` → `ordinaire` (échoue avant : rendait `inconnu`).
- `test_is_ordinary_stage_normalizes_case_and_separators` : casse/espaces/tirets ; `VMAX`, `ex`,
  `GX`, `Niveau Sup`, inconnu → **pas** un stade.
- `test_migration_corrects_stage_row_and_leaves_vmax_intact` : `Stage1` → `(None, "ordinaire")` ;
  `VMAX` et `ZX-NOUVEAU` → `None` (non touchés).
- `test_unknown_rule_box_refuses_to_guess` (déjà présent) : une vraie Rule Box inconnue reste
  `inconnu`.

Ces tests référencent `is_ordinary_stage`/`corrected_stage_row` (absents de l'ancien code) → ils
échouent sans le correctif.

### 4. Preuve — cas PROD reproduit sur base jetable, avant/après la migration réelle

Base `pbm_fix_stades_proof` montée au schéma **pré-correctif** (`alembic upgrade e7c2a9f14b63`),
semée de 4 cartes reproduisant la PROD, puis `alembic upgrade head` (applique a3f9c2e5b1d4) :

```
AVANT (état PROD reproduit)              APRÈS (migration appliquée)
  Pikachu          rule_marker=Stage1       prize_marker=inconnu   →  rule_marker=None  prize_marker=ordinaire
  Herbizarre       rule_marker=Stage2       prize_marker=inconnu   →  rule_marker=None  prize_marker=ordinaire
  Astronelle VMAX  rule_marker=VMAX         prize_marker=vmax      →  rule_marker=VMAX  prize_marker=vmax      (intacte)
  Truc ZX          rule_marker=ZX-NOUVEAU   prize_marker=inconnu   →  rule_marker=ZX-NOUVEAU prize_marker=inconnu (vraie Rule Box inconnue : reste inconnu)
  cartes 'inconnu' : 3                      →  cartes 'inconnu' : 1
```

Base jetable supprimée après la preuve.

## Validation sur chimera

- `uv run ruff check` sur les 5 fichiers touchés : **All checks passed**.
- `uv run alembic heads` : **`a3f9c2e5b1d4` (head)** — unique.
- `alembic upgrade head` sur une base vide : les deux migrations passent (backfill à 0 ligne).
- `uv run pytest tests/test_prize_marker.py tests/test_import_service.py` : **59 passed**.
  (Le test DB `pbm_v2_catalogue_complet_test` était resté à `b2d4f6a8c0e1` ; migré à head avant
  pytest, comme le fait la CI.)

La CI GitHub Actions (passage `push` sur `roadmap/**`, workflow « CI ») fait foi.

## Livraison

Le commit **de tête de la branche** (basé sur `b0df8ae`) part en PROD — **pas** `main`. La
migration `a3f9c2e5b1d4` s'applique à la livraison et remet les 564 cartes en cohérence. Fusion
dans `main` faite après CI verte, sous le verrou `pbm-merge.lock`.
