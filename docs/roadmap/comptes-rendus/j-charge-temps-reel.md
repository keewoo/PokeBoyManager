# j-charge-temps-reel — Tenue en charge : combien de parties simultanées sur deux cœurs

> Lot exécuté le **14/10/2026**, piloté depuis devAI, travaillé sur **chimera** (WSL Ubuntu-24.04),
> worktree `~/dev/wt-j-charge-temps-reel`, branche `roadmap/j-charge-temps-reel`.
> Garde-fou d'ordre : `suivi.py verifier j-charge-temps-reel` → **code 0**.

## Résumé

Le jeu sera servi par `kailo-srv` : **2 vCPU, 3,8 Go**, qui héberge déjà `kailo.life`, son UAT et
`acx-connect.com`. Ce lot mesure ce qu'une partie coûte, cherche le point de rupture, pose un
**plafond de 24 parties simultanées appliqué par le service** (refus en `503` + `Retry-After`, et
non un ralentissement général), dimensionne la purge, et écrit les chiffres dans
`docs/jeu/CHARGE.md`.

Deux résultats méritent d'être lus avant le reste, parce qu'ils contredisent ce qu'on attendait :

1. **Le point de rupture n'a pas été atteint.** Même à 48 parties simultanées sur deux cœurs, la
   latence d'un coup reste à 350 ms au 95ᵉ centile, sous le seuil de jouabilité de 500 ms. Le
   plafond de 24 n'est donc pas une limite physique : c'est une marge assumée, et c'est écrit comme
   tel plutôt qu'habillé d'une fausse précision.
2. **La cible a des cœurs plus rapides que la machine de mesure** (1,68× sur un banc représentatif).
   La mesure sur chimera est donc conservatrice côté processeur — ce qui ne la rend pas optimiste
   pour autant, puisque la cible doit faire tenir sa base de données sur les deux mêmes cœurs.

## Livrables

| Livrable | Où |
|---|---|
| Plafond mesuré, écrit et **appliqué** | `apps/api/src/pbm_api/games/capacite.py`, garde dans `creer_partie` |
| Refus HTTP unique pour les trois portes | `apps/api/src/pbm_api/routers/capacite_http.py` (503 + `Retry-After: 30`) |
| File d'attente plutôt que dégradation | `apps/api/src/pbm_api/games/matchmaking.py` (`apparier` suspend, les rangs tiennent) |
| Réglage par l'environnement | `settings.jeu_parties_simultanees_max` (`JEU_PARTIES_SIMULTANEES_MAX`), défaut **24** |
| Mesures reproductibles | `apps/api/scripts/measure_game_load.py` |
| Métriques et alertes de capacité | `observabilite/{releve,metriques,regles}.py` + `docs/jeu/OBSERVABILITE.md` |
| Les chiffres, datés | **`docs/jeu/CHARGE.md`** |
| Tests | `apps/api/tests/test_games_capacite.py` (11 tests) |

## Preuves

### Le plafond est mesuré

Mesure sur chimera, bornée à deux cœurs (`taskset -c 0,1`), 15 parties jouées jusqu'à leur fin,
`VACUUM ANALYZE` avant chaque lecture de taille :

| | Valeur |
|---|---|
| Empreinte en base, par partie (21 coups) | **178,7 Kio** — journal 146,1 / instantanés 29,9 / `games` 2,7 |
| Empreinte **par coup** (la grandeur transférable) | **8,5 Kio** (journal seul : 7,0 Kio) |
| Partie médiane réelle (215 coups, campagne `j-simulation-bots`) | **≈ 1,8 Mio** |
| Résidu après purge complète | 14,4 Kio par partie |
| Processeur par coup | **≈ 20 ms** (15 ms API + ~5 ms Postgres) |
| Mémoire par partie simultanée | **≈ 0,5 Mo** (83 Mo à vide → 107 Mo à 48 parties) |

Latence d'un coup par palier de concurrence (p50 / p95) : 1 → 98/181 ms · 8 → 162/219 · 12 →
167/289 · 16 → 235/376 · **24 → 223/368** · 32 → 265/378 (p99 **1 178**) · 48 → 225/350.
Le débit plafonne à 30-48 coups/s ; 24 parties à un coup toutes les trois secondes en demandent 8.

JSON complet des relevés : `/tmp/charge-A.json` et `/tmp/charge-B.json` sur chimera (fichiers de
travail, non versionnés — le script les refait).

### Le plafond est appliqué, et une partie de plus reçoit un refus clair

`creer_partie` est le **seul** endroit du dépôt qui insère une ligne `games` : la garde y vit, donc
aucun chemin ne la contourne. Le comptage est fait deux fois — une fois sans verrou à l'entrée (pour
ne pas payer la résolution de deux decks quand on va refuser), une fois sous
`pg_advisory_xact_lock` juste avant l'insertion, ce qui rend le plafond **exact** sous concurrence
et non simplement indicatif.

```
tests/test_games_capacite.py ........... 11 passed in 2.48s
```

