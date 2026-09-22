# CLAUDE.md — PokeBoyManager

> **Ce fichier est un index, pas une encyclopédie.** Il porte ce qu'il faut savoir *avant d'agir* :
> ce qu'est le projet, les règles qui ne se discutent pas, et où trouver le reste.
> Le détail vit dans `docs/` — voir « Les fiches » plus bas, et « Où écrire quoi » avant d'ajouter
> une ligne ici.

## Ce qu'est le projet

Espace privé (compte e-mail + mot de passe) : photos de cartes Pokémon → reconnaissance par l'IA
**de l'utilisateur** (clé Claude, Gemini ou OpenAI déposée dans son profil) → collection filtrable,
valeur dans le temps, fiche carte (image officielle, état estimé, anecdotes sourcées, étude en jeu).
Puis, plus tard, **jouer** avec ses propres cartes.

En service : **https://pokeboy.acx-connect.com** (depuis le 20/09/2026).

## Le plan fait foi

- `docs/roadmap/roadmap.json` : le plan du produit (lots, dépendances, décisions). Seule source.
- `docs/roadmap/etat.json` : l'état réel, écrit **uniquement** par `docs/roadmap/suivi.py`.
- `docs/roadmap/jeu/plan/` : le plan du **jeu**, sans dates, ordonné par dépendances.
- `BACKLOG.md`, `prompts/*.md`, `docs/roadmap/ROADMAP.html`, `docs/roadmap/jeu/BACKLOG-JEU.md`,
  `docs/roadmap/jeu/jeu.json` sont **générés** — ne jamais les éditer à la main :
  `python3 docs/roadmap/suivi.py build` et `python3 docs/roadmap/jeu/build-jeu.py`.
- Chaque lot démarre par `suivi.py verifier <id>` : code 2 = ordre non tenu → on s'arrête et on
  demande à JF.
- Page publiée (roadmap, backlog du jeu, maquettes) : https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy

## Les règles qui ne se discutent pas

- Un lot = un worktree `../wt-<id>`, une branche `roadmap/<id>`, une PR. Jamais `git stash`,
  jamais `git add -A`.
- Python **3.12** (`UV_PYTHON=3.12`), Node 24. **La CI GitHub Actions fait foi.**
- Toute route utilisateur filtre par `user_id` issu de la session ; test d'accès croisé obligatoire.
- Les clés IA ne sont **jamais** renvoyées, journalisées ni écrites en clair (AES-256-GCM, clé
  maître hors base).
- Aucun secret dans le dépôt (`.env` ignoré, `.env.example` sans valeur réelle).
- Le front reproduit la maquette ; identité propre, **pas de logo officiel Pokémon**.
- **Construire sur chimera, déployer par devAI** ; jamais de build ni de déploiement depuis le Mac
  de JF.
- **Traitements lourds sur la flotte, jamais sur la machine qui sert** — garde `HEAVY_JOBS_ENABLED`
  (faux par défaut en production).
- **Un repli silencieux est interdit** (`|| true`, `except: pass`, `2>/dev/null` sur un chemin
  nominal) : un relevé de prix vide ou un lot sans compte rendu est une panne, pas un cas normal.

## Chercher ici : le graphe avant le grep

Ce dépôt est **indexé** (`.mcp.json` → serveur `graphify`) : 5 381 nœuds, 13 614 arêtes, 267
communautés. **Avant d'ouvrir dix fichiers** pour savoir qui appelle quoi, demande au graphe —
`query_graph`, `get_neighbors`, `shortest_path`, `god_nodes`. Une réponse en un appel au lieu de
vingt lectures, et autant de contexte gagné pour le travail réel.

Rafraîchir après un gros changement : `graphify update .` (~25 s, AST local, aucun coût). **Un
graphe périmé répond faux avec aplomb.** Il oriente, il ne prouve pas : on ouvre le fichier réel
avant d'affirmer qu'une ligne existe. Détail : `docs/PLUGINS.md`.

