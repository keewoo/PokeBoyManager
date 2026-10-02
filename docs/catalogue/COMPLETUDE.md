# Rapport de complétude du catalogue

Généré le 2026-10-02T12:02:09.316331+00:00 — mission `v2-catalogue-complet` point 4.

## Vue d'ensemble

- Extensions : **203**
- Cartes : **22653**
- Noms FR : **22173** (97.9 %)
- Noms EN : **22551** (99.5 %)
- Cartes avec image officielle : **18750** (82.8 %)
- Cartes avec `ptcg_id` (rapprochement Pokémon TCG API) : **19065** (84.2 %)
- Cartes avec faiblesses ou résistances : **22534** (99.5 %)
- Cartes avec coût de retraite : **19182** (84.7 %)
- Cartes avec variantes connues : **22653** (100.0 %)
- Cartes avec au moins un prix relevé : **19676** (86.9 %)

## Texte d'effet des Dresseurs et des Énergies spéciales

Les Dresseurs (Objet, Supporter, Stade, Outil, Machine Technique) et les Énergies spéciales sont les seules cartes dont l'effet vit dans le champ `effect` (les Pokémon ont `attacks`/`abilities`, les Énergies de base n'ont pas d'effet). C'est le texte dont part le chantier des effets du jeu (lot `cat-textes-effets`).

- Dresseurs : **2904**, dont **2851** avec un texte d'effet (98.2 %)
- Énergies spéciales : **185**, dont **178** avec un texte d'effet (96.2 %)

Détail des Dresseurs par sous-type (un Dresseur sans texte chez TCGdex reste vide et se compte comme tel, jamais un effet inventé) :

| Sous-type | Total | Avec effet |
|---|---|---|
| Supporter | 1297 | 1279 |
| Objet | 885 | 862 |
| Outil | 342 | 336 |
| Stade | 236 | 234 |
| (sans sous-type) | 124 | 121 |
| Stadium | 7 | 6 |
| Item | 6 | 6 |
| Machine Technique | 4 | 4 |
| Tool | 3 | 3 |

## Extensions non rapprochées avec Pokémon TCG API

50 extension(s) sans une seule carte avec `ptcg_id` (absente de Pokémon TCG API, ou rapprochement raté — voir `catalog/reconciliation.py`) :

- `tk-bw-e` — BW Kit du dresseur (Minitaupe)
- `tk-bw-z` — BW Kit du dresseur (Zoroark)
- `jumbo` — Cartes Jumbo
- `A2` — Choc Spatio-Temporel
- `30th-c` — Collection Classique30ᵉ Anniversaire
- `2013bw` — Collection McDonald's 2013
- `2018sm-fr` — Collection McDonald's 2018
- `2019sm-fr` — Collection McDonald's 2019
- `2023sv` — Collection McDonald's 2023
- `2024sv` — Collection McDonald's 2024
- `A3a` — Crise Interdimensionnelle
- `cel25cc` — Célébrations Collection Classique
- `tk-dp-l` — DP Kit dresseur (Lucario)
- `tk-dp-m` — DP Kit dresseur (Manaphy)
- `exu` — EX Forces Cachées Collection Zarbi
- `tk-ex-latia` — EX Kit dresseur (Latias)
- `tk-ex-latio` — EX Kit dresseur (Latios)
- `tk-ex-m` — EX Kit dresseur (Négapi)
- `tk-ex-p` — EX Kit dresseur (Positi)
- `B1a` — Embrasement Écarlate
- `A3` — Gardiens Astraux
- `tk-hs-g` — HS Kit du dresseur (Léviator)
- `tk-hs-r` — HS Kit du dresseur (Raichu)
- `A3b` — La Clairière d'Évoli
- `A2a` — Lumière Triomphale
- `A1a` — L’Île Fabuleuse
- `mep` — MEP Black Star Promos
- `B2a` — Merveilles de Paldea
- `B1` — Méga-Ascension
- `mee` — Méga-Évolution Énergie
- `B2` — Parade Onirique
- `P-A` — Promo-A
- `A1` — Puissance Génétique
- `rc` — Radiant Collection
- `A2b` — Réjouissances Rayonnantes
- `tk-sm-l` — SM Kit du dresseur (Lougarox)
- `tk-sm-r` — SM Kit du dresseur (Raichu d'Alola)
- `A4` — Sagesse Entre Ciel et Mer
- `sp` — Sample
- `A4a` — Source Secrète
- `wp` — W Promotional
- `tk-xy-n` — XY Kit du dresseur (Bruyverne)
- `tk-xy-w` — XY Kit du dresseur (Grodoudou)
- `tk-xy-latia` — XY Kit du dresseur (Latias)
- `tk-xy-latio` — XY Kit du dresseur (Latios)
- `tk-xy-sy` — XY Kit du dresseur (Nymphali)
- `tk-xy-p` — XY Kit du dresseur (Pikachu Libre)
- `tk-xy-b` — XY Kit du dresseur (Scalproie)
- `tk-xy-su` — XY Kit du dresseur (Suicune)
- `xya` — carte alternative A Jaune

## Trous restants (cartes manquantes par rapport au total officiel TCGdex)

5 extension(s) dont l'import n'a pas ramené toutes les cartes officielles :

| Extension | Importées | Officiel (TCGdex) |
|---|---|---|
| `jumbo` Cartes Jumbo | 0 | 160 |
| `rc` Radiant Collection | 0 | 25 |
| `tk-sm-l` SM Kit du dresseur (Lougarox) | 18 | 30 |
| `sp` Sample | 0 | 10 |
| `wp` W Promotional | 0 | 7 |

## Explication des trous confirmés

Vérifié le 2026-09-19 par requête directe sur `api.tcgdex.net` : pour `jumbo`, `wp`, `rc`, `B1a` et `B2`, le détail de l'extension annonce un `cardCount.total` mais renvoie un tableau `cards` **vide** — la source elle-même n'a pas les fiches, notre import ne peut pas créer des cartes qui n'existent pas côté TCGdex. Pour `basep`, `np`, `svp` et `swshp`, le tableau `cards` est partiel par rapport à `cardCount.total` (même méthode de vérification). Ce n'est pas une erreur de notre pipeline ni une panne réseau transitoire — deux imports ciblés à des minutes d'écart ont ramené exactement les mêmes nombres.
