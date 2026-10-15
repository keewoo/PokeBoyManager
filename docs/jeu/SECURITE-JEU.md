# Sécurité du jeu — revue avant ouverture

> **Revue du 15/10/2026**, lot `j-securite-jeu` (P0, jalon J5). Portée : le jeu seulement — le
> reste du produit a eu la sienne (`docs/SECURITE.md`), et cette fiche n'en redit rien.
>
> **Pourquoi le jeu mérite la sienne.** Il ouvre un canal **permanent** entre deux comptes, dont
> celui d'un mineur, et il fait circuler de l'information que l'un des deux joueurs n'a pas le
> droit de connaître. Les deux risques n'existent nulle part ailleurs dans le produit.

## Verdict en une page

| # | Ce qui a été éprouvé | Verdict | Correctif |
|---|---|---|---|
| 1 | Non-fuite sur **l'ensemble des scripts livrés** | **3 fuites trouvées** | corrigées (moteur + porte de refus) |
| 2 | Canal : message malformé, action hors tour, partie étrangère, rafale | **2 défauts trouvés** | corrigés (500 sur un entier ; refus muets) |
| 3 | Suppression de compte ↔ parties et journaux | **non tenu** | corrigé (`delete_account`) |
| 4 | Authentification du canal temps réel | conforme | — (refus désormais journalisés) |
| 5 | Limitation de débit | **partielle**, nommée | non corrigé — voir « Risques résiduels » |
| 6 | Validation des charges utiles | conforme, 2 trous bouchés | `ge=0`, refus nommé |
| 7 | Isolation des parties entre comptes | conforme | — |
| 8 | Protection du mineur | conforme | — |
| 9 | Données conservées et durée | conforme | — |

**Six correctifs livrés**, chacun avec un test qui échoue sans lui. **Deux risques résiduels
nommés**, aucun bloquant pour l'ouverture — aucun des deux ne porte sur la confidentialité.

---

## 1. Non-fuite d'information cachée sur les scripts de cartes

### Pourquoi le test existant ne suffisait pas

Le moteur était éprouvé — `projeter` ne fuite sur aucun de **1 000 états** aléatoires
(`test_sortie_projection`), et tout `EVT_*` sans projecteur est refusé. Mais la mission du lot
disait « **pas seulement sur le moteur** », et la fiche nommait le risque : *« c'est dans un script
mal écrit que la prochaine fuite apparaîtra »*. Elle avait raison, et trois fois.

Trois raisons de **ne pas** énumérer les scripts livrés :

1. le corpus réel vit en base (`card_scripts`, **94 scripts** au 14/10/2026) et **n'est pas dans le
   dépôt** : un test sur liste figée aurait été vert sur six scripts et muet sur quatre-vingt-huit ;
2. le corpus grandit à chaque passe de génération : il faut couvrir le script n°95 sans y repenser ;
3. une fuite ne vient pas d'un script, elle vient d'une **combinaison** primitive × zone ×
   propriétaire que personne n'avait exercée.

La garde est donc **structurelle** : `apps/game/tests/test_securite_scripts_fuite.py` balaie les
**486 combinaisons** du langage (18 primitives × 9 zones × 3 propriétaires), exécute les **337**
qui sont chargeables et sûres (141 hors langage, 8 refusées par l'audit — comptées, jamais sautées
en silence), et projette **chaque événement produit pour les deux joueurs** en interdisant toute
identité (`instance_id` *et* `ref`) d'une zone cachée à son destinataire.

### Fuite n°1 — un `choisir` sur une zone cachée livrait les identités

`DemandeDecision.ensemble_cache` **existait**. La projection l'honorait (`options_nombre` au lieu
d'`options`), le journal moteur l'honorait. **Aucun appelant ne le posait jamais** : zéro
occurrence de `ensemble_cache=True` dans tout le code de production.

Conséquence : un script « choisissez une carte de la main de votre adversaire » livrait au joueur
qui tranche les `instance_id` de la main adverse — et `enrichir_demande` les résolvait ensuite en
`ref`, `nom` et `type`. Le joueur **voyait la main de son adversaire**, dans son écran.

**Correctif** — `pbm_game.effets.dsl.execution.ensemble_cache_pour`, appelé par
`strategie_demande` : l'ensemble est caché dès qu'un candidat est une carte d'une zone que le
destinataire n'a pas le droit de voir.