Réponse mesurée de `POST /matchmaking/entrainement` à plafond atteint : **503**, en-tête
`Retry-After: 30`, et `detail` = « Le serveur tient déjà 1 parties en même temps, pour un plafond
de 1 : impossible d'en lancer une de plus pour l'instant. Réessaie dans un instant — les parties en
cours, elles, ne sont pas ralenties. »

Côté écran, **rien n'a été à changer, et c'est vérifié plutôt que supposé** :
`apps/web/src/lib/api/client.ts` propage le `detail` du serveur pour tout code non-2xx, et
`apps/web/src/components/game/fin-partie.tsx:108` affiche `err.message` — la phrase arrive donc
telle quelle au joueur sur le bouton « Revanche ». La route `/matchmaking/entrainement` n'est pas
encore appelée par le front (prévue par `j-salon-partie`, pas encore câblée).

### Les parties en cours ne ralentissent pas

Garantie **structurelle**, pas chronométrique : le verrou et le comptage sont sur le chemin de la
création, jamais sur celui d'un coup. `test_un_coup_ne_prend_jamais_le_verrou_de_capacite` espionne
le SQL réellement émis pendant un `appliquer_action` joué alors que le plafond est atteint, et
vérifie qu'il ne contient ni `pg_advisory_xact_lock` ni comptage des parties actives.

C'est volontairement un test de structure et non de durée : une assertion sur un chronomètre dans
un coureur de CI partagé serait instable, donc désactivée tôt ou tard, donc inutile. Les durées, qui
sont la vraie mesure, vivent dans `CHARGE.md` et se refont par le script.

### Les tests mordent

Garde neutralisée (les deux appels à `verifier_capacite` retirés de `creer_partie`) :

```
7 failed, 4 passed      ← sans la garde
11 passed               ← avec la garde
```

Les quatre qui passent dans les deux cas sont ceux qui n'ont pas besoin du refus : repli d'un
réglage absurde, parité des trois portes, et les deux lectures de métriques.

### Non-régression

`uv run pytest tests/` sur chimera, base **propre** : **1205 passés, 2 échecs**. Les deux échecs
sont `test_catalogue_seed.py` (`pg_dump: command not found`) — **préexistants** : vérifiés
identiques sur l'arbre `main` de chimera au commit `0d0ebd6`, sans aucune de mes modifications.
`ruff check` passe sur tout `apps/api`. Les 191 tests du jeu, du matchmaking, du lancement, des
invitations et de l'observabilité passent. `apps/game` et `apps/web` ne sont pas touchés.

### La croissance de la base est chiffrée et la purge dimensionnée

La purge existait déjà (`games_maintenance_task`, toutes les 10 min : `expirer_parties` puis
`purger`). Ce lot la **dimensionne** à partir des 1,8 Mio d'une partie médiane :

| Rythme | Volume au plateau (30 jours) | Part des 12 Go libres de la cible |
|---|---|---|
| 3 parties/jour (l'usage réel : trois joueurs) | 160 Mio | 1,3 % |
| **18 parties/jour** | **1 Gio** | **8 %** |
| 50 parties/jour | 2,7 Gio | 23 % |

**La purge à 30 jours est correctement dimensionnée**, avec plus d'un ordre de grandeur de marge
pour l'usage prévu. Le seuil retenu et écrit : au-delà de **~18 parties par jour en moyenne**,
descendre `jeu_purge_anciennete_j` plutôt que de regarder le disque se remplir.

Mesuré au passage : la purge des instantanés intermédiaires est le gros du ménage — **138
instantanés effacés pour 15 parties**, et l'empreinte retombe de 178,7 à 14,4 Kio par partie.

### La saturation se voit avant la plainte

`GET /jeu/metriques` publie `parties_actives`, `capacite_plafond` et `capacite_taux` ; deux alertes
nouvelles : `capacite_frolee` (avertissement, ≥ 80 %) et `capacite_atteinte` (critique). Le seuil
est à 80 % et non à 100 % parce qu'une alerte qui arrive en même temps que le premier joueur refusé
n'est pas une alerte, c'est un constat. Les trois compteurs tiennent dans la requête d'état
existante : pas un aller-retour de plus.

Chaque refus laisse un incident `partie_refusee` / `capacite_atteinte` — motif **distinct** de
`carte_non_scriptee`, parce que l'un se corrige en écrivant un script et l'autre en agrandissant la
machine.

## Décisions prises dans le lot

| Décision | Pourquoi |
|---|---|
| **503 + `Retry-After`**, pas 429 | Aucun quota n'est attaché au joueur : c'est la machine qui est pleine, et le même joueur passera sans rien changer. 429 dirait « tu demandes trop », ce qui est faux |
| La file d'attente **n'est pas** refusée | Un joueur qui a demandé « trouve-moi un adversaire » a déjà accepté d'attendre ; un 503 serait du bruit. Il garde sa place et son rang |
| Une partie **échue** ne compte pas | Sinon quelques dizaines de parties abandonnées fermeraient le jeu jusqu'au prochain balayage, pour protéger un processeur que personne ne sollicite |
| Une partie **d'entraînement** compte | Elle ne compte pas au classement, mais le bot (et plus encore l'IA) consomme *plus* qu'un humain qui réfléchit |
| La capacité est contrôlée **avant** la règle D9 | En régime saturé, refuser avant de résoudre deux decks est la différence entre un serveur qui encaisse les tentatives et un serveur qui s'écroule sous elles. Le refus D9 est permanent, celui de capacité est transitoire : le joueur au deck injouable l'apprendra à sa prochaine tentative |
| Le lancement **par défaut** (délai échu) avale le refus de capacité | Cette résolution est déclenchée par des routes qui ne demandent pas à lancer une partie — un simple `GET`, et même un **abandon**. Laisser remonter le 503 rendrait l'abandon impossible pendant une saturation, c'est-à-dire au moment où libérer la place est utile |
| Plafond **24**, pas 48 | Moitié du plus grand palier mesuré tenable. Marge pour la contention de la base (sur la cible, Postgres partage les deux cœurs) et les trois voisins. Relevable par l'environnement, **avec une mesure à l'appui** |