## Les fiches — où lire quoi

| Fiche | On l'ouvre quand… |
|---|---|
| `docs/CODE.md` | on écrit du code : structure du monorepo, commandes, versions, git, tests, définition du « fini » |
| `docs/ARCHITECTURE.md` | on veut savoir **ce que fait** le produit côté serveur : données, auth, catalogue, prix, reconnaissance, decks, et les repères d'implémentation par lot |
| `docs/UI-UX.md` | on touche à `apps/web` : maquette, jetons de style, composants, écrans livrés, accessibilité |
| `docs/LIVRAISON.md` | on met en ligne : environnements, variables d'environnement, chaîne de livraison, preuve, retour arrière |
| `docs/RELEASE.md` | on annonce une version : qui décide, comment ça se nomme, le CHANGELOG, la check-list |
| `docs/PLUGINS.md` | on ajoute ou on diagnostique un service tiers : catalogue, prix, IA, e-mails, stockage — et ce qui n'est **pas** branché |
| `docs/SECURITE.md` | on touche à l'authentification, aux clés, aux envois de fichiers, ou avant d'ouvrir un accès |
| `docs/infra/SERVEUR-POKEBOY.md` | on veut l'état exact du serveur (rapport daté du 19/09) |
| `docs/infra/JOBS-LOURDS.md` | on planifie ou on diagnostique un traitement lourd |
| `docs/catalogue/COMPLETUDE.md` | on se demande si le catalogue est complet, et où sont les trous |
| `docs/roadmap/jeu/BACKLOG-JEU.md` | on travaille sur le jeu (67 lots, paliers, décisions `DJ*`) |

## Où écrire quoi

Ce fichier a atteint 641 lignes parce que chaque lot y ajoutait sa section. **On ne recommence pas.**
Quand un lot est fini, son savoir durable va dans **une** fiche :

| Ce que le lot a produit | Où ça s'écrit |
|---|---|
| un comportement serveur, une table, une route | `docs/ARCHITECTURE.md` |
| un écran, un composant, une règle de style | `docs/UI-UX.md` |
| une convention de code, une commande, un test | `docs/CODE.md` |
| une étape de mise en ligne, une variable d'environnement | `docs/LIVRAISON.md` |
| un appel à un service extérieur, une clé, un budget | `docs/PLUGINS.md` |
| une faille trouvée, une parade posée | `docs/SECURITE.md` |
| ce qui s'est passé pendant le lot (mesures, écarts, preuves) | `docs/roadmap/comptes-rendus/<id>.md` |

**Dans `CLAUDE.md`, uniquement** : une règle nouvelle qui s'applique partout, ou une entrée dans la
carte des fiches. Trois lignes, pas trente. Si on hésite, c'est que ça va dans une fiche.

Une fiche ne redit pas ce qu'une autre dit déjà : elle y renvoie. Tous les chemins cités dans les
fiches sont donnés **depuis la racine du dépôt**.

## La flotte

Ce dépôt est travaillé par plusieurs machines : **chimera** construit et exécute les traitements
lourds, **devAI** livre, le Mac de JF ne fait qu'éditer. Les règles complètes (délégation,
`fleet-run`, pièges par machine, accès SSH) sont dans `~/.claude/CLAUDE.md` du poste concerné —
elles s'appliquent ici sans être recopiées.

Trois points qui ne valent que pour ce dépôt :

- On construit sur **chimera** (32 Go, 16 threads), jamais sur la machine qui sert.
- Le lien Internet de chimera plafonne à **~250 Ko/s** : éviter les téléchargements et les images
  Docker inutiles ; un gros téléchargement passe par devAI, puis on copie.
- **Session autonome** (`claude -p`) : commits ciblés, jamais `git stash`, jamais `git add -A`, et
  **compte rendu obligatoire même en cas d'échec ou de blocage** — un lot silencieux est une panne,
  jamais une conclusion.
