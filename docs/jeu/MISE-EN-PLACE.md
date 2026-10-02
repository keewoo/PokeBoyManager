# Mise en place d'une partie (R-4)

> Comment une partie passe de « deux decks résolus » à « premier tour ». Moteur pur
> `pbm_game.mise_en_place` ; tout ce qui est décrit ici cite sa règle de référence
> (`docs/jeu/REGLES.md`). Livré par le lot `j-initialisation`.

## Ce que ça fait, dans l'ordre du livret (R-1.1)

1. **Mélange + pioche de sept** (R-4.1) — chaque joueur mélange son deck par son flux d'aléatoire
   nommé (`flux_melange_deck(<joueur>)`, reproductible et vérifié) et pioche sept cartes.
2. **Boucle de mulligan** (R-4.4 / R-4.6) — une main d'ouverture **sans Pokémon de base** est
   **révélée à l'adversaire**, remélangée, et le joueur repioche sept cartes. On répète jusqu'à ce
   que les deux mains aient au moins une base. Si **les deux** joueurs sont sans base le même tour,
   c'est un mulligan **simultané** : les deux recommencent, **sans** carte bonus (R-4.6).
3. **Cartes bonus** (R-4.5 / R-16.9) — pour chaque mulligan qu'un joueur prend **seul**,
   l'adversaire a droit à **une** carte supplémentaire. Elles sont **comptées** pendant la boucle
   (`MiseEnPlace.bonus`) et **piochées à la révélation**, pas avant.
4. **Placement de l'Actif et du banc, face cachée** (R-4.2 / R-3.2) — chaque joueur choisit, dans
   sa main, un Pokémon de base posé comme Actif (**obligatoire**) et au plus cinq bases au banc.
   Le choix vit dans `EtatPartie.mise_en_place`, **jamais** dans l'Actif/banc publics, tant que la
   révélation n'a pas eu lieu.
5. **Révélation simultanée** (R-4.2 / R-4.3) — quand le **second** joueur place, Actif/banc des
   deux côtés deviennent publics **en même temps**, six récompenses sont posées face cachée
   (R-3.4), les cartes bonus sont piochées, et la partie commence (`mise_en_place` repasse à
   `None`).

## Deux transitions journalisées

| Action | Nature | Rôle |
|---|---|---|
| `mise_en_place_initiale` | système | Déterministe depuis la graine : mélange, pioche de sept, boucle de mulligan complète. Aucun choix de joueur. |
| `placer_mise_en_place` | joueur | Chaque joueur place son Actif/banc face cachée ; quand les deux ont placé, la **même** transition résout la révélation simultanée. |

Elles s'enregistrent dans le `REGISTRE` du journal **à l'import** du paquet (motif `banc` /
`cartes` / `checkup`) ; `pbm_game` importe `mise_en_place` à son chargement.

## Les deux garanties qui comptent, et comment elles tiennent

- **Rien ne fuit avant la révélation.** Le placement d'un joueur n'apparaît ni dans les zones
  publiques ni dans la projection (`vue`) servie à l'adversaire : celle-ci ne dit que `a_place:
  true`, jamais le contenu. Un seul moment rend une main publique — le mulligan (R-4.4), et le
  journal en garde la trace (`EVT_MAIN_REVELEE` porte le contenu révélé).
- **La révélation est simultanée.** Même si un joueur valide dix secondes avant l'autre, aucun
  Actif n'est révélé tant que le second n'a pas placé ; la révélation est **un seul** événement
  (`EVT_MISE_EN_PLACE_REVELEE`) portant les deux côtés — personne n'est révélé avant l'autre.

## Le moteur ne devine aucun stade (D9)

Savoir si une carte est un Pokémon **de base** suppose sa fiche catalogue. Le moteur étant pur, les
deux actions portent un `params["definitions"]` (mapping `ref → fiche`) **fourni par le service** ;
une fiche absente **bloque** bruyamment (jamais « pas une base par défaut »). Le service projette
ses fiches catalogue en `dict` via `pbm_game.cartes.definition_vers_dict` (inverse exact de
`definition_depuis_dict` ; round-trip testé) — le journal transporte alors la fiche, donc le rejeu
n'a pas besoin du catalogue.

## Où c'est

- Moteur : `apps/game/src/pbm_game/mise_en_place/` (`modele.py`, `transitions.py`, `__init__.py`).
- Projection par joueur : `apps/game/src/pbm_game/state/projection.py` (clé `mise_en_place`).
- Sérialisation : `apps/game/src/pbm_game/state/serialisation.py` (aller-retour JSON exact).
- Tests : `apps/game/tests/test_mise_en_place.py` (cite chaque `R-x.y`).

Le **câblage service** (construire l'action `mise_en_place_initiale` depuis deux decks et la jouer)
n'est pas dans ce lot : `apps/api` ne consomme pas encore ces transitions.
