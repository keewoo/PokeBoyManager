# Compte rendu — `j-simulation-bots`

**Bots de simulation : des milliers de parties pour débusquer les blocages.** Jalon J2, piste
Qualité & exploitation, couloir J-QUA (chimera).

## Résumé

Livré le paquet d'outillage **`pbm_sim`** (`apps/game/src/pbm_sim/`, à côté du moteur pur
`pbm_game`, jamais dedans) : deux bots qui décident sur la **seule vue joueur**, un orchestrateur
qui joue une partie complète et range toute défaillance dans une **anomalie nommée**, des campagnes
de masse en parallèle, et la **reproduction d'une anomalie en une commande** depuis sa graine. La
campagne réduite tourne désormais en CI à chaque poussée ; une campagne longue tourne chaque nuit.

**Le chiffre du lot (critère d'acceptation n°1)** : campagne de **10 000 parties** sur chimera
(16 fils, 2 min 59 s), **10 000 saines, 0 anomalie**. Les 36 affrontements de decks du roster sont
couverts et les trois voies de fin de partie représentées.

## Livrables

- **Deux bots** (`pbm_sim.bots`) qui ne reçoivent **jamais** l'`EtatPartie` — seulement la vue
  projetée et la liste des coups légaux (garanti par signature, testé) :
  - `bot_aleatoire` : n'importe quel coup légal (hors abandon), flux d'aléatoire reproductible ;
  - `bot_heuristique` : promeut le Pokémon le moins amoché (R-8.7), attaque pour le plus de dégâts
    (R-9/R-10), évolue (R-7), pose ses bases, n'attache une énergie que si ça rapproche d'une
    attaque (économise ses ressources).
- **Un roster de 6 decks synthétiques** (`pbm_sim.decks`), 60 cartes chacun, **entièrement jouables**
  au jalon J2 (attaques à dégâts secs, énergies de base — D9) : aggro électrique, tank incolore,
  ligne d'évolution eau, faiblesse ×2, résistance −30, cible TAG TEAM (3 récompenses).
- **Un scénario déterminé par une seule graine** (`scenario_depuis_graine`) : decks, bots, siège qui
  commence, graine moteur — tout en découle. C'est ce qui rend une anomalie reproductible.
- **L'orchestrateur** (`pbm_sim.orchestrateur.jouer_partie`) : enchaîne les coups système (mise en
  place R-4, pioche de début de tour R-5.2, Pokémon Checkup R-12) et les coups de bot, contrôle les
  invariants **après chaque coup**, rejoue le journal à la fin et compare l'empreinte. Six types
  d'anomalie : `etat_invalide`, `exception`, `blocage`, `partie_sans_fin`, `rejeu_divergent`,
  `demande_inattendue`.
- **Les campagnes de masse** (`pbm_sim.campagne`) : parallélisme par processus, mémoire plate
  (aucun journal ne traverse les processus), distribution des durées (tours et coups), couverture
  (raisons de fin, affrontements).
