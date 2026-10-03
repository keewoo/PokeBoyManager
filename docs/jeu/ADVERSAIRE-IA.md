# Adversaire IA — un partenaire d'entraînement qui raisonne et explique (lot `j-adversaire-ia`)

> Jalon **J4**, décision **DJ7**. Le bot heuristique d'abord (`docs/jeu/MODE-SOLO.md`), puis, sur la
> clé du joueur, **son IA** : elle joue en expliquant pourquoi, ce qui fait d'une partie
> d'entraînement une leçon pour un enfant de onze ans.

## Le principe en une phrase

Dans une partie d'entraînement, l'adversaire du siège 1 peut être **le bot** (muet) ou **mon IA**
(fournisseur et clé du coffre du joueur, `pbm_api.ai`). À chaque décision, l'IA ne reçoit que la
**vue projetée** de son camp et la liste des **coups légaux** numérotés ; elle choisit un **index**
dans cette liste et l'explique en une phrase simple ; le moteur rejoue le coup ; l'explication part
au journal de la partie.

## Une seule interface « joueur automatique » (bot ou IA)

Le serveur reste autorité. La boucle `pbm_api.games.bot.boucle_joueur_auto` ne connaît ni le bot ni
l'IA : elle appelle un **décideur** (`pbm_api.games.adversaire_ia.Decideur`) qui rend une
`ResultatDecision`, puis **rejoue par le moteur** le coup choisi — jamais une action libre.

| Décideur | Construit par | Comportement |
|---|---|---|
| bot | `_decideur_bot(niveau)` | le bot heuristique de `pbm_sim.bots`, sans rien à expliquer |
| IA | `_decideur_ia(db, game, humain, provider, repli_niveau)` | l'IA du joueur ; **bascule sur le bot** en cas d'échec |

L'IA **ne contourne ni la validation du moteur ni l'autorité du serveur** : elle choisit un index
dans la liste que `actions_legales` a calculée, donc le coup est **légal par construction**. Un index
hors bornes est un échec (repli bot), jamais un coup inventé (D9).

## Ce que l'IA voit — et ne voit jamais

Le message (`adversaire_ia.construire_message`) est bâti **uniquement** depuis
`pbm_game.state.projection.vue(etat, acteur)` — qui cache déjà la main adverse, l'ordre de la pioche
(pour **tout le monde**) et l'identité des récompenses — et depuis les étiquettes des coups légaux de
l'acteur. Laisser l'IA voir l'état complet « pour qu'elle joue mieux » serait de la triche : un enfant
ne battrait jamais un adversaire qui voit sa main. Un test parcourt le message réellement transmis et
vérifie qu'aucun `instance_id` de la main ou de la pioche adverse n'y figure.

## L'échec ne se cache jamais

Réponse invalide, absente, trop lente, ou plafond d'appels atteint : **le bot joue ce coup**, et le
journal le **dit** (« Mon IA n'a pas pu jouer (…) — le bot a joué à sa place »). Jamais un repli
silencieux (règle du dépôt). Le repli joue au **même niveau** que celui choisi pour la partie.

## Plafonds, budget, coût affiché

| Garde | Constante (`adversaire_ia`) | Où |
|---|---|---|
| appels à l'IA par partie | `MAX_APPELS_PAR_PARTIE` (60) | compté sur `games.ia_appels` (persistant, survit au F5) |
| délai par coup | `DELAI_MAX_COUP_S` (20 s) | `asyncio.wait_for` autour de l'appel |
| longueur d'une explication | `MAX_LONGUEUR_EXPLICATION` (240) | tronquée au mot près |

Les jetons consommés s'accumulent sur `games.ia_tokens` **dans la transaction du coup** (compté
seulement si le coup est persisté) et alimentent aussi l'usage mensuel du joueur
(`ai_service.record_usage(..., commit=False)`). Le **coût estimé** est exposé par
`GET /games/{id}` (`ia_cout : {appels, jetons, plafond_appels}`). Le prix en **euros** n'est pas
encore calculé — aucune table de tarification par modèle n'existe dans ce dépôt (reste à faire,
documenté) : l'écran affiche appels et jetons, honnêtement, plutôt qu'un chiffre inventé.

La **clé du joueur ne sort jamais** : elle déchiffre le fournisseur dans `boucle_bot_pour_partie`,
n'est ni journalisée ni renvoyée, et le fournisseur est refermé après le tour.

## La route

`POST /matchmaking/entrainement` prend `adversaire` (`"bot"` par défaut, ou `"ia"`). Sans clé IA
utilisable, `adversaire="ia"` est **refusé en 422** (`CleIAIndisponible`) avec un message qui invite
à ajouter une clé et renvoie vers le bot en attendant (jamais un repli muet sur le bot). La capacité
est annoncée à l'avance par `GET /matchmaking/presence` (`ia_disponible`), pour que le salon propose
« mon IA » ou l'explication selon le cas.

## Où vit quoi

| Rôle | Fichier |
|---|---|
| décideur IA, message, plafonds, `choisir_coup_ia` | `apps/api/src/pbm_api/games/adversaire_ia.py` |
| interface unifiée (bot/IA), boucle, décideurs, création | `apps/api/src/pbm_api/games/bot.py` |
| explication portée au client | `apps/api/src/pbm_api/games/projection.py` (`commentaires`) |
| trace au journal, budget, siège IA | migration `a1b2c3d4e5f6`, `models/games.py` |
| route, capacité | `apps/api/src/pbm_api/routers/matchmaking.py`, `routers/games.py` |

## Placement initial : toujours le bot

Le placement du camp de l'adversaire survient à la **création** de la partie (route synchrone) : il
est fait par le **bot** (rapide, déterministe, sans appel réseau), même pour un adversaire IA. L'IA
prend la main pour les **tours de jeu**.

## Reste à faire (suivi front)

Le couloir de ce lot est **serveur** (J-SRV). Côté écran restent à câbler, dans un lot front :
le choix « mon IA / bot » au salon (en lisant `ia_disponible`), le rendu des `commentaires` dans le
panneau de journal, l'affichage de `ia_cout`, et la régénération du client TypeScript (`pnpm gen:api`,
le schéma d'API ayant gagné `adversaire`, `ia_disponible`, `ia_cout`, `adversaire_ia`). Enrichir le
fournisseur simulé (`AI_SIMULATED_PROVIDER`) pour l'e2e d'une partie contre l'IA viendra avec.
