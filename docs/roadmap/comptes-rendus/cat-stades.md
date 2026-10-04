# cat-stades — le stade de chaque Pokémon du catalogue

Lot **hors plan**, premier du gros chantier des effets (« go pour le gros chantier effet », JF,
04/10/2026). Ouvert après le constat du 03/10 : en remplissant la collection de JF, la PROD ne
compte qu'une poignée de cartes jouables. L'hypothèse de départ : des Pokémon sans `cards.stage`
que `definition_depuis_card` bloque à raison (R-7), et un repli anglais qui comblerait le trou.

**L'enquête a déplacé la cause.** Le catalogue de référence a déjà ses stades ; le repli anglais ne
récupère rien ; et la vraie cause des cartes injouables en PROD est que la chaîne d'import n'a jamais
rétro-rempli les cartes déjà chargées. Ce compte rendu dit ce qui a été mesuré, décidé et livré.

## Mesures sur `pbm_catalogue_ref` (chimera, 04/10/2026)

22 653 cartes au total, dont **19 215 Pokémon**. Distribution de `stage` (Pokémon) :

| stage | cartes | | stage | cartes |
|---|---|---|---|---|
| Base | 10 200 | | VMAX | 210 |
| Niveau 1 | 5 404 | | MÉGA | 94 |
| Niveau 2 | 1 809 | | VSTAR | 94 |
| **(vide)** | **806** | | Niveau Sup | 67 |
| Basic | 266 | | TURBO | 37 |
| Stage1 | 121 | | V-UNION | 20 |
| Stage2 | 63 | | Restauré | 13 / Bébé 7 / LEVEL-UP 4 |

- **Stade jouable** (reconnu par `is_ordinary_stage` — Base/Basic/Niveau 1-2/Stage 1-2) :
  **17 863 / 19 215 (93,0 %)**. Ces cartes passent la porte du stade en jeu.
- **Sans stade** : **806 (4,2 %)**.
- **Stade « spécial »** non géré par le moteur (VMAX, VSTAR, MÉGA, Niveau Sup, TURBO, V-UNION,
  Restauré, Bébé, LEVEL-UP) : **527** — mécaniques non implémentées, bloquées à raison.

## Découverte 1 — le repli anglais ne récupère rien (vérifié carte par carte)

Les **806** Pokémon sans stade ont été interrogés **un par un** sur `api.tcgdex.net/v2/en` :
TCGdex renvoie `stage = null` pour **les 806 en anglais** comme en français. Répartition par
marqueur : GX 437, EX 168, ex 70, ESCOUADE (TAG TEAM) 95, V 4 — soit **774 cartes à Rule Box**,
bloquées de toute façon par leur marqueur — et **32 promos** sans Rule Box (ex. Détective Pikachu).

**Conséquence** : le repli anglais du stade **recouvre 0 carte** sur le catalogue actuel. TCGdex
n'attribue tout simplement pas de stade aux EX/GX/TAG TEAM, dans aucune langue. On ne devine pas
(pas de déduction depuis le nom ni les PV, R-7) : ces 806 restent vides et comptées.

Le repli a quand même été implémenté (ci-dessous) : c'est le comportement correct si un jour le
catalogue `fr` prend du retard sur le `en` sur ce champ, et le lot le demandait explicitement.

## Découverte 2 — la vraie cause des cartes injouables en PROD

La chaîne flotte **transporte bien `stage`** depuis le 02/10 (`export_cards.sql` /
`import_weekly.sql`, lot `cat-textes-effets`). Mais `import_weekly.sql` est **INSERT-ONLY** : il
n'a jamais touché aux cartes **déjà** en PROD. Or six colonnes (`energy_type`, `element_type`,
`stage`, `prize_marker`, `trainer_type`, `effect`) n'existaient pas dans la chaîne avant le 02/10.

**Toutes les cartes PROD chargées avant cette date sont donc restées `NULL`** sur ces colonnes, et
`definition_depuis_card` bloque un Pokémon sans `stage` **ou** sans `prize_marker`. C'est la cause
mesurée des très rares cartes jouables en PROD — pas un trou de la base de référence, pas l'import.

## Ce qui a été livré