| Zone du candidat | Cachée au destinataire ? |
|---|---|
| `recompenses` (de qui que ce soit) | **oui, toujours** — une récompense est face cachée pour les deux joueurs (R-3.4) ; montrer les identités à son propriétaire lui dirait laquelle prendre |
| `main`, `pioche` d'**un autre** joueur | **oui** (R-3.2, R-3.3) |
| `main`, `pioche` de **soi** | non — « cherchez dans votre deck » donne explicitement le droit de regarder (R-5.2) |
| Pokémon en jeu, défausse, zone perdue, Stade | non — public (R-3.1, R-3.6) |

Choisir à l'aveugle dans un ensemble caché est le comportement **juste**, pas un repli : le TCG
fait lui-même choisir au hasard dans une main adverse. Le destinataire reçoit le nombre d'options
et désigne une position.

### Fuite n°2 — le choix retenu partait aux deux joueurs

`EVT_DEMANDE_REPONDUE` et `EVT_DEMANDE_EXPIREE` pointaient sur `_public`, au motif — écrit en
commentaire, **imposé par rien** — que ces événements « ne portent jamais une carte d'une zone
cachée ici ». C'était une convention d'écriture des scripts. Dès que le DSL a su poser de vraies
demandes, elle est devenue fausse : `choix` porte les `instance_id` retenus, qui peuvent venir de
n'importe quelle zone qu'un `choisir` sait viser.

**Correctif** — projecteur `_demande_tranchee` : seul celui qui a tranché revoit son `choix` ; tout
autre joueur reçoit `choix_nombre`. L'événement porte désormais son `destinataire` (champ public :
savoir *de qui* la partie attendait une décision évite un écran muet).

**On ne perd rien en route** : la *conséquence* publique d'une décision est toujours publiée par
son propre événement — `changer_actif` annonce le nouvel Actif, `defausser` les `ref` défaussées,
`degats` les dégâts subis. Ce qui redevient privé, c'est la **décision**. Le journal moteur, à
part, garde la trace complète (rejouabilité, support, anti-triche).

### Fuite n°3 — `chercher` publiait les `ref` de sa propre main

