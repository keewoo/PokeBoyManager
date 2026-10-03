# Livraison — mettre en ligne, et revenir en arrière

> **À lire avant toute mise en ligne.** Le geste technique : où ça tourne, qui construit, qui
> déploie, comment on prouve que c'est en ligne, comment on revient en arrière.
> Ce qui n'est pas ici : **quoi** sort et quand (`docs/RELEASE.md`), le code (`docs/CODE.md`),
> la préparation historique du serveur (`docs/infra/SERVEUR-POKEBOY.md`, rapport daté).
> Tous les chemins sont donnés **depuis la racine du dépôt**, sauf ceux préfixés `/srv` (serveur).

## ⛔ La règle d'or : on ne construit pas sur la machine qui sert

`kailo-srv` a **2 cœurs et 3,8 Go de RAM**, et il sert déjà `kailo.life`, `uat.kailo.life` et
`acx-connect.com`. Un build sur place dégrade le service pendant qu'il tourne — mesuré ailleurs :
charge 143 sur 4 cœurs, `/health` qui expire à 30 s pour un visiteur réel, un OOM-kill.

**chimera construit. devAI livre. Le serveur ne fait que recevoir et redémarrer.**
Aucun build, aucun `docker compose`, aucun déploiement **depuis le Mac de JF** — c'est le verrou
posé après l'incident du 2026-08-09 (`~/.claude/CLAUDE.md`).

## Contrainte absolue : kailo.life et ACX ne bougent pas

Avant **et** après chaque étape qui touche au serveur, on vérifie que les sites voisins répondent
comme avant :

```bash
for u in https://kailo.life https://www.kailo.life https://acx-connect.com \
         https://www.acx-connect.com https://uat.kailo.life; do
  printf "%-32s %s\n" "$u" "$(curl -s -o /dev/null -w '%{http_code}' "$u")"
done
# attendu : 200 200 308 200 307
```

Une seule valeur qui change : on arrête et on remet en état. Les sites de JF passent avant
PokeBoyManager.

## Ce qui tourne aujourd'hui

| | |
|---|---|
| PROD | **https://pokeboy.lol** — domaine propre depuis le **22/09/2026** ; en service depuis le **20/09/2026 15h39** (commit `5873a9c`) sous `pokeboy.acx-connect.com`, qui redirige désormais en 308 vers l'apex (`docs/infra/DOMAINE-POKEBOY-LOL.md`) |
| UAT | **aucun** (D2, JF 19/09) : la recette se fait en local sur chimera, on déploie directement en PROD |
| Machine | `kailo-srv` / UpCloud « sites-and-crons » (`004ba88c…`), 5.22.213.226 |
| Services | `pokeboy-prod-web` (Next.js, port 3100), `pokeboy-prod-api` (FastAPI/uvicorn, 8100), `pokeboy-prod-worker` (arq) |
| Entrée | Caddy de l'hôte, qui importe `/srv/pokeboy/caddy/pokeboy.caddy` |
| Données | PostgreSQL 18 de l'hôte, base `pokeboy_prod` (rôle propre, `REVOKE CONNECT ... FROM PUBLIC`) ; Redis local, base logique **0 = prod, 1 = uat** |
| Fichiers | `/srv/pokeboy/prod/{app,config,data/photos,backups,logs,releases}`, utilisateur système `pokeboy` |

Les unités `pokeboy-uat-*` (ports 3110 / 8110) existent mais restent **inactives** tant qu'il n'y a
pas d'UAT.

## La chaîne de livraison

1. **La CI est verte** sur le commit à livrer (GitHub Actions fait foi — voir `docs/CODE.md`).
2. **chimera construit** les artefacts (front Next.js, API, dépendances).
3. **Transfert** vers `/srv/pokeboy/prod/releases/<horodatage>/` — le groupe `pokeboy` y écrit,
   c'est fait pour ça.
4. **Bascule** : `app/` pointe sur la nouvelle version.
5. **Migrations** Alembic appliquées.
6. `systemctl restart pokeboy-prod-{api,worker,web}`.
7. **Preuve** (voir ci-dessous), puis vérification des sites voisins.

> **Point ouvert.** Ces étapes sont celles du rapport `pbm-serveur` et de la mise en PROD du 20/09.
> Le script qui les enchaîne n'est **pas encore dans le dépôt** (`infra/` ne contient à ce jour que
> les SQL de la chaîne flotte). Tant qu'il n'y est pas, la livraison se fait depuis devAI à la main
> et **chaque livraison doit reporter ici ce qu'elle a réellement exécuté**. Le jour où le script
> existe, son chemin remplace ce paragraphe.

## Livraison du 23/09/2026 — vague V7D « Gestionnaire de decks »

