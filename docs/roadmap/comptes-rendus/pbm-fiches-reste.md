# Compte rendu — lot `pbm-fiches-reste`

**Les 4 434 cartes sans fiche, couvertes en RÈGLES DE JEU SEULES (sans anecdotes).**

Le ciblage 80 % (`pbm-insights-ciblage-large`) avait laissé 4 434 cartes sans fiche (surtout
Communes, Peu communes, Rares). Décision de JF (22/09) : les couvrir **sans anecdotes, avec
seulement les règles de jeu** — le modèle met en forme les données du catalogue, il n'invente rien.
Le champ des anecdotes reste vide (à remplir plus tard si JF le décide).

## Ce qui a été livré (code, branche `roadmap/pbm-fiches-reste`)

| Fichier | Rôle |
|---|---|
| `apps/api/src/pbm_api/insights_batch/large_generation.py` | Ajout d'une variante **règles seules** : schéma `RulesOnlyExtraction` (par carte : `card_ref`, `game_rules` — **aucune anecdote**), `build_rules_only_prompt` (uniquement les données de jeu du catalogue, **aucun contexte wiki**), `parse_rules_only_result` (anti-mélange par `card_ref` repris à l'identique). `RULES_ONLY_PROMPT_VERSION = "rules-v1"`. |
| `apps/api/scripts/generate_rules_only.py` | Driver : sélection des cartes non couvertes (catalogue moins TSV du lot précédent), groupage par extension, lots Anthropic (Message Batches −50 %, Haiku 4.5), plafond dur 15 €, grand livre de reprise, ré-essai carte par carte des paquets en échec, sortie TSV `anecdotes=[]`. |
| `apps/api/tests/test_insights_batch_large_generation.py` | +6 tests (schéma sans anecdotes, prompt sans wiki, anti-mélange règles-seules). 22 tests verts. |

Import inchangé : le TSV a le **même format** que le lot précédent (9 colonnes), seule la colonne
`anecdotes` vaut `[]` au lieu d'anecdotes peuplées. `infra/fleet/import_insights.sql` et
`import.sh` du lot précédent sont réutilisés tels quels.

## Pourquoi c'est peu cher — et pourquoi aucune source wiki

Le coût du lot précédent (24,92 € pour 17 735 cartes ≈ 1 750 jetons d'entrée/carte) venait de la
**lecture des pages wiki** pour sourcer les anecdotes. Ici, **aucune source externe n'est
récupérée** : le prompt ne contient que les données de jeu déterministes (attaques, coûts, talents,
faiblesses/résistances, PV, retraite, légalités, règle des Prix). Entrée mesurée ≈ 340 jetons/carte,
sortie ≈ 163 jetons/carte.

## Où ça tourne — même écart assumé que le lot précédent

**La génération tourne sur devAI**, pas sur chimera, pour la raison de sécurité tranchée à la
mesure et maintenue : *la clé personnelle d'Aymeric ne quitte pas devAI* (chimera n'a aucune clé).
La Message Batches API exige la clé sur la machine appelante ; « appeler depuis chimera »
impliquerait d'y copier la clé, ce que l'hygiène de secret interdit. Le seul « lourd » réellement
proscrit est la machine qui **sert** (`kailo-srv`/PROD) — pleinement respecté : rien n'y a tourné,
elle n'a fait que recevoir un TSV (COPY + upsert, aucun appel IA). La clé a été lue depuis le
fichier chmod 600 via `--key-file`, **jamais** en variable d'environnement, jamais en argument,
jamais journalisée (fuite vérifiée absente des logs, TSV, grand livre).

## Génération et import — mesures réelles (2026-09-22, Haiku 4.5, Batch −50 %)

| | |
|---|---|
| Cartes couvertes ce lot | **4 434 / 4 434** (3 604 Pokémon, 622 Dresseur, 208 Énergie) |
| Coût réel | **2,40 € / 15 €** (2,75 $, taux USD→EUR 1,146 ; 0,00054 €/carte) |
| Couverture finale du catalogue | **22 169 / 22 169 = 100,0 %** |
| Paquets en échec (mélange) | 6 sur 218, **tous récupérés** par ré-essai carte par carte (126 cartes) — 0 carte perdue |
| Anecdotes | aucune (`[]`), par décision — champ laissé vide pour plus tard |
| Règles de jeu vides | 0 |
| Temps de génération | ≈ 11 min (mesure 100 cartes + gros lot de 4 334) |

Import par jointure `cards.tcgdex_id` (`import.sh both`) : **base de référence chimera**
(`pbm_catalogue_ref`, 4 434 reçues, 0 sans carte) **et PROD** (`pokeboy_prod`, 4 434 reçues, 0 sans
carte, garde-fou HTTP vert avant/après). Après import : les deux bases comptent **22 169 fiches,
toutes avec règles de jeu**.

## Vérification « fiche sans appel IA »

Contrôle sur PROD d'une carte règles-seules (`2012bw-1`, Lianaja) : `anecdotes = []`,
`in_game_study` peuplé (320 caractères), `game_study_cached_until` et `cached_until` **frais**
(dans le futur, TTL 180 j), `game_study_source_model = anthropic:claude-haiku-4-5:batch:rules-v1`.

La garantie « pas d'appel IA » est **structurelle** : `pbm_api/ingame/service.py` `_study_fresh()`
et `pbm_api/insights/service.py` `_fresh()` renvoient le cache **avant** toute logique de
credential/IA. L'onglet « En jeu » se lit donc sur `in_game_study` sans clé IA ; l'onglet
anecdotes, avec `anecdotes = []` et un cache frais, se comporte en **cache négatif** (vide, aucun
appel) — exactement le comportement attendu par la mission.

## Reste à faire

Rien pour la couverture : le catalogue est à 100 %. Les anecdotes des 4 434 cartes restent vides
(`[]`) ; elles pourront être générées plus tard si JF le décide (le prompt/schéma complet existe
déjà dans `large_generation.build_large_prompt`). Une carte redevient candidate à une passe
anecdotes le jour où `RULES_ONLY_PROMPT_VERSION` change ou par une sélection dédiée.