1. **Repli anglais du stade à l'import** (`catalog/import_service.py`). Le stade est pris dans la
   langue source, **sinon en anglais**, borné aux Pokémon réellement sans stade et pas déjà
   anglais (on ne tire que les cartes concernées sur le lien bridé de chimera). Jamais pour écraser
   un stade présent ; une carte sans stade nulle part reste `None`. Deux compteurs au rapport :
   `cards_stage_from_en_fallback` et `cards_pokemon_without_stage` — le repli et les trous sont
   **mesurables** d'un import à l'autre, jamais silencieux.
2. **Rétro-remplissage PROD** (`infra/fleet/backfill_cards.sql`). Le « geste PROD distinct » que
   `import_weekly.sql` nommait sans le fournir. UPDATE des cartes existantes, rapproché par
   `tcgdex_id`, sur les six colonnes — mais **uniquement là où la PROD est `NULL`** et la référence
   renseignée (`COALESCE` + garde `WHERE`). Jamais d'écrasement, colonne légitimement vide laissée
   vide, **idempotent**. Lancé **une fois** par la livraison (doc `docs/LIVRAISON.md`).
3. **Rapport de complétude** : section « Stade d'évolution des Pokémon » ajoutée au **générateur**
   (`catalog/completeness.py` + `scripts/generate_completeness_report.py`) et `COMPLETUDE.md`
   régénéré — pas une édition à la main d'un fichier généré (qui serait effacée au prochain run).

## Preuve chiffrée

- **Catalogue de référence** : stade jouable **17 863 / 19 215** (inchangé par ce lot — les stades
  y sont déjà ; le repli anglais ajoute 0, mesuré). 806 sans stade, confirmés stageless en `en`.
- **Rétro-remplissage, validé le 04/10 sur une base clonée de la référence** (50 Pokémon simulés
  « pré-02/10 », stade + marqueur + type vidés) :

  | | stage NULL | prize_marker NULL | element_type NULL |
  |---|---|---|---|
  | avant backfill | 856 | 49 | 54 |
  | après backfill | **806** | **0** | **4** |

  Les 50 cartes retrouvent leur stade et leur marqueur ; les 4 `element_type` réellement vides dans
  la référence restent vides (jamais inventés) ; un témoin `prize_marker` déjà posé n'est **pas**
  écrasé tout en récupérant son stade. C'est le chiffre qui compte pour le jeu : en PROD, le même
  backfill rendra jouables toutes les cartes qui n'étaient bloquées que par ces colonnes `NULL`.

## Tests (`apps/api/tests/test_import_service.py`)

- `test_import_repli_stade_anglais` : stade présent seulement en anglais → repli appliqué
  (`cards_stage_from_en_fallback == 1`) ; carte sans stade dans aucune langue → reste `None` et se
  compte (`cards_pokemon_without_stage == 1`).
- `test_import_repli_stade_borne_aux_cartes_sans_stade` : `Stage1` (sans espace) déjà présent en
  source → conservé tel quel, ne pollue pas `rule_marker`, **aucun** appel anglais inutile.

26 tests verts dans `test_import_service.py` ; 75 verts avec `test_catalog_completeness`,
`test_prize_marker`, `test_jeu_catalogue`. (La base `pbm_test` de chimera est en retard d'une
migration — `users.coach_actif` manquant — ce qui fait échouer des tests sans rapport, uploads/jeu ;
la CI migre à neuf et fait foi.)

## Ce qui reste à faire (hors de ce lot, signalé)

- **La livraison** doit lancer `backfill_cards.sql` une fois, puis vérifier le compte de Pokémon
  sans stade côté PROD. Ce lot ne touche pas la PROD.
- Les stades « spéciaux » (VMAX, VSTAR, MÉGA, LEVEL-UP/Niveau Sup, Bébé, Restauré) et les EX/GX/TAG
  TEAM restent bloqués : ce sont des mécaniques du moteur à décider (DJ*), pas un trou de catalogue.
  « Bébé » et « Restauré » (20 cartes) sont conceptuellement des Pokémon de base ; les rendre
  jouables serait une **décision de règle**, pas une déduction à prendre seul — laissé à JF.