Ce qui a réellement été exécuté (la chaîne n'est toujours pas scriptée dans le dépôt).
Release **`20260923-024121`**, commit **`3063f41`**, précédente `20260922-234920` (`b32daec`).

```bash
# 0. Portes : CI verte sur 3063f41 ; codes HTTP des voisins relevés AVANT (200 200 308 200 307)
# 1. chimera construit — le worktree de build appartient au dépôt RELAIS, pas au clone :
ssh chimera 'wsl … -- bash -lc "cd ~/dev/wt-pbm-deploy && git fetch github && git checkout --detach github/main"'
ssh chimera 'wsl … -- bash -lc "bash ~/dev/pbm-build-lol.sh"'   # → ~/dev/pbm-artefacts/{web,api}-TS.tgz
# 2. transfert chimera → devAI → serveur, empreintes SHA-256 comparées aux TROIS étapes
ssh chimera 'wsl … -- cp ~/dev/pbm-artefacts/*-TS.tgz /mnt/c/tmp/pbm/'
ssh devai   'scp chimera:C:/tmp/pbm/{web,api}-TS.tgz /tmp/pbm/ && scp /tmp/pbm/*-TS.tgz kailo-srv:/tmp/pbm/'
# 3. point de restauration frais AVANT toute écriture
ssh kailo-srv 'sudo -n -u pokeboy bash /srv/pokeboy/prod/backups/backup.sh'
# 4. préparation (n'engage rien : le service tourne encore sur l'ancienne release)
ssh kailo-srv 'TS=20260923-024121 COMMIT=3063f41 LOT=v7d-gestionnaire-de-decks bash /tmp/prep-lol.sh'
# 5. bascule, avec retour arrière automatique sur échec de santé
ssh kailo-srv 'TS=20260923-024121 bash /tmp/deploy-switch.sh'
```

**Preuve relevée après bascule** : `app/ -> releases/20260923-024121`, `RELEASE_INFO` porte
`commit=3063f41` ; les 3 unités `active` ; `https://pokeboy.lol/api/health` → 200 ;
`/jeu/decks` → 307 (route présente et gardée, pas 404) ; l'OpenAPI servi expose **14 routes
`decks`**, dont `/me/decks/cards` (recherche), `/me/decks/{id}/stats`, `/me/decks/{id}/propose`
(assistant IA), `/me/decks/alerts` et `/me/decks/{id}/replacements` (synchro collection) ;
voisins **inchangés** (200 200 308 200 307).

**Aucune migration** : la base était déjà à `b2d4f6a8c0e1`, `alembic upgrade head` n'a rien eu
à faire — la release précédente avait déjà embarqué `v7-decks-collection-sync`.

### Deux pièges rencontrés, à ne pas rejouer

- **Le worktree de build de chimera (`~/dev/wt-pbm-deploy`) est rattaché au dépôt relais
  `~/dev/pokeboy.git`, pas au clone `~/dev/pokeboy`.** Un `git fetch` fait dans le clone ne
  l'avance pas : son `github/main` retardait de **12 commits**. Rien n'échoue dans ce cas —
  on construit l'ancienne version en croyant livrer la nouvelle. **Vérifier le HEAD du
  worktree après le checkout**, jamais supposer qu'il a bougé.
- **Le SSH vers chimera se fait couper** (`kex_exchange_identification: Connection reset`)
  pendant les builds : ce n'est pas une panne, on réessaie. Une boucle de 5 tentatives
  espacées de 15 s a suffi à chaque fois.

## Livraison du 01/10/2026 — marqueur de récompenses, fin de l'interblocage, polices embarquées

Ce qui a réellement été exécuté (la chaîne n'est toujours pas scriptée dans le dépôt).
Release **`20261001-234045`**, commit **`b0df8ae`**, précédente `20260923-024121` (`3063f41`).
Livré depuis **devAI** en session autonome ; `main` avançait en parallèle (lot `j-cartes-pokemon`),
on a donc livré le **commit figé `b0df8ae`**, pas `main` (`origin/main` valait `b0df8ae` au moment de
la livraison).

```bash
# 0. Portes : CI « CI » verte sur b0df8ae (web, api, e2e, game — 4 jobs success) ;
#    voisins AVANT 200 200 308 200 307 ; serveur sain (charge 0.11, 2379 Mo dispo).
# 1. chimera construit — worktree de build (dépôt relais) checkout --detach b0df8ae, HEAD vérifié :
#    pbm-build-lol.sh ne fait PAS son propre checkout (il était resté sur 3063f41, piège n°1).
#    PATH non-interactif : node/pnpm vivent dans ~/.local/node/bin, à ajouter (pnpm: command not found sinon).
#    Build lancé détaché (setsid, survit à la coupure SSH) puis sondé jusqu'à BUILD_DONE.
ssh chimera 'wsl … bash -s'  # checkout b0df8ae + setsid bash ~/dev/pbm-build-lol.sh → web/api-20261001-234045.tgz
#    Artefact web vérifié : 4 .woff2 sous .next/static/media/, 0 occurrence de fonts.googleapis/gstatic.
# 2. transfert chimera → devAI → kailo-srv, SHA-256 comparés aux TROIS étapes (identiques) :
#    web 280633be…d71c · api 9c6a7150…0bcb
# 3. point de restauration frais AVANT toute écriture :
ssh kailo-srv 'sudo -n -u pokeboy bash /srv/pokeboy/prod/backups/backup.sh'  # dump 41,5 Mo/26 tables, photos 1051, daté de l'instant
# 4. préparation (n'engage rien : l'ancienne release sert encore ; la migration passe ici) :
ssh kailo-srv 'TS=20261001-234045 COMMIT=b0df8ae LOT=livraison-20261001 bash /tmp/prep-lol.sh'  # → PREPARATION_OK
# 5. bascule, avec retour arrière automatique sur échec de santé :
ssh kailo-srv 'TS=20261001-234045 bash /tmp/deploy-switch.sh'  # → BASCULE_OK (api=200 web=200 au 1er contrôle)
```

**Migration appliquée** : Alembic `b2d4f6a8c0e1 → e7c2a9f14b63` (`cards.prize_marker`, additive et
auto-remplissante). Tête après migration : `e7c2a9f14b63 (head)`.

**Preuve relevée après bascule** : `app/ -> releases/20261001-234045`, `RELEASE_INFO` porte
`commit=b0df8ae` ; les 3 unités `active` ; `https://pokeboy.lol/api/health` → 200 et `/` → 200.
- **Marqueur de récompenses**, exécuté avec le **code de la release déployée** (`prize_rule_of`) sur
  de **vraies lignes PROD** : Méga-Blizzaroi-ex (`mega_ex`) → **3 Prix** ; Dracaufeu et Roussil GX
  (`tag_team`) → **3 Prix** ; Otaria (`ordinaire`) → **1 Prix** ; Poké Ball (Dresseur) → hors Pokémon.
  Greedent (supertype `Pokemon` **sans accent**) est bien reconnu Pokémon : le défaut `Pokémon`/`Pokemon`
  est corrigé. La route HTTP `GET /cards/{id}/in-game-study` n'a **pas** été appelée : elle exige une
  session **et** déclenche une génération IA facturée — `prize_rule` étant une fonction pure du
  marqueur, l'exécuter sur le code déployé prouve le comportement sans dépense ni compte jetable.
- **Polices embarquées** : la page servie et son CSS (`/_next/static/css/8864c34c7e7099cc.css`, 200)
  ne citent **aucune** URL `fonts.googleapis.com`/`fonts.gstatic.com` (0/0) et référencent **4**
  `/_next/static/media/*.woff2`, tous en **200**.
- **Voisins inchangés** à chaque étape et à la fin (`200 200 308 200 307`). Serveur après : charge
  0.08, 2541 Mo dispo, 3 unités `active`.

### Écart à corriger (signalé, non bloquant) : 564 cartes « Stage1/Stage2 » classées `inconnu`

Les comptes `prize_marker` en PROD diffèrent de la référence de dev (`pbm_catalogue_ref`, annoncée
« identique » mais ne l'est pas) : **148 attendus / 175 observés** pour `mega_ex`, **119/119** pour
`tag_team`, et surtout **0 attendu / 564 observés** pour `inconnu`. Ces 564 cartes portent toutes
`rule_marker` = **`Stage1`** (422) ou **`Stage2`** (142) — des marqueurs de **stade d'évolution** que
`normalized_prize_marker` ne reconnaît pas et range donc en `inconnu` (refus de deviner, R-13.4), alors
que ce sont des Pokémon **ordinaires** (Greedent, Arcanine, Beedrill…). La référence de dev avait ces
champs vides (→ `ordinaire`) ; l'import PROD les a peuplés.

**Conséquence, mesurée** : la fiche « En jeu » de ces 564 cartes affiche « Récompenses non déterminées
(marqueur de règle inconnu) » avec `prizes_taken=None` — **dégradation d'affichage, jamais un 500** (la
route API gère `inconnu`/`None` gracieusement, `apps/api/src/pbm_api/ingame/rules.py`), et pas pire que
l'ancienne version qui faisait passer toute carte réelle pour « hors Pokémon ». **Non bloquant** : les
~23 000 autres cartes sont désormais correctes. **Correctif candidat** (lot de suite, code + CI + rebuild) :
ajouter `stage1`/`stage2` (ou tout marqueur de stade) aux marqueurs ordinaires de
`catalog/prize_marker.py`, et poser le test qui l'aurait attrapé.

### Pièges rejoués / nouveaux

- **`pbm-build-lol.sh` ne fait pas son propre checkout** (contrairement au `build-pbm.sh` modèle de
  devAI) : il construit le HEAD courant du worktree, resté sur `3063f41`. Checkout + **vérification du
  HEAD** faits à la main avant le build — piège n°1 du 23/09, toujours valable.
- **PATH non-interactif de chimera** : `cw.sh` ouvre un `bash -s` (non-login), où `pnpm` est absent
  (`command not found`). node/pnpm sont dans `~/.local/node/bin` — à ajouter au PATH du build.
- **Trace dépôt non écrite sur `/Volumes/Data`** : ce process n'a pas l'autorisation macOS d'écrire sur
  ce volume externe (`Operation not permitted`, TCC — non contournable par le bac à sable). Repli sur un
  worktree **transitoire** `~/dev/wt-livraison-20261001` (disque système, 22 Gi libres), **pas** le clone
  `~/dev/pokeboy` de la file de lots, supprimé juste après le push.

## Livraison du 02/10/2026 — correctif des stades : un stade ordinaire n'est jamais un marqueur de règle

Ce qui a réellement été exécuté (la chaîne n'est toujours pas scriptée dans le dépôt).
Release **`20261002-005119`**, commit **`124f0cd`** (tête de `roadmap/fix-marqueur-stades`, **basée sur
`b0df8ae`**), précédente `20261001-234045` (`b0df8ae`). Livré depuis **devAI** en session autonome ;
on a livré le **commit figé** `124f0cd`, **pas** `main` (qui portait d'autres lots, `j-cartes-pokemon`…).
Ce lot corrige l'écart signalé le 01/10 : **564 cartes `Stage1`/`Stage2` classées `inconnu`**.

```bash
# 0. Portes : CI « CI » verte sur 124f0cd (passage push, success) ; voisins AVANT 200 200 308 200 307 ;
#    serveur sain (charge 0.13, 2500 Mo dispo). Comptes prize_marker AVANT relevés (inconnu=564, ordinaire=16055).
#    (Le run « CI » pull_request du même SHA est en échec à 0 job — démarrage de workflow sur le merge-ref
#    de main, pas un échec de test ; la porte nommée est le passage push, vert.)
# 1. chimera construit — worktree de build (dépôt relais) checkout --detach 124f0cd, HEAD vérifié
#    (pbm-build-lol.sh ne fait PAS son propre checkout, il était resté sur b0df8ae — piège n°1).
#    Build détaché (setsid, survit à la coupure SSH), sondé jusqu'à BUILD_DONE. TS=20261002-005119.
#    Artefact web vérifié : 4 .woff2 sous .next/static/media/, 0 occurrence fonts.googleapis/gstatic.
# 2. transfert chimera → devAI → kailo-srv, SHA-256 identiques aux TROIS étapes :
#    web 7329b919…c60247 · api 54f776a3…ca5c3d
# 3. point de restauration frais AVANT toute écriture :
ssh kailo-srv 'sudo -n -u pokeboy bash /srv/pokeboy/prod/backups/backup.sh'  # pokeboy_prod-20261001-225356.dump (41,5 Mo/26 tables), photos 1051, daté de l'instant
# 4. préparation (n'engage rien ; la migration passe ici) :
ssh kailo-srv 'TS=20261002-005119 COMMIT=124f0cd… LOT=livraison-20261002 bash /tmp/prep-lol.sh'  # → PREPARATION_OK
# 5. bascule, retour arrière automatique sur échec de santé :
ssh kailo-srv 'TS=20261002-005119 bash /tmp/deploy-switch.sh'  # → BASCULE_OK (api=200 web=200 au 1er contrôle)
```

**Migration appliquée** : Alembic `e7c2a9f14b63 → a3f9c2e5b1d4` (`fix_marqueur_stades`) — correction de
**données** : pour toute carte dont `rule_marker` était un stade ordinaire (`Stage1`/`Stage2`, sans espace),
`rule_marker` repasse à NULL et `prize_marker` est recalculé via la **même** fonction pure que l'import
(`corrected_stage_row`). Les vraies Rule Box (`VMAX`, `ex`, `GX`…) sont laissées intactes. Additive et
rejouable ; `downgrade` = no-op explicite (le libellé brut n'est pas reconstituable). Tête après migration :
`a3f9c2e5b1d4 (head)`.

**Preuve du correctif en base** (lecture seule, `pokeboy_prod`, relevée avant/après) :
- `prize_marker = 'inconnu'` : **564 → 0** ✔
- `prize_marker = 'ordinaire'` : 16055 → **16619** (+564) ✔ ; **tous les autres marqueurs inchangés**
  (ex 1248, v 607, gx 472, pokemon_ex 354, vmax 210, mega_ex 175, tag_team 119, vstar 95, m_pokemon_ex 89,
  lv_x 71, break 37, etoile 29, v_union 24, legende 20, radiant 16, prisme_etoile 16, `(null)` 3628).
- `rule_marker` : `Stage1` (422) et `Stage2` (142) **disparus** ; EX/V/GX/VMAX/ESCOUADE… intacts.

**Preuve du code déployé** (`prize_rule_of` de la release, sur de vraies lignes PROD, **sans** appeler la
route IA facturée `GET /cards/{id}/in-game-study`) :
- Arcanine (ex-`Stage1`, désormais `ordinaire`) → **1 Prix** ✔ — avant : « Récompenses non déterminées »
- Méga-Blizzaroi-ex (`mega_ex`) → **3 Prix** ✔
- Dracaufeu et Roussil GX (`tag_team`) → **3 Prix** ✔
- Poké Ball (Dresseur) → hors Pokémon ✔

**Preuve de mise en ligne** : `app/ -> releases/20261002-005119` ; `RELEASE_INFO` porte
`commit=124f0cd8c5bf6a0c4cc90eb2a9c34b8488c429a2` ; les 3 unités `active` ;
`https://pokeboy.lol/api/health` → 200 et `/` → 200. **Voisins inchangés** à chaque étape et à la fin
(`200 200 308 200 307`). Serveur après : charge 0.31, 2527 Mo dispo, 3 unités `active`.

### Pièges rejoués
- **Worktree de build (dépôt relais) resté sur `b0df8ae`** : `checkout --detach 124f0cd` + **vérification du
  HEAD** faits à la main avant le build — piège n°1, toujours réel.
- **PATH non-interactif de chimera** : node/pnpm/uv ajoutés (`~/.local/node/bin`, `~/.local/bin`) au lancement.
- **Trace dépôt** écrite dans un worktree **transitoire** `~/dev/wt-livraison-20261002` (disque système),
  **pas** le clone `~/dev/pokeboy` de la file de lots, supprimé juste après le push. `graphify update` non
  exécuté (doc seule ; le faire toucherait le clone de la file) — à rattraper au prochain entretien de `main`.

## Livraison du jeu — 03/10/2026 — première version jouable, réservée à JF et Aymeric (lot `livraison-jeu-j1`)

Mise en PROD des 13 lots du jalon J1 du jeu (`j-partie-service`, `j-autorite-vues`, `j-file-attente`,
`j-temps-reel`, `j-invitations`, `j-lancement-partie`, `j-salon-partie`, `j-cartes-energies`,
`j-initialisation`, `j-plateau-layout`, `j-plateau-etat-visuel`, `j-plateau-interactions`,
`j-plateau-journal`), tous `integre` dans `etat.json`. Release **`20261003-033245`**, commit figé
**`12bfadd`**, précédente `20261002-005119` (`124f0cd`). Livré depuis **devAI** en session autonome ;
CI « CI » verte sur `12bfadd` (passage push, success).

Le jeu est **privé** (D11) : l'inscription reste libre, mais un compte ordinaire ne voit **rien** du
jeu (404 sur toutes les routes `/games`, `/matchmaking`, et pas d'entrée « Jouer »). L'accès s'accorde
**hors ligne uniquement**, par la CLI d'administration — aucune route HTTP.

### Besoins de la livraison, relevés AVANT de toucher au serveur

- **Migrations** : 7 nouvelles, chaîne à tête unique `a3f9c2e5b1d4 → … → d4e1f2a3b5c6` (game_tables,
  users_game_access, card_effect/trainer_type, fusion, game_invitations, game_launch, game_clocks).
  Aucune têtes multiples — rien à fusionner. Toutes additives.
- **Variables d'environnement** : aucune **obligatoire**. Les lots `j-timer` et `j-deconnexion-abandon`
  ajoutent des réglages (`HORLOGE_*`, `JEU_INACTIVITE_PLAFOND_H`, `JEU_PURGE_ANCIENNETE_J`) **tous
  pourvus de défauts** dans `pbm_api.config` (90/1500/30/10/120 s ; 72 h ; 30 j). `/srv/pokeboy/prod/config/.env`
  **non modifié**.
- **Nouveau processus** : aucun. Le canal temps réel est un **WebSocket servi par l'API uvicorn
  existante** (`WS /games/{id}/ws`, repli HTTP `GET /games/{id}/sync`), pas un service séparé.
  `uvicorn[standard]` embarque `websockets` (17.1 dans le venv construit).
- **Caddy** : **non touché**. L'URL navigateur est `wss://pokeboy.lol/api/games/{id}/ws` ; le bloc
  `handle_path /api/* { reverse_proxy 127.0.0.1:8100 }` existant relaie déjà le WebSocket (Caddy gère
  l'upgrade de façon transparente) et retire le préfixe `/api` attendu par la route FastAPI.

### ⚠️ Nouveau besoin de build : l'API dépend du moteur pur `pbm-game` (`apps/game`)

`apps/api/pyproject.toml` déclare désormais `pbm-game = { path = "../game", editable = true }`
(dépendance **editable**, moteur pur sans dépendance d'exécution). Les artefacts précédents ne
packageaient **que** `apps/api` : tel quel, `uv sync --frozen` sur le serveur échouait à résoudre
`../game`. Deux scripts d'exploitation (hors dépôt) ont été corrigés, de façon idempotente :

- **`~/dev/pbm-build-lol.sh` (chimera)** : produit en plus `game-$TS.tgz` (contenu de `apps/game` à la
  racine du tar, caches exclus), ajouté au `sha256sum` et au marqueur.
- **`/tmp/prep-lol.sh` (kailo-srv)** : extrait `game-$TS.tgz` dans `$REL/game` (sibling de `$REL/api`)
  **avant** `uv sync`, de sorte que `../game` résolve. Sauvegarde : `/tmp/prep-lol.sh.avant-game`.

> Le `~/dev/build-pbm.sh` de devAI (variante à disposition historique, non utilisée pour les livraisons
> `lol` — layout `web/`+`api/`, alors que `prep-lol.sh` attend le contenu à la racine) n'a **pas** été
> modifié : s'il redevient la voie, lui ajouter aussi `apps/game`.

### Ce qui a réellement été exécuté

```bash
# 0. Portes : CI verte sur 12bfadd ; voisins AVANT 200 200 308 200 307 ; serveur sain (charge 0.13, 2505 Mo).
# 1. chimera : worktree de build (dépôt relais) checkout --detach 12bfadd, HEAD vérifié (12bfadd) ;
#    apps/game présent ; pbm-build-lol.sh patché (game-$TS.tgz) ; build détaché (setsid), sondé → BUILD_DONE.
#    → web/api/game-20261003-033245.tgz
# 2. transfert chimera → devAI → kailo-srv, SHA-256 IDENTIQUES aux TROIS étapes :
#    web 210e41b6…d2e0 · api 16b88a34…5296 · game e7ab6371…4500
# 3. point de restauration frais : pokeboy_prod-20261003-013610.dump (43,9 Mo / 26 tables), photos 1053.
ssh kailo-srv 'sudo -n -u pokeboy bash /srv/pokeboy/prod/backups/backup.sh'
# 4. préparation (extrait web+api+game, uv sync, migration ; l'ancienne release sert encore) :
ssh kailo-srv 'TS=20261003-033245 COMMIT=12bfadd… LOT=livraison-jeu-j1 bash /tmp/prep-lol.sh'  # → PREPARATION_OK
# 5. bascule, retour arrière automatique sur échec de santé :
ssh kailo-srv 'TS=20261003-033245 bash /tmp/deploy-switch.sh'  # → BASCULE_OK (api=200 web=200 au 1er contrôle)
```

**Migration appliquée** : `a3f9c2e5b1d4 → d4e1f2a3b5c6`. Tête après migration : `d4e1f2a3b5c6 (head)`.

**Preuve de mise en ligne** : `app/ -> releases/20261003-033245` ; `RELEASE_INFO` porte
`commit=12bfadd9379cfafd409d3b22c3920268829f149c` ; les 3 unités `active` ;
`https://pokeboy.lol/api/health` → 200 et `/` → 200. **Voisins inchangés** du début à la fin
(`200 200 308 200 307`). Serveur après : charge 0.18, 2488 Mo dispo.

### Accès ouvert à JF et Aymeric — et à personne d'autre

Commande (hors ligne, dans le venv de la release) :

```bash
cd /srv/pokeboy/prod/app/api && .venv/bin/python -m pbm_api.admin set-game-access <email> on
```

- **`aymeric.fonteray@gmail.com`** : compte présent en PROD → **accès accordé** ✔ (pseudo « bibi »).
- **`jfonteray@gmail.com`** : **aucun compte en PROD** (la commande refuse, code 1, sur une adresse
  inconnue — jamais de succès silencieux). JF doit **d'abord s'inscrire** sur https://pokeboy.lol,
  puis relancer la commande ci-dessus avec son adresse.
- Audit après coup : un **seul** compte a `game_access=true` (aymeric), sur 4 comptes au total.

### Preuves de fonctionnement en PROD (deux comptes de test jetables, supprimés ensuite)

Script de preuve exécuté dans le venv déployé (crée 2 comptes avec accès + deck jouable, 1 compte
**sans** accès, une partie par le service `creer_partie`, puis supprime tout — aucun vrai compte
touché). **17/17 contrôles PASS** :

- **Fermeture** : compte sans droit → `GET /me` `game_access=false` ; `GET /games`, `/matchmaking/presence`,
  `/games/{id}` → **404** (jamais 403 : pas de fuite d'existence). L'entrée « Jouer » dérive de ce
  drapeau (`app-shell.tsx`), donc invisible pour lui.
- **Canal temps réel** : les deux joueurs ouvrent `WS /api/games/{id}/ws` et reçoivent la
  resynchronisation projetée (numéro 0).
- **Non-fuite** : chaque joueur voit **sa** main comme liste de cartes ; la main adverse n'est qu'un
  **nombre** (`main_nombre`), la clé `main` adverse est **absente**.
- **Coup réel par l'API + diffusion temps réel** : A joue `abandonner` (`POST /games/{id}/actions`,
  HTTP 200) → le moteur déployé l'applique (autorité serveur) → le coup est **diffusé aux DEUX
  joueurs** sur le WebSocket → la partie bascule `terminee`, **vainqueur = B**.
- **Suppression prouvée** : 0 compte de test, 0 partie, 0 deck, 0 carte restants.

### Écart, signalé et non bloquant : l'API joueur n'expose encore que l'abandon

La palette de coups du jalon J1 (`pbm_api.games.actions.PALETTE_COMMANDES`) est `avancer_phase` +
`abandonner` ; la **mise en place interactive**, **attacher une énergie**, **attaquer** et
**l'enchaînement des tours** ne sont **pas encore câblés sur l'API joueur**. Le moteur pur (`apps/game`),
le plateau, le canal temps réel, le cycle de vie des parties et le droit d'accès **sont** en place et
livrés ; ce qui manque est la couche d'orchestration qui joue la mise en place (coup système portant
les `definitions` du catalogue) et expose les coups ciblés. Une partie se crée, se visualise à deux en
temps réel sans fuite, et se termine par abandon — c'est le périmètre réellement jouable aujourd'hui.

## Conclure « déployé » — jamais sur une ligne de journal

Un build qui échoue laisse la plateforme **debout sur l'ancienne version** : tout a l'air normal et
rien n'est livré. La preuve minimale, dans cet ordre :

```bash
systemctl is-active pokeboy-prod-api pokeboy-prod-web pokeboy-prod-worker   # active ×3
curl -s https://pokeboy.lol/api/health                                      # 200
# et la version servie est bien le commit attendu
```

Plus un parcours réel : se connecter, ouvrir la collection, ouvrir une fiche carte.

## Traitements lourds : sur la flotte, jamais sur la machine qui sert

Relevé de prix, import du catalogue, génération par lots, relevé de tournoi : ils tournent **sur
chimera**, et seul le résultat est importé en PROD (`infra/fleet/*.sql`). Le worker de PROD ne garde
que le court — reconnaissance, exports RGPD, e-mails — sous la garde `HEAVY_JOBS_ENABLED`
(**faux par défaut en production**). Runbook complet : `docs/infra/JOBS-LOURDS.md`.

## ⛔ « L'outil est absent » : vérifie le PATH avant de le croire (2026-09-22)

Trois pannes du 22/09, une seule cause. Un lot lancé par `ssh devai 'nohup claude -p …'` est mort à
la seconde : `claude: No such file or directory`, **journal de 41 octets**, aucune branche. Le même
jour, deux lots ont écrit « `gh` CLI absent de cette session » puis se sont déclarés **finis, sans
PR donc sans CI**.

Les trois diagnostics étaient faux : `claude` et `gh` vivent dans `/opt/homebrew/bin`, que le PATH
d'un **ssh non interactif** ne contenait pas. Les binaires étaient là depuis juillet.

Corrigé dans le `~/.zshenv` de devAI, **en fin de PATH** et pas en tête : Homebrew fournit aussi
`node`/`npm`/`npx`, et c'est `~/.local/node/bin` qui doit continuer de gagner.

**La règle** : avant de conclure qu'un outil manque, `command -v <outil>` puis
`ls /opt/homebrew/bin/<outil>`. Introuvable dans un shell non interactif ≠ absent — et « absent »
n'a jamais été une raison de livrer sans CI.

## La PR n'est pas optionnelle

`bash scripts/ouvrir-pr.sh <branche>` ouvre la PR du lot. Il ne se rabat jamais en silence :

| Situation | Code |
|---|---|
| PR déjà ouverte | `0`, et il en donne l'URL |
| Branche déjà fusionnée dans `main` | `0`, en le **disant** (vérifie alors la CI sur `main`) |
| Branche pas poussée, ou pas de remote GitHub | `3` |
| Jeton sans `pull_requests=write` | `4`, avec la cause nommée |
| Machine sans jeton (chimera) | `5`, avec la commande à lancer depuis devAI |

Il **ne dépend pas de `gh`** (absent de la WSL de chimera) : API REST via `curl` et `python3`. Il
trouve seul le bon remote — `origin` sur devAI, `github` sur chimera, dont l'`origin` est un dépôt
relais local **qui retarde**.

Un code ≠ 0 n'autorise pas à conclure : le lot passe en `bloque`, ou nomme le manque **dans son
compte rendu ET dans son dernier message**. Sans PR, le workflow ne tourne pas sur la branche
(il se déclenche sur `pull_request` et sur `push: [main]`), et c'est la CI qui fait foi.

### Pourquoi ça ne marche pas encore tout seul

Quatre identifiants testés le 22/09 — `GITHUB_TOKEN` et `~/.github-token-claude-desktop` sur devAI,
le jeton stocké de `gh`, `~/.config/git/github-token` sur le Mac. **Aucun ne peut ouvrir une PR.**
Ce n'est pas une déduction, GitHub le dit dans l'en-tête de son refus :

```
HTTP/2 403
x-accepted-github-permissions: pull_requests=write
```

`.github/workflows/pr-auto.yml` contourne le problème par le jeton du runner, que GitHub fabrique
lui-même. Il est en place, il **tourne**, et il bute sur un réglage du dépôt :
*« GitHub Actions is not permitted to create or approve pull requests »*.

**Deux corrections, toutes deux chez JF — une seule suffit :**
1. cocher *Settings → Actions → General → Workflow permissions → « Allow GitHub Actions to create
   and approve pull requests »* → **toutes** les PR s'ouvrent seules, pour toujours ;
2. ou ajouter *Pull requests: write* au jeton fine-grained → `ouvrir-pr.sh` fonctionne.

Tant qu'aucune n'est faite, `pr-auto` **reste rouge exprès** — un lot sans PR n'a pas de CI, ça doit
se voir — mais son message dit que le code n'est pas en cause et donne le lien d'ouverture manuelle.

## Retour arrière

Les versions précédentes restent dans `/srv/pokeboy/prod/releases/` : revenir en arrière, c'est
refaire pointer `app/` sur la version précédente et redémarrer les trois services. Une migration de
base déjà appliquée, elle, ne se défait pas toute seule — c'est le point à vérifier **avant** de
livrer une migration destructive.

> **À éprouver** : le compte rendu de `v5-prod` laisse deux points ouverts — « sauvegardes à
> éprouver sur une vraie restauration » et « surveillance à compléter ». Tant que la restauration
> n'a pas été essayée pour de vrai, on ne sait pas si on a des sauvegardes : on a des fichiers.

## Configuration par variables d'environnement

`apps/api` lit sa configuration via `pbm_api.config.Settings` (pydantic-settings, fichier `.env`
optionnel) : `DATABASE_URL`, `REDIS_URL`, `S3_ENDPOINT_URL`/`S3_ACCESS_KEY`/`S3_SECRET_KEY`/
`S3_BUCKET`/`S3_REGION`, `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/`SMTP_FROM`,
`SECRET_KEY`/`APP_PUBLIC_URL`/`API_PUBLIC_URL`/`SESSION_COOKIE_NAME`/`CSRF_COOKIE_NAME`/
`SESSION_TTL_DAYS`/`EMAIL_TOKEN_TTL_MINUTES`/`LOGIN_RATE_LIMIT_MAX_ATTEMPTS`/
`LOGIN_RATE_LIMIT_WINDOW_SECONDS` (comptes, lot `v1-auth` — `SECRET_KEY` signe les jetons CSRF,
à définir par variable d'environnement en dehors du dépôt pour tout déploiement ;
`API_PUBLIC_URL`, lot `v5-rgpd`, est l'origine de l'API elle-même, distincte d'`APP_PUBLIC_URL` —
le lien de téléchargement d'export envoyé par e-mail pointe dessus), `AI_KEY_ENCRYPTION_KEY`
(coffre de clés IA, lot `v1-byok` — clé maître AES-256 en base64, 32 octets ; chiffre/déchiffre
les clés des utilisateurs, à définir par variable d'environnement hors dépôt pour tout
déploiement), `PLATFORM_ANTHROPIC_API_KEY`/`INSIGHTS_BUDGET_EUR`/`INSIGHTS_BATCH_MODEL`/
`INSIGHTS_BATCH_CHUNK_SIZE` (insights par lots, lot `v4-insights-batch` — clé PLATEFORME
distincte de toute clé d'utilisateur et plafond de dépense cumulé, vides/nuls par défaut : sans
eux, `scripts/run_insights_batch.py` refuse de dépenser quoi que ce soit ; à fournir par JF hors
dépôt, D4), `HORLOGE_PAR_TOUR_S`/`HORLOGE_PAR_JOUEUR_S`/`HORLOGE_PAR_DECISION_S`/
`HORLOGE_TOLERANCE_RESEAU_S`/`HORLOGE_PAUSE_DECONNEXION_S` (horloges d'une partie, lot `j-timer`,
DJ4 — en secondes), `JEU_INACTIVITE_PLAFOND_H`/`JEU_PURGE_ANCIENNETE_J` (lot
`j-deconnexion-abandon` — le **plafond** au-delà duquel une partie sans activité est close d'office
par le cron léger `games_maintenance_task` du worker, et l'ancienneté au-delà de laquelle une partie
morte est purgée ; défauts 72 h / 30 j, les changer ne demande pas de redéployer le moteur). Ce cron
de maintenance des parties est **léger** et tourne sur tous les nœuds, y compris la PROD (il n'est
pas sous la garde `HEAVY_JOBS_ENABLED`).
Chaque lot pointe sa propre base/bucket/préfixe — ne jamais réutiliser ceux d'un autre lot sur
l'infra partagée (`pbm-shared`). `apps/web` lit `NEXT_PUBLIC_API_URL` (défaut
`http://localhost:8000`) et `NEXT_PUBLIC_SESSION_COOKIE_NAME` (défaut `pbm_session`, doit
rester alignée avec `SESSION_COOKIE_NAME` côté API : le middleware de garde de route ne lit que
la présence de ce cookie, `apps/web/src/middleware.ts`). `apps/api` accepte les requêtes
cross-origin du front (`CORSMiddleware`, origine = `APP_PUBLIC_URL`, `allow_credentials=True`
pour le cookie de session) — obligatoire dès qu'ils tournent sur des ports/domaines différents.
`apps/web` lit aussi `NEXT_PUBLIC_UPLOAD_ORIGIN` (lot `v5-e2e`, doit rester alignée avec
`S3_ENDPOINT_URL` côté API quand `STORAGE_BACKEND=s3` — vide/absente avec `STORAGE_BACKEND=local`) :
la CSP `connect-src` du middleware (lot `v5-securite`) doit inclure l'origine du stockage objet,
sinon le `PUT` présigné direct du navigateur vers le stockage S3 est bloqué et **tout envoi de photo
échoue** — trouvé en faisant tourner un vrai envoi par le navigateur pour la première fois
(`parcours-complet.spec.ts`), jamais exercé avant par les e2e précédentes (résultat toujours semé
directement en base).

> Les pages d'authentification et leurs chemins (`/verifier`, `/reinitialiser`…) sont décrits
> dans `docs/UI-UX.md` : ce sont des écrans, pas de la configuration.