- **La ligne de commande** `python -m pbm_sim` : `campagne` (code 1 s'il reste une anomalie) et
  `reproduire <graine>` (rejoue une partie en détail, code 1 si anomalie).
- **La campagne réduite de CI** (`tests/test_simulation_campagne_ci.py`, 250 parties) : tourne dans
  le job `game` à chaque poussée — la garde « une campagne à chaque lot de scripts de cartes ».
- **La campagne longue de nuit** (`.github/workflows/simulation-nuit.yml`, cron 03:17 UTC, 20 000
  parties par défaut).
- **La fiche** `docs/jeu/SIMULATION.md`.

## Preuves

- **10 000 parties saines, 0 anomalie** (chimera, préfixe `jalon-j2`) :
  - tours — min 2, médiane 37, moyenne 45,8, p95 95, max 95 ;
  - coups — min 11, médiane 215, moyenne 266, p95 547, max 599 ;
  - raisons de fin — dernière récompense 6242, pioche impossible 1939, plus de Pokémon 1819 ;
  - 36 affrontements de decks couverts.
- **Reproduction en une commande** (chimera) :
  `uv run python -m pbm_sim reproduire jalon-j2:4242` → `eau-resistante vs evolution-eau`,
  bots `heuristique vs aleatoire`, `B` vainqueur par pioche impossible, 95 tours, 556 coups, saine.
- **Suite complète du moteur verte sur chimera** : `uv run pytest -q` → **905 passés** ; `ruff` tout
  vert. (La CI GitHub fait foi — SHA cité dans le dernier message.)
- **La détection mord vraiment** (sinon une campagne verte ne vaudrait rien) :
  `test_simulation_orchestrateur.py` force une `partie_sans_fin` (plafond de coups bas) et vérifie
  que la graine est archivée ; et vérifie que le filtre d'invariants exempte **étroitement** le seul
  transitoire de promotion (R-3.3/R-8.7) mais laisse passer une carte présente dans deux zones.
- **Les bots ne voient que la vue** : `test_simulation_bots.py` vérifie qu'aucune signature de bot
  n'expose `etat`.

## Écarts au plan / décisions prises (session autonome)

- **Decks synthétiques, pas le vrai catalogue.** Au jalon J2, seules les attaques à dégâts secs sont
  jouables (D9) ; le vrai catalogue n'est pas encore scripté. Un roster de 6 decks jouables de bout
  en bout était donc nécessaire pour que des milliers de parties se déroulent. Le roster s'enrichira
  de cartes réelles au fil des lots `j-cartes-*`. Documenté dans `SIMULATION.md`.
- **Exemption étroite d'un invariant.** Le moteur laisse volontairement l'état « Actif K.O., banc
  non vide, partie non finie » entre un K.O. et la promotion du tour suivant (R-3.3/R-8.7) — ses
  propres tests ne vérifient pas les invariants sur cet état (`test_ko_recompenses`, cas « promotion
  demandée »). L'orchestrateur exempte **ce seul cas, pour le seul joueur concerné** ; toute autre
  violation reste une anomalie. Ce n'est pas un repli silencieux : c'est documenté, testé dans les
  deux sens, et calqué sur le comportement du moteur lui-même.
- **Les bots ignorent l'abandon** tant qu'un autre coup existe (il en existe toujours un) : un
  abandon au hasard mettrait fin aux parties sans rien exercer. L'abandon reste un coup légal du
  moteur.
- **`pbm_sim` vit dans `src/` à côté de `pbm_game`** (et non dans `tools/`) pour que la CI l'importe
  via `pytest` ; il n'est pas empaqueté dans le *wheel* du moteur (`packages=["src/pbm_game"]`) et
  reste hors du balayage de pureté (qui ne scanne que `pbm_game`). Aucune modification du moteur.

## Reste à faire

- Enrichir le roster de **cartes réelles** à mesure que les lots de scripts les rendent jouables
  (`j-cartes-attaques-effets`, `j-effets-dsl` déjà là) — chaque nouveau script devrait ajouter un
  deck qui l'exerce, pour que la campagne de CI le couvre.
- Quand un lot introduira des **effets à décision** jouables, étendre l'orchestrateur pour piloter
  les `demande` (aujourd'hui `demande_inattendue` est une anomalie, faute de pilote au jalon J2).
- Débloque `j-charge-temps-reel` (tenue en charge) et `j-mode-solo` (entraînement contre un bot),
  qui réutiliseront ces bots.

## Grille

| Tâche | État | Preuve |
|---|---|---|
| dev | fait | `pbm_sim` (bots, decks, orchestrateur, campagne, rapport, CLI) |
| tests | fait | 4 fichiers `test_simulation_*`, suite moteur 905 verts sur chimera |
| securite | fait | bots sur la vue seule (jamais l'état) ; aucun secret ; `pbm_sim` hors du *wheel* moteur |
| maquette | s.o. | lot moteur/outillage, sans écran |
| doc_tech | fait | `docs/jeu/SIMULATION.md` ; docstrings françaises partout |
| release_uat | fait | recette sur chimera : campagne 10 000 = 10 000 saines, 0 anomalie |
| release_prod | s.o. | pas de livraison PROD (outillage ; la PROD se livre à part, par devAI) |
| backlog | s.o. | tenu par la file (etat.json non touché) |
| compte_rendu | fait | ce fichier |