## Écarts au plan

- **Rien n'a été mesuré sur la cible en charge.** La mission demandait « mesurer sur chimera puis
  vérifier sur le serveur cible, avec les autres services en fonctionnement » : la seconde moitié
  n'a pas été faite, et ce n'est pas un oubli — on ne construit pas, et on ne mesure pas, sur la
  machine qui sert (règle d'or de la flotte), et ce lot ne déploie rien. Ce qui a été fait à la
  place, en lecture seule : relevé de l'état réel de `kailo-srv` (2 vCPU, 3 861 Mo dont 2 473
  disponibles, 12 Go libres sur 30, charge **0,07**, les cinq services voisins actifs, API pokeboy
  à 55 Mo) et **banc processeur comparatif** des deux machines. La vérification en charge est
  écrite comme procédure en quatre étapes dans `CHARGE.md`, pour le lot `j-mise-en-ligne-jeu` que
  celui-ci débloque.
- **Le point de rupture n'a pas été trouvé** (pas de palier rompu jusqu'à 48). Le plafond est donc
  une marge, pas une limite mesurée — dit explicitement dans `CHARGE.md` plutôt que présenté comme
  un résultat.
- **Les parties de mesure font 21 coups, pas 215.** Le joueur de mesure joue simplement et les
  parties finissent vite. C'est pour cette raison que la grandeur retenue est l'octet **par coup**,
  insensible à la longueur ; la projection vers une partie médiane réelle utilise les 215 coups
  mesurés par `j-simulation-bots`.
- **Le canal temps réel n'est pas dans les chiffres** : les coups ont été joués par le service, pas
  par HTTP + WebSocket. La diffusion ajoute un envoi par abonné et par coup (file bornée à 256
  messages) ; à 24 parties, 48 abonnés. Écart consigné dans `CHARGE.md`.
- **`measure_game_load.py` n'est pas exécuté par la CI** (`scripts/` n'est pas dans `testpaths`) :
  c'est un outil de mesure, pas un test. Ce que la CI garde, c'est le **comportement** du plafond,
  via `test_games_capacite.py`.

## Deux pièges rencontrés, pour le lot suivant

1. **Un deck de mesure irréaliste fausse tout.** La première version semait 20 cartes avec un
   attaquant qui met K.O. d'un coup : les parties finissaient en **sept** coups et l'empreinte par
   partie était vingt fois trop basse. Le deck de mesure fait maintenant soixante cartes, 120 PV et
   30 de dégâts. Une mesure de volume ne vaut que si la partie mesurée ressemble à une partie.
2. **Un micro-banc `sha256` donnait la cible 2,8× plus rapide** — faux pour notre usage : les
   processeurs récents accélèrent SHA-256 en matériel (SHA-NI), ce qui exagère leur avance sur du
   bytecode Python ordinaire. Le banc retenu (sérialisation JSON d'un état + parcours de structures)
   ramène l'écart à **1,68×**. Les deux chiffres sont dans `CHARGE.md`, avec la raison de l'écart :
   le mauvais banc est aussi instructif que le bon.

Au passage, une leçon d'intendance : le script de mesure **écrit** (joueurs, cartes, parties). Lancé
sur la base de tests, il a fait échouer 16 tests qui supposent une base vide. Il refuse désormais
`pbm_catalogue_ref`, `pokeboy_prod` et `pokeboy_uat`, et `CHARGE.md` lui donne une base dédiée.

## Reste à faire

- **Vérifier en charge sur la cible**, au moment de la mise en ligne : procédure en quatre étapes
  dans `docs/jeu/CHARGE.md` § « Vérification sur la cible ». C'est le lot `j-mise-en-ligne-jeu`.
- **Mesurer le canal temps réel** (HTTP + WebSocket de bout en bout) : ce lot a mesuré le service.
- **Relever le plafond si la mesure in situ le permet** — jamais parce qu'un joueur a reçu un 503.
- Le front n'a **pas** d'écran dédié au refus de capacité : il affiche la phrase du serveur, ce qui
  suffit au critère. Un écran plus soigné (compte à rebours sur `Retry-After`) serait du confort,
  pas une correction.
