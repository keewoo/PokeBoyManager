# fix-marqueur-recompenses — marqueur de règle normalisé pour la règle des Prix

> Lot **hors plan** demandé par JF le 01/10/2026 (« Oui, petit lot »). Aucune entrée dans
> `roadmap.json` ; `suivi.py`/`etat.json` non touchés.

## Résumé

La règle des Prix (combien de récompenses l'adversaire prend en mettant K.O. une carte) se
déduisait du **suffixe du nom** (`pbm_api.ingame.rules.prize_rule_of`, ancienne version). Deux
catégories en souffraient (R-13.7) :

- une **Méga-Évolution Pokémon ex** (série Méga-Évolution, 2025) finit par « ex » → l'ancien code
  disait **2** au lieu de **3** ;
- une **TAG TEAM** finit par « GX » → **2** au lieu de **3**.

On normalise désormais, **une fois pour toutes à l'import**, vers un **marqueur de règle** du
vocabulaire du moteur (`pbm_game.combat.fin.MARQUEUR_RECOMPENSES`), stocké dans une nouvelle colonne
`cards.prize_marker`. `prize_rule_of` lit ce marqueur, **plus jamais le nom**, et le nombre de
récompenses vient d'une **seule** table (copie d'`apps/api` tenue égale à celle du moteur par un
test de parité). Un marqueur **inconnu** donne « récompenses non déterminées », jamais un nombre
deviné (R-13.4/R-15.22).

## Livrables

| Fichier | Rôle |
|---|---|
| `apps/api/src/pbm_api/catalog/prize_marker.py` | **la fonction pure** `normalized_prize_marker(name, supertype, rule_marker)` — refuse de deviner |
| `apps/api/src/pbm_api/ingame/rules.py` | `prize_rule_of(marker, supertype)` ; `PRIZES_BY_MARKER` (copie du moteur) + libellés |
| `apps/api/src/pbm_api/models/catalog.py` | colonne `Card.prize_marker` (String(16), nullable) |
| `apps/api/src/pbm_api/catalog/import_service.py` | remplissage de `prize_marker` à chaque import |
| `apps/api/migrations/versions/e7c2a9f14b63_card_prize_marker.py` | ajout colonne **non destructif** + **remplissage des cartes existantes** dans la migration |
| `apps/api/src/pbm_api/insights_batch/runner.py`, `ingame/service.py` | lisent `card.prize_marker` |
| `apps/api/tests/test_prize_marker.py` | classification (vraies cartes citées) + **parité avec le moteur** |
| `apps/api/tests/test_ingame_rules.py` | règle des Prix bout en bout (vraies cartes) ; ancien comportement retiré |
| `docs/ARCHITECTURE.md` | la colonne et sa règle (section catalogue + règle des Prix) |

## Comment la classification tranche, et pourquoi le nom seul ne suffit pas

Mesuré sur `pbm_catalogue_ref` (22 169 cartes, **identique à la PROD** par `tcgdex_id`), le couple
(`cards.rule_marker`, nom) distingue chaque catégorie de R-15. Le `rule_marker` est le **suffixe
TCGdex en français** : `ESCOUADE`=TAG TEAM, `TURBO`=BREAK, `Niveau Sup`=LV.X, `MÉGA`=M Pokémon-EX
(ère XY), `LÉGENDE`, `ex`/`EX`/`V`/`GX`/`VMAX`, ou `SP`/`Primo`/`Restauré`/`Bébé` pour des Pokémon
**ordinaires**, sinon NULL. On **croise** toujours les signaux là où le suffixe tromperait
(R-13.7) : une Méga-Évolution ex se reconnaît à son **préfixe** « Méga » (pas à « ex »), une TAG
TEAM à son **jointeur** « et »/« & » (pas à « GX »).

⚠️ Le `rule_marker` est **lacunaire** : ~60 Pokémon à Rule Box ont `rule_marker` NULL alors que
leur nom porte la désignation (`Sulfura ex`, `Mewtwo et Mew GX`, `Zarbi V`, `Évoli Radieux`,
`Diancie ◇`, `Entei ☆`…). Le nom est donc un **repli** nécessaire — jamais utilisé seul là où il
tromperait. La colonne `stage` n'existe même pas dans la base de référence : elle n'a pas été
nécessaire, (nom, `rule_marker`) suffit. **Aucun champ TCGdex supplémentaire n'a eu besoin d'être
ajouté à l'import.**

## Preuve chiffrée — distribution sur `pbm_catalogue_ref` (22 169 cartes, 01/10/2026)

Classement de **toutes** les cartes par la fonction livrée (dump TSV `name|supertype|rule_marker`
→ `normalized_prize_marker`) :

| marqueur | cartes | | marqueur | cartes |
|---|---:|---|---|---:|
| `ordinaire` | 15 305 | | `vstar` | 95 |
| *(hors Pokémon → NULL)* | 3 387 | | `m_pokemon_ex` | 89 |
| `ex` | 1 201 | | `lv_x` | 61 |
| `v` | 607 | | `break` | 37 |
| `gx` | 472 | | `etoile` | 24 |
| `pokemon_ex` | 338 | | `v_union` | 24 |
| `vmax` | 210 | | `legende` | 20 |
| `mega_ex` | **148** | | `prisme_etoile` | 16 |
| `tag_team` | **119** | | `radiant` | 16 |

- **Cartes non classées (`inconnu`) : 0.** Toutes les cartes à Rule Box du catalogue sont rangées.
- **Cartes mal rangées en `ordinaire` alors que le nom porte une désignation : 0** (garde du
  script de preuve).
- Somme des marqueurs Pokémon = 18 782 = nombre exact de Pokémon du catalogue (`supertype` =
  « Pokémon »). Les 3 387 NULL = Dresseurs (2 873) + Énergies (514).
- Les **148 `mega_ex`** et **119 `tag_team`** sont précisément les cartes que l'ancien code sous-
  comptait à 2 au lieu de 3.

## Écarts / décisions

- **Pas de dépendance uv vers le moteur** : `apps/api` et `apps/game` ne partagent pas de
  workspace. On garde donc dans `apps/api` une **copie** de la table du moteur, tenue **égale** par
  `test_prize_marker.py::test_prizes_table_matches_engine` (lit le source du moteur en AST + compare).
  Si l'une bouge sans l'autre, la CI casse. C'est la voie « copie gardée égale » explicitement prévue.
- **Tera ex** est indistinct d'un `ex` dans les données stockées (même nombre, 2) : classé `ex`. Le
  marqueur `tera_ex` du moteur reste valide et testé (donne 2).
- **`rule_marker` n'a pas changé de sens** : il garde le suffixe brut de TCGdex ; ses lecteurs
  (`decks/stats.py`, `decks/service.py` : « carte spéciale » = `rule_marker` présent) sont inchangés.
- La base de référence est en **schéma ancien** (pas de colonne `stage`) : la preuve a donc été
  calculée sans `stage` — ce qui confirme que la classification n'en a pas besoin.

## Reste à faire

- **À livrer en PROD avec la prochaine livraison** (par devAI, la PROD restant manuelle) : la
  migration `e7c2a9f14b63` est **non destructive et rejouable** et **remplit les cartes existantes
  elle-même** — elle s'applique donc sans intervention au prochain `alembic upgrade head`. Après
  livraison, l'onglet « En jeu » affichera 3 Prix pour les Méga-Évolution ex et les TAG TEAM.
- Le lot `j-cartes-pokemon` (qui part juste après) lira `cards.prize_marker` pour charger les
  cartes dans le moteur : la donnée est désormais juste et complète (0 inconnu).
