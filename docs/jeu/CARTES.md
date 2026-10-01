# CARTES.md — cartes Pokémon jouables depuis le catalogue (lot `j-cartes-pokemon`)

> Comment une carte Pokémon du catalogue devient jouable : sa **définition** (ce que le moteur en
> sait), sa **pose** en jeu, et sa **pile d'évolution**. Le corpus qui fait foi reste
> `docs/jeu/REGLES.md` — chaque mécanique ci-dessous cite son `R-x.y`.

## Le principe : rien en dur, le moteur reçoit une définition

Le moteur `pbm_game` est **pur** : il ne lit ni base ni réseau. Il ne connaît donc **aucune**
caractéristique de Pokémon en dur (D9). Une carte lui arrive sous la forme d'un
`pbm_game.cartes.DefinitionCarte` — un descripteur **validé** — que le service extrait du
catalogue. Les actions `poser` / `evoluer` transportent cette définition dans leurs `params` : le
journal la porte, donc le rejeu n'a pas besoin du catalogue.

`DefinitionCarte` (`apps/game/src/pbm_game/cartes/modele.py`) porte : `ref`, `nom`, `stade`
(`base` / `stade1` / `stade2`), `pv`, `type`, `marqueur` (de règle), `evolue_depuis`, `faiblesse`,
`resistance`, `cout_retraite`, `attaques`. Sa validation **mord** : un champ manquant ou incohérent
lève `ValueError` — jamais une valeur devinée.

- **Marqueur de règle** : validé contre la table close `pbm_game.combat.fin.MARQUEUR_RECOMPENSES`.
  Un marqueur **inconnu** est refusé (R-13.4 / R-15.22), jamais « par défaut 1 ».
- **Chaîne d'évolution** (R-7.1) : une base n'a pas de prédécesseur ; un stade 1/2 **doit** nommer
  son `evolue_depuis` — sinon la carte est bloquée.
- **Attaques** : seules les attaques à **dégâts secs** sont jouables au jalon J1. Une attaque dont
  le texte porte un effet, ou dont les dégâts sont variables (« 20× »), est chargée fidèlement mais
  marquée (`AttaqueDef.effet` non vide) ; son script arrive avec `j-cartes-attaques-effets` (D9).

## Poser un Pokémon (R-5.3)

Action `poser` (`pbm_game.cartes.transitions`) : une carte de **base** de la main entre en jeu,
au **banc** (`zone: "banc"`, défaut) ou directement comme **Actif** sur une place vide
(`zone: "actif"` — le cas particulier d'une entrée par un effet ou à la mise en place). Gardes : la
phase principale du joueur actif (R-5.3), banc ≤ 5 (R-3.2 / R-8.1), on ne remplace jamais un Actif
présent (R-3.3). Le Pokémon posé est noté **entré en jeu ce tour** (`tour.entres_en_jeu_ce_tour`) :
il ne pourra pas évoluer ce tour-ci (R-7.3). Une carte d'évolution ne se **pose** pas : elle entre
par `evoluer`.

## Faire évoluer (R-7)

Action `evoluer` : la carte d'évolution de la main **coiffe** la pile du Pokémon ciblé (identité
stable = l'`instance_id` de sa carte de base). Ce qu'elle **conserve** et ce qu'elle **efface** :

| Conserve (R-7.1) | Efface (R-7.2 / R-11.9) |
|---|---|
| énergies attachées, Outil, compteurs de dégâts, pile d'évolution | tous les états spéciaux (via la porte partagée `etats.soigner_etats_speciaux`) |

Gardes de tour (`tour.contraintes.peut_evoluer`, le serveur fait autorité) :

- **R-6.5** — pas d'évolution au premier tour de chaque joueur (`numero ≤ 2`) ;
- **R-7.3** — pas d'évolution d'un Pokémon entré en jeu ce tour (`entres_en_jeu_ce_tour`) ;
- **R-7.4** — pas deux évolutions du **même** Pokémon le même tour (`evolues_ce_tour`, nouveau champ
  de `Tour` — distinct de `entres` : une évolution ne rend pas le Pokémon « nouveau en jeu » pour
  l'attaque ou la retraite, seulement pour une seconde évolution).

La **chaîne** est vérifiée dans la transition : `definition.evolue_depuis` doit égaler `nom_base`
(le nom du Pokémon au sommet de la cible, fourni par le service depuis le catalogue) — on n'évolue
que sur le **bon** Pokémon (R-7.1). Un K.O. défausse ensuite **toute** la pile, ses énergies et son
Outil (R-13.2, primitive partagée `combat.ko.cartes_a_defausser`).

## L'adaptateur catalogue (`apps/api/src/pbm_api/jeu/catalogue.py`)

C'est **ici**, hors du moteur, que vit la connaissance des colonnes du catalogue.
`definition_depuis_card(card)` lit `name`, `hp`, `energy_type`/`element_type`, `stage`, `attacks`,
`weaknesses`, `resistances`, `retreat_cost`, `prize_marker` et en fabrique une `DefinitionCarte`.
Le `prize_marker` est **déjà normalisé** à l'import (`pbm_api.catalog.prize_marker`) vers le
vocabulaire du moteur : l'adaptateur ne lit jamais le nom pour deviner les récompenses (R-13.7). Un
champ manquant (PV, stade, coût de retraite) ou un marqueur inconnu **bloque** la carte.

⚠️ **Lacune de catalogue connue** : le catalogue ne porte pas encore la chaîne d'évolution
(`evolves_from`), et la base de référence de chimera n'a pas la colonne `stage`. Une carte
d'évolution sans ces champs est donc **bloquée** par l'adaptateur (comportement voulu — on ne
devine pas). Les alimenter (import de `evolveFrom` depuis TCGdex) est un chantier de catalogue à
part. Les **cartes de base** complètes se chargent, elles, sans ce chantier.

## Où c'est prouvé

| Quoi | Où |
|---|---|
| Les six cas d'évolution (R-7.1/7.2/7.3/7.4, R-6.5, R-13.2) | `docs/jeu/cas-executables/evolution.yaml` |
| Définition, pose, pile, cas limites du moteur | `apps/game/tests/test_cartes.py` |
| L'adaptateur catalogue (blocages, marqueur inconnu) | `apps/api/tests/test_jeu_catalogue.py` |
