# Compte rendu — `cat-textes-effets`

**Le texte d'effet des Dresseurs et des Énergies dans le catalogue** · lot hors plan (vague des 4
validée par JF le 02/10/2026) · préalable au chantier des effets du jeu · exécuté sur **chimera**
(WSL Ubuntu-24.04), piloté depuis **devAI**.

## Résumé

Avant ce lot, **2 766 des 2 873 Dresseurs** du catalogue n'avaient ni `attacks` ni `abilities` :
leur **texte d'effet n'était pas stocké**, pas plus que celui des Énergies spéciales ni le
sous-type des Dresseurs. Tout le chantier des effets du jeu (`j-effets-dsl`,
`j-effets-catalogue-compilation`, `j-cartes-objets`/`-supporters`/`-stades`/`-outils`,
`j-cartes-energies`) part de ce texte — sans lui, aucune carte Dresseur ne peut être scriptée et la
règle D9 les refuserait toutes.

Deux colonnes additives ont été ajoutées à `cards` : **`effect`** (texte d'effet, TCGdex `effect`)
et **`trainer_type`** (sous-type de Dresseur, TCGdex `trainerType`). L'import les peuple par la voie
normale. La base de référence de chimera (`pbm_catalogue_ref`) a été **remise à `head`** puis
**réimportée** : le texte d'effet y est désormais présent pour **2 851 / 2 904 Dresseurs (98,2 %)**
et **178 / 185 Énergies spéciales (96,2 %)**. La chaîne flotte (`export_cards.sql`,
`import_weekly.sql`) transporte les nouvelles colonnes jusqu'à la PROD.

## Ce que porte chaque champ (vérifié sur `api.tcgdex.net`, 02/10/2026)

| Catégorie | `category` (fr/en) | sous-type | effet |
|---|---|---|---|
| Objet / Supporter / Stade / Outil / Machine Technique | Dresseur / Trainer | `trainerType` : "Objet"/"Supporter"/"Stade"/"Outil"/"Machine Technique" (fr), "Item"/"Supporter"/"Stadium"/"Tool"/"Technical Machine" (en) | `effect` |
| Énergie spéciale | Énergie / Energy, `energyType`="Spécial"/"Special" | — | `effect` |
| Énergie de base | Énergie / Energy, `energyType`="De base"/"Normal" | — | `None` (pas d'effet) |
| Pokémon | Pokémon | — | `None` (le jeu vit dans `attacks`/`abilities`) |

Comme `supertype` et `stage`, `effect` et `trainer_type` sont rangés **bruts** (deux langues
possibles via le repli fr→en de l'import) : c'est au lecteur du jeu de normaliser.

## Livrables

- **Modèle** (`apps/api/src/pbm_api/models/catalog.py`) : `Card.effect` (`Text`),
  `Card.trainer_type` (`String(32)`), toutes deux nullables.
- **Migration** `f3b8d1c6a927_card_effect_and_trainer_type` : additive (`add_column` × 2),
  `down_revision = c5f1a9e3b7d0` (tête précédente).
- **Import** (`catalog/import_service.py`) : `_upsert_card` range `detail.get("trainerType")` et
  `detail.get("effect")`. Une carte sans `effect` chez TCGdex reste `None` — jamais un texte
  inventé.
- **Complétude** (`catalog/completeness.py`, `scripts/generate_completeness_report.py`) : nouveau
  bloc « Texte d'effet des Dresseurs et des Énergies spéciales » dans `docs/catalogue/COMPLETUDE.md`
  (totaux, taux, détail par sous-type), taux calculés sur le **dénominateur de la catégorie**
  (`ratio_pct`), pas sur l'ensemble des cartes.
- **Chaîne flotte** (`infra/fleet/export_cards.sql`, `infra/fleet/import_weekly.sql`) : transportent
  désormais **six** colonnes jeu — `energy_type`, `element_type`, `stage`, `prize_marker`,
  `trainer_type`, `effect` — que la chaîne perdait jusque-là en silence (voir « Dette flotte »).
- **Tests** (`tests/test_import_service.py`) : doublure `EffectsTcgdexClient` (un Dresseur par
  sous-type + Énergie spéciale + Énergie de base + Dresseur sans texte) et trois tests
  (`test_import_stores_effect_text_and_trainer_subtype`,
  `test_import_leaves_effect_empty_when_tcgdex_has_none`,
  `test_completeness_counts_effect_text_honestly`). `uv run pytest tests/test_import_service.py
  tests/test_catalog_completeness.py` → **26 passed** ; `ruff check` propre.
- **Docs** : `docs/ARCHITECTURE.md` (section Catalogue + « Dette côté flotte » mise à jour),
  `docs/catalogue/COMPLETUDE.md` (régénéré).

## Preuve chiffrée (base de référence `pbm_catalogue_ref`, chimera)

**Avant** : alembic `216ae1bf9f95` ; colonnes `effect`/`trainer_type` absentes (ainsi que
`energy_type`/`element_type`/`stage`/`prize_marker`) ; 22 169 cartes, 2 873 Dresseurs, **0** texte
d'effet stocké (la colonne n'existait pas).

**Après** (migration vers `head` `f3b8d1c6a927` + réimport complet par la voie normale) :

| | total | avec texte d'effet |
|---|---|---|
| Dresseurs | **2 904** | **2 851 (98,2 %)** |
| Énergies spéciales | **185** | **178 (96,2 %)** |

Dresseurs par sous-type (total / avec effet) : Supporter 1 297 / 1 279 · Objet 885 / 862 · Outil
342 / 336 · Stade 236 / 234 · (sans sous-type) 124 / 121 · Stadium 7 / 6 · Item 6 / 6 · Machine
Technique 4 / 4 · Tool 3 / 3. (`trainer_type` renseigné pour **2 780 / 2 904** Dresseurs ; les 124
sans sous-type sont des cartes pour lesquelles TCGdex n'expose pas `trainerType`, dont 121 ont tout
de même un effet.)

Les **quatre colonnes jeu jusque-là absentes** de la base de référence sont aussi peuplées pour la
première fois (même réimport) : `element_type` 19 318 · `prize_marker` 19 215 · `stage` 18 510 ·
`energy_type` 491. Le réimport a aussi **créé 484 cartes** manquantes (surtout Pokémon TCG Pocket :
`A4`, `B1`, `me01`→`me05`…), portant le catalogue à **22 653 cartes**.

### Ce qui reste vide, et pourquoi (jamais masqué)

- **53 Dresseurs sans effet.** Les 53 `tcgdex_id` ont été re-vérifiés un à un sur
  `api.tcgdex.net` : **52 sont vides chez TCGdex** (champ `effect` nul), le dernier (`np-28`
  « Championship Arena ») est vide **en fr comme en en**. Ce sont des promos XY (`xyp`, 17),
  TCG Pocket (`B2a`, 10), kits du dresseur HGSS (`tk-hs-r`/`tk-hs-g`, 8+8), promos Nintendo
  (`np`, 4), rééditions anniversaire (`30th`/`30th-c`, 3+2) et Generations (`g1`, 1) : **trou
  réel de la source**, pas un défaut d'import.
- **7 Énergies spéciales sans effet** (`ex4-88`, `ex9-87`, `ex14-88`, `neo1-19`, `neo1-104`,
  `neo1-105`, `neo4-16`) : vides dans l'édition **fr** (langue source), mais **présentes en en**.
  C'est une **limite connue du repli de langue**, qui opère au niveau de l'*existence de la carte*,
  pas du *champ* — cohérent avec tous les autres champs de l'import. Les corriger demanderait un
  repli champ par champ (double fetch de chaque carte), coûteux sur le lien à ~250 ko/s de chimera
  pour 7 cartes anciennes ; non fait dans ce lot, signalé pour `j-cartes-energies`.

## Le chemin vers la PROD (chaîne flotte)

`export_cards.sql` et `import_weekly.sql` transportent maintenant les six colonnes jeu, dans le
**même ordre** des deux côtés (contrat du TSV, commenté dans les deux fichiers). ⚠️ L'import hebdo
est **insert-only** (« jamais d'UPDATE », garde-fou de la mission) : les cartes **déjà en PROD**
avant que ces colonnes ne circulent **ne sont pas rétro-remplies** par la chaîne — seules les cartes
**nouvelles** les portent. Rétro-remplir les cartes PROD existantes relève d'un geste PROD distinct
(manuel, décision JF) et n'est pas fait ici (le lot ne touche pas la PROD).

## Déroulé & mesures (chimera)

- Migration de `pbm_catalogue_ref` `216ae1bf9f95` → `head` : additive, a aussi créé les tables
  jeu/decks absentes de cette base restée en retard (sans incidence : l'export ne lit que
  `cards`/`sets`).
- Réimport complet (`scripts/import_full_catalogue.py`, FR+EN, concurrence 8) : **1 218 s**, 223
  extensions vues, 20 207 cartes mises à jour + 120 créées. 196 « erreurs » : 132 timeouts réseau
  **tous dans `A4`** (lien saturé en fin de course — données antérieures préservées, pas d'écrasement),
  25 pannes transitoires 500/502 de Pokémon TCG API (le `ptcg_id` existant n'est jamais effacé),
  39 « pas d'édition secondaire » (carte prise dans l'autre langue — sans conséquence).
- **Reprise ciblée** (`import_full_catalogue.py "A4,…,30th"`, 21 extensions) : **0 erreur**,
  2 496 cartes mises à jour + 364 créées → a fait passer les Dresseurs avec effet de 90,1 % à
  98,2 %. La reprise est la voie normale (idempotente, par `tcgdex_id`), pas un correctif ad hoc.
- Volume réseau réel bien en-deçà de ce que le lien encaisse (JSON de carte, quelques Ko pièce) :
  l'import complet est resté sur chimera, pas de bascule devAI nécessaire.

## Limites et suites

- Les 7 Énergies spéciales vides en fr / pleines en en (repli au niveau carte) — à traiter si
  `j-cartes-energies` en a besoin.
- Les 53 Dresseurs et les cartes sans `trainer_type` dépendent de TCGdex : un futur enrichissement
  de la source les comblera au prochain réimport, sans changement de code.
- Rétro-remplissage des colonnes jeu pour les cartes **déjà en PROD** : geste PROD distinct, non
  couvert par la chaîne insert-only.