**Celle-ci, c'est le balayage qui l'a trouvée**, à sa toute première exécution, alors que la règle
écrite à la main ne regardait que le propriétaire (« chez l'adversaire »). Un `chercher` sur sa
**propre main** publiait ses `ref` à son adversaire.

`chercher` déplace vers la **main** (cachée) *et* publie les `ref` — parce que le texte imprimé des
cartes de recherche dit « cherchez dans votre deck, **montrez-la** et ajoutez-la à votre main »
(R-5.2). La publication est juste pour **sa propre pioche**, et fausse partout ailleurs.

**Correctif** — `pbm_game.effets.dsl.audit` **refuse** le script, et le chargeur en fait un refus
nommé à la construction du deck (même porte D9 qu'un effet non implémenté) :

> *« script refusé par l'audit de confidentialité — « chercher » publie les `ref` des cartes
> touchées alors qu'il les déplace vers une zone cachée… »*

**Pourquoi refuser plutôt que corriger.** Distinguer « déplacer » de « montrer » est une évolution
du **langage** d'effets (un paramètre `montrer` sur `chercher`, et sa sémantique carte par carte) :
une décision de règles, qui appartient au lot des effets. Une revue de sécurité qui réécrirait la
sémantique d'une primitive pour fermer une fuite ferait exactement ce que D9 interdit — jouer une
carte autrement que ce qu'elle dit. Alors on dit « je ne sais pas jouer cette carte sans fuiter »,
on le dit **avant** la partie, et on nomme la raison.

La forme du correctif compte : `audit.py` nomme ce qui est **autorisé** et traite tout le reste
comme une fuite. L'inverse — énumérer les cas interdits — est précisément ce qui avait laissé
passer « sa propre main ».

### La garde qui empêche la prochaine

`PUBLICATION_PAR_OP` classe **chaque** primitive du vocabulaire selon ce qu'elle publie des
identités qu'elle touche (`rien`, `a_bon_droit`, `si_chez_soi`, `par_demande`). Un `op` ajouté au
vocabulaire sans entrée fait **casser** `test_la_table_d_audit_couvre_tout_le_vocabulaire` — même
mécanique que la parité des projecteurs. C'est ce qui empêche la prochaine primitive d'arriver sans
que personne ne se demande ce qu'elle laisse voir.

### ⚠️ Ce qui reste à faire avant d'ouvrir — passer l'auditeur sur le corpus réel

Les 94 scripts de la base **n'ont pas été audités** : ils n'existent pas dans le dépôt, et la base
de PROD ne se lit pas depuis un lot. Un script du corpus qui tomberait sous le refus rendrait sa
carte **injouable** (en le disant, mais sans que personne l'ait vu venir).

L'outil est livré et c'est de la **lecture seule** :

```bash
cd apps/api && UV_PYTHON=3.12 uv run python scripts/auditer_scripts_effets.py
UV_PYTHON=3.12 uv run python scripts/auditer_scripts_effets.py --dsn "postgresql+asyncpg://…"
```

Il rend **1** s'il reste un script fautif. **À passer sur dev, UAT et PROD avant la mise en ligne
du jeu** (`j-mise-en-ligne-jeu`), et après chaque passe de génération de scripts.

---

## 2. Le canal temps réel, éprouvé

### Ce qui tenait déjà

| Épreuve | Résultat | Où c'est prouvé |
|---|---|---|
| Message malformé (non-JSON) | `{}` → `type_inconnu`, socket **non fermée** | `test_games_temps_reel` |
| Type de message inconnu | `{"type":"erreur","code":"type_inconnu"}` | `test_games_temps_reel` |
| `resync` avec un `depuis` absurde | `depuis_invalide`, puis borné à `[0, numéro courant]` | `temps_reel.py` |
| Action **hors tour** / illégale | 422 motivé, état **inchangé**, refus tracé | `test_games_projection` |
| **Rafale** de coups illégaux | WARNING par coup, puis `ERROR "ALERTE anti-triche"` + incident en base | `test_games_projection` |
| Action sur une partie **étrangère** | 404 (jamais 403 — aucune fuite d'existence) | `test_games_projection` |
| Origine tierce sur le WebSocket | fermeture **4403** avant toute authentification (anti-CSWSH : un WebSocket n'est pas protégé par le CORS) | `test_games_ws_routes` |
| Authentification du canal | **cookie de session**, pas de jeton en query string ; participation vérifiée **avant** `accept()` | `games_ws.py` |

L'ordre des contrôles du canal est le bon et vaut d'être noté : **origine → session → participation
→ `accept()`**. Un non-participant n'obtient jamais de socket ouverte.

### Défaut n°4 — un entier négatif faisait tomber la route

`{"type": "piocher", "numero_attendu": -1}` entrait dans le chemin de **rejeu idempotent**
(`numero_attendu < current_numero`), n'y trouvait aucun événement, et remontait un `NoResultFound`
**non rattrapé** : une **500**, déclenchable par n'importe quel client avec un seul entier.

Corrigé en **deux couches**, parce qu'une seule n'aurait pas suffi :

- `ActionIn.numero_attendu: int = Field(ge=0)` — borne de schéma, protège la route ;
- `scalar_one()` → `scalar_one_or_none()` + `ConflitNumero` nommé — protège les appels **internes**
  (bot, revanche, scripts), qui ne passent pas par le schéma, et le cas d'un journal troué.

### Défaut n°5 — les refus les plus intéressants ne laissaient aucune trace

Le critère du lot dit « toute action sur une partie étrangère est refusée **et journalisée** ». Elle
était refusée, parfaitement, et **parfaitement muette** : `_game_pour_participant` levait sans une
ligne. `routers/games_ws.py` déclarait même un `logger` **utilisé nulle part** — les trois
fermetures du canal (origine rejetée, session invalide, partie étrangère) ne produisaient rien.

Corrigé, avec un partage qui compte :

| Situation | Niveau | Pourquoi |
|---|---|---|
| Partie **inconnue** (identifiant périmé, signet, partie purgée) | INFO | banal |
| Partie **étrangère** (elle existe, le demandeur n'y joue pas) | **WARNING** | le signal utile : énumération d'identifiants, client modifié |
| Canal : origine non autorisée | **WARNING** | tentative de CSWSH |
| Canal : cookie présent mais invalide / sans droit de jeu | **WARNING** | |
| Canal : aucun cookie | INFO | banal |

Sans ce partage, le choix était entre un journal muet et un journal qui crie à chaque signet mort —
et un journal qui crie pour rien est un journal que personne ne lit. Le client, lui, reçoit
toujours le même 404 muet : **ce qui change, c'est ce que le serveur garde**.

### Le jeton CSRF — trois mutations l'ignoraient

`POST /games/{id}/actions`, `/abandon` et `/conseil` écrivaient **sans** `require_csrf`, alors que
**toutes** les autres mutations du jeu l'exigeaient (revanche, partages de replay, réglages de
confort / rendu / emotes / notifications, file d'attente, invitations, lancement) — et que le dépôt
a un test `*_exige_le_csrf` par mutation. Rien ne documentait l'exception ; c'était un oubli.

Exploitabilité réelle : **faible**. Le corps est en `application/json`, donc une requête
cross-origin exige un préflight CORS, et `allow_origins` ne contient que l'URL du front. C'est de
la **défense en profondeur** — mais une seule ligne de configuration sépare cet état d'un trou, et
la session vit dans un cookie. Les trois routes sont ferrées, avec leurs tests.

---

## 3. Suppression de compte ↔ parties et journaux

**Le critère n'était pas tenu.** `delete_account` supprimait la ligne `users` et laissait les
cascades SQL faire le reste. Elles couvraient l'authentification, la collection, les envois et les
exports. **Pas le jeu** — parce que `games` n'a **aucune clé étrangère vers `users`** (seul
`vainqueur_user_id` en a une, en `SET NULL`).

Survivaient donc, indéfiniment :

| Table | Ce qui restait du compte effacé |
|---|---|
| `games` | `etat_initial` (JSONB) — les identifiants de joueur **sont** les `user_id` |
| `game_events` | `auteur`, un `str(user_id)` **en clair, une ligne par coup joué**, plus les `commentaire` en texte libre de l'IA |
| `game_snapshots` | `etat` — les mêmes identifiants, à chaque instantané |

Et une partie `en_cours` n'était **jamais** ramassée par la purge d'ancienneté (`service.purger` ne
prend que `terminee`/`expiree`) : elle serait restée pour toujours. Le test existant qui s'appelle
`test_delete_account_leaves_no_row_tied_to_the_user_id` n'assertait que cinq tables, aucune du jeu,
et son jeu d'essai ne créait **aucune** donnée de partie.

**Correctif** — `delete_account` relève les parties par `game_players` (le seul lien entre un compte
et ses parties) **avant** de supprimer l'utilisateur, et les supprime ; `game_events` et
`game_snapshots` suivent par leur cascade vers `games`. La place du joueur dans la **file d'attente**
(Redis) est retirée au passage : une entrée de file qui survit à son compte fait tenter un
appariement sur un utilisateur inexistant.

### Ce qui survit, et l'arbitrage assumé

L'en-tête `game_results` **reste** (statut, raison de fin, nombre de coups, tours, durée), son
`vainqueur_user_id` mis à `NULL` par la cascade. Elle ne porte alors plus aucune donnée
personnelle, et c'est elle qui tient l'historique de l'**adversaire** — dont le
`game_result_players` a survécu, puisque le compte supprimé n'est pas le sien
(`docs/jeu/FIN-COMPTE.md`).

**Le prix à payer est nommé : le *replay* de ces parties disparaît pour l'adversaire.** Il n'existe
pas de replay sans le journal, et un journal qui nomme un compte effacé n'a pas à survivre à son
effacement. L'adversaire garde ses statistiques et ses lignes d'historique ; il perd le rejeu. Entre
les deux, l'effacement gagne.

`jeu_incidents` survit avec `user_id` à `NULL` (cascade `SET NULL`) : son `detail` est un message
d'erreur borné à 512 caractères, sans donnée personnelle. Volontairement conservé — c'est la trace
anti-triche, et l'anonymiser suffit.

---

## 4. Protection du mineur — conforme, et c'est une décision de conception

Rien à corriger. Ce qui le garantit n'est pas une liste de filtres, c'est l'**absence de surface** :

| Exigence | État |
|---|---|
| **Aucun texte libre** entre joueurs | garanti par construction : les emotes sont un **catalogue fermé** (`code in CODES`), et il n'existe **aucune route HTTP** pour en envoyer — seulement le WebSocket. Aucun champ de saisie n'atteint l'autre joueur, nulle part |
| Aucune emote ne peut narguer | règle du catalogue, testée (`docs/jeu/EMOTES.md`) |
| Débit des emotes | 5 par 20 s **et** 1 s minimum entre deux (`games/emotes.py`) |
| Couper les emotes | interrupteur immédiat et mémorisé sur le compte |
| **Invitation révocable** | `POST /invitations/{id}/annuler` (l'invitant), `/refuser` (l'invité) ; les invitations par lien sont des jetons stockés **hachés**, rendus une seule fois en clair |
| Accès au jeu | `require_game_access` (D11) : un compte n'a le jeu que si le drapeau est posé |

**Un manque, nommé** : il n'existe pas de **blocage d'un joueur** (liste de comptes dont on refuse
toute invitation). Aujourd'hui on refuse chaque invitation une par une. Avec un catalogue d'emotes
fermé et aucun texte libre, la surface de nuisance est très étroite — mais « refuser toujours » est
un geste que l'invitation révocable ne remplace pas. **Hors périmètre de ce lot** (c'est une
fonctionnalité, pas un correctif) : à inscrire au backlog du jeu.

Le seul texte libre qui atteint un écran de joueur est le **commentaire de l'IA** en mode solo
(`adversaire_ia.commentaire_journal`) : il provient de l'IA du joueur lui-même, sur sa propre clé,
en partie contre un bot — il n'y a pas d'autre humain dans la boucle.

---

## 5. Risques résiduels — nommés, non corrigés, non bloquants

Aucun ne porte sur la confidentialité. Les deux demandent de **choisir un chiffre**, ce qui relève
du lot de charge (`docs/jeu/CHARGE.md`), pas d'une revue.

### R1 — pas de limitation de débit sur les routes du jeu

Le `RateLimiter` Redis du dépôt (`security/rate_limit.py`) ne sert **que** `routers/auth.py`. Aucune
route du jeu n'en a. Ce qui existe à la place : le plafond de parties simultanées (503 +
`Retry-After`), le débit des emotes, la borne de file d'abonné (256), le détecteur de rafale de
coups illégaux — qui **alerte sans bloquer**, c'est documenté et voulu.

Sans plafond, et par ordre de coût décroissant :

| Chemin | Ce que ça coûte |
|---|---|
| WS `resync` | un rejeu depuis le dernier instantané **et une session de base** par message, sans aucun throttle |
| `POST /invitations/pseudo` | **un e-mail envoyé** par appel |
| `GET /cards/{id}/in-game-study` | dépense la **clé IA de l'appelant** sur un défaut de cache |
| `GET /games/{id}/sync` | rejeu du journal par appel |
| `POST /games/{id}/conseil` | borné par `coach_max_conseils`, lui |

Le plus coûteux est `resync`, et c'est aussi le plus simple à borner : le `LimiteurEmotes`
(`games/emotes_service.py`) est exactement la pièce qu'il faut, keyée `(game_id, user_id)`.

### R2 — `ActionIn.params` n'a aucun plafond de taille

Un `params` inconnu est **ignoré, jamais interprété** : il n'y a ni requête construite par
concaténation ni chemin de fichier dérivé d'un `params` — donc ni injection ni traversée (fixé par
`test_des_params_inconnus_sont_ignores_et_non_interpretes`). Mais il est **journalisé tel quel**
dans `game_events.action` : un client peut écrire du JSON arbitraire, de taille non bornée, dans le
journal de **sa** partie, un enregistrement par coup. Sur un petit serveur partagé, c'est un
vecteur de croissance du disque. Une borne de taille au schéma suffirait.

---

## Ce qui est contrôlé par la CI, et ce qui ne l'est pas

**Par la CI** (elle fait foi) : le balayage des 486 combinaisons du langage, les deux fuites de
projection, la table d'audit exhaustive, les refus de scripts fuitants, la journalisation des accès
croisés, le CSRF des trois mutations, l'effacement des parties à la suppression du compte, les
charges utiles hostiles. Jobs `game` (1 159 tests) et `api` (1 413 tests).

**Pas par la CI, à faire à la main** :

1. **l'audit du corpus réel** (`scripts/auditer_scripts_effets.py`) — § 1, avant la mise en ligne ;
2. les deux risques résiduels — § 5, quand le chiffre sera choisi ;
3. le blocage d'un joueur — § 4, quand la fonctionnalité sera décidée.

## Quand relire cette fiche

- avant `j-mise-en-ligne-jeu` (c'est elle qui porte la liste du § « Ce qui reste à faire ») ;
- après chaque **passe de génération de scripts** : repasser l'auditeur sur la base ;
- à chaque **primitive ajoutée** au DSL : la table d'audit casse la CI, la décision se prend ici ;
- à chaque **nouveau `EVT_*`** : la parité des projecteurs casse la CI, même règle.
