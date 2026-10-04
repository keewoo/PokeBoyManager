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

### Rétro-remplissage du catalogue (colonnes de jouabilité) — une seule fois

`import_weekly.sql` est **INSERT-ONLY** : il n'a jamais rempli les colonnes ajoutées à la chaîne le
02/10/2026 (`energy_type`, `element_type`, `stage`, `prize_marker`, `trainer_type`, `effect`) sur les
cartes **déjà en PROD**. Toutes les cartes chargées avant cette date sont donc restées `NULL` sur ces
colonnes, et en jeu `definition_depuis_card` **bloque** un Pokémon sans `stage` ou sans `prize_marker`
(R-7, on ne devine pas) : c'est la cause des très rares cartes jouables observée le 03/10. Le lot
`cat-stades` livre le rattrapage.

À faire **une fois**, pendant la livraison qui embarque `cat-stades`, avec le **même bundle** que
l'import hebdo (`cards.tsv` dans `/tmp/pbm-import/`) :

```bash
sudo -u postgres psql -d pokeboy_prod -f infra/fleet/backfill_cards.sql
```

Le script affiche le compte de Pokémon sans `stage` / `prize_marker` / `element_type` **avant et
après**. Il ne remplit que ce qui est `NULL` en PROD **et** renseigné dans la référence (`COALESCE` +
garde `WHERE`) : une valeur déjà posée n'est jamais écrasée, une colonne légitimement vide reste vide.
**Idempotent** — un second passage ne change plus rien. Validé le 04/10 sur une base clonée de la
référence (50 cartes simulées « pré-02/10 » rattrapées, un témoin déjà rempli laissé intact).

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

## Tentative de livraison des coups du joueur — 03/10/2026 — **BLOQUÉE** (bug de projection, retour arrière)

Lot `livraison-jeu-coups`, pour mettre en PROD `j-coups-joueur` (les vrais coups : mise en place
interactive, attacher une énergie, attaquer, enchaînement des tours). Commit figé
**`eb0ecfcf22b5d6755c3f2dda104fcf7218718242`** (`integre` dans `etat.json`, CI « CI » verte au
passage push). La bascule a **réussi** et la plateforme était saine, mais la **preuve de
fonctionnement a échoué** : un bug de la couche de projection rend le jeu injouable par l'API/le
temps réel. **Retour arrière immédiat sur la release J1** (`20261003-033245`, `12bfadd`). Aucun
changement d'accès. PROD debout sur J1.

### Ce qui a réellement été exécuté

```bash
# 0. Portes : CI « CI » verte sur eb0ecfc (push, success) ; voisins AVANT 200 200 308 200 307 ;
#    serveur sain (charge 0.09, 2461 Mo). Besoins relevés AVANT : AUCUNE migration (diff vide côté
#    versions/), AUCUNE variable d'environnement nouvelle (aucun getenv/settings ajouté dans
#    apps/api|apps/game), AUCUN nouveau processus, Caddy NON concerné (le WebSocket passe déjà par
#    le reverse_proxy /api existant). Seuls apps/api + apps/game changent (code pur) + doc-web.
# 1. chimera : worktree de build (dépôt relais) checkout --detach eb0ecfc, HEAD vérifié (eb0ecfc) ;
#    apps/game présent, dép. editable ../game déclarée ; pbm-build-lol.sh (game-aware) ; build
#    détaché (setsid), sondé → BUILD_DONE. TS=20261003-125043. Artefact web : 4 .woff2, 0 googleapis,
#    15 pokeboy.lol, 0 acx-connect.
# 2. transfert chimera → devAI → kailo-srv, SHA-256 IDENTIQUES aux TROIS étapes :
#    web 632421c3…f9c1 · api 04d2a582…3952 · game f5f1e104…b855
# 3. point de restauration frais AVANT toute écriture :
ssh kailo-srv 'sudo -n -u pokeboy bash /srv/pokeboy/prod/backups/backup.sh'  # pokeboy_prod-20261003-105435.dump (46,5 Mo / 32 tables), photos 1053
# 4. préparation (extrait web+api+game, uv sync ; `alembic upgrade head` = NO-OP, tête inchangée) :
ssh kailo-srv 'TS=20261003-125043 COMMIT=eb0ecfc… LOT=livraison-jeu-coups bash /tmp/prep-lol.sh'  # → PREPARATION_OK, tête d4e1f2a3b5c6 avant ET après
# 5. bascule, retour arrière automatique sur échec de santé :
ssh kailo-srv 'TS=20261003-125043 bash /tmp/deploy-switch.sh'  # → BASCULE_OK (api=200 web=200)
# — bascule en ligne vérifiée : app/ -> 20261003-125043, RELEASE_INFO commit=eb0ecfc, 3 unités active,
#   /api/health 200, / 200, voisins 200 200 308 200 307. Puis PREUVE DE JEU → échec (ci-dessous).
# 6. RETOUR ARRIÈRE délibéré sur J1 :
ssh kailo-srv 'TS=20261003-033245 bash /tmp/deploy-switch.sh'  # → BASCULE_OK release=20261003-033245
#   Vérifié : app/ -> 20261003-033245, commit=12bfadd, 3 unités active, health 200, voisins inchangés.
```

### Le bug : 7 types d'événements sans projecteur → 500 sur le premier vrai coup

La preuve a été menée par un script dans le venv déployé (2 comptes jetables avec accès + decks
jouables réels — attaquant Pikachu « Charge » 60 dégâts + énergies ; cibles Duo Tag 60 PV à 3
récompenses — 1 compte sans accès). **Fermeture, accès, non-fuite et suppression : PASS.** Mais dès
le premier coup réel de mise en place :

```
POST /games/{id}/actions (placer_mise_en_place) → HTTP 500
ValueError: Événement « placement_cache » sans projecteur … (pbm_game/sortie/evenements.py:111)
  ← projeter_resultat (projection.py:96) ← play_action (routers/games.py:168)
```

**Cause.** `pbm_game.sortie.evenements.PROJECTEURS` déclare un projecteur par type d'événement, et
`projeter_evenement` **refuse** (garde D9, « aucun repli silencieux ») tout type absent. Or le lot
`j-coups-joueur` (et la mise en place) émettent **sept** types qui ne sont **pas** dans ce registre :
`energie_attachee` (nouveau, `cartes/attache.py`), `placement_cache`, `mulligan`, `main_revelee`,
`mise_en_place_prete`, `mise_en_place_revelee`, `fin_tour`. Tout coup ou toute resync qui en émet un
passe par `projeter_resultat` (réponse HTTP de `POST /actions` **et** diffusion `HUB.publier` du
canal temps réel) ou par `resynchroniser` (resync WebSocket depuis 0), et **lève → 500**. Observé :
WebSocket A/B n'ont reçu **aucune** resync (0), la mise en place émettant ces événements au
`demarrer_partie`.

**Pourquoi la CI est verte quand même.** `test_games_partie_complete.py` et `test_partie_complete.py`
jouent la partie via `appliquer_action`/`reprendre_partie` — qui **ne passent pas** par
`projeter_resultat`/`projeter(evenements)`. Le chemin de **sortie autoritaire** (projection des
événements vers un client HTTP ou WebSocket) n'est donc **jamais exercé** pour ces événements. Le
compte rendu du lot le signalait à demi-mot : le critère « le plateau joue ces coups dans un
navigateur (e2e à deux contextes) » était coché « Reste à faire », faute de navigateur Playwright sur
la flotte.

### Décision

Le défaut est **systémique** (7 types d'événements) et **sensible à la sécurité** : plusieurs de ces
projecteurs décident d'une **non-fuite** (un mulligan ou `main_revelee` **révèle une main**, R-4.4 ;
le contenu d'un `placement_cache` doit rester **caché** à l'adversaire). Les écrire correctement est
une **décision de conception** du moteur, pas un correctif anodin à poser en autonomie sur un chemin
sécurité. Conformément aux règles (« au moindre doute, tu ne livres pas et tu l'écris » ; « une PROD
debout vaut mieux qu'une PROD cassée »), **retour arrière sur J1** et lot bloqué. Le public n'est pas
concerné (le jeu est privé, D11 — JF/Aymeric) ; J1 reste jouable jusqu'à l'abandon, comme avant.

**Correctif à faire dans un lot de suite (moteur + CI) :** déclarer les sept projecteurs manquants
dans `PROJECTEURS`, en tranchant la non-fuite de chacun (public, propriétaire-seul, ou retrait des
`instance_id`), **et** poser un test qui **exerce la projection** (`projeter_resultat` /
`resynchroniser`) sur une partie jouée — pas seulement `appliquer_action` — pour qu'un futur
événement sans projecteur casse en CI, pas en PROD. Idéalement un test de **parité** : tout type
d'`Evenement` produit par le moteur doit avoir une entrée dans `PROJECTEURS`.

La release non déployée `20261003-125043` (commit eb0ecfc) reste dans `releases/` (non pointée) ;
`graphify update` non exécuté (trace doc seule, depuis un worktree transitoire).

## Coups du joueur — 2ᵉ tentative, 03/10/2026 — **toujours BLOQUÉE**, cette fois **sans toucher à la PROD**

Le lot `livraison-jeu-coups` a été relancé (file B). Rien n'a changé dans `main` depuis le blocage de
13:07 : le HEAD est `a12b106` (trace doc seule), `j-coups-joueur` est toujours `integre` à `eb0ecfc`,
et **aucun correctif de projection n'a été fusionné**. Le défaut décrit ci-dessus est donc intact —
vérifié dans le code de `eb0ecfc`/`a12b106`, pas supposé :

- `apps/game/src/pbm_game/sortie/evenements.py` : `PROJECTEURS` ne contient toujours que 17 types ;
- `apps/game/src/pbm_game/journal/modele.py` définit bien `EVT_ENERGIE_ATTACHEE`, `EVT_MAIN_REVELEE`,
  `EVT_MULLIGAN`, `EVT_MISE_EN_PLACE_PRETE`, `EVT_PLACEMENT_CACHE`, `EVT_MISE_EN_PLACE_REVELEE`,
  `EVT_FIN_TOUR` — les sept absents du registre. La preuve de jeu exigée (poser, **attacher une
  énergie**, attaquer) émet dès `attacher_energie` l'`EVT_ENERGIE_ATTACHEE` → `ValueError` → 500.

**Décision de cette passe : ne PAS re-déployer.** Re-livrer `eb0ecfc` referait exactement la bascule
de 13:07 — santé verte, puis échec de la preuve de jeu, puis retour arrière nº 2 : une perturbation de
PROD pour un résultat connu d'avance. « Une PROD debout vaut mieux qu'une PROD cassée » : on ne touche
pas au serveur. **État PROD vérifié (lecture seule)** : `app/` → `releases/20261003-033245` (J1,
`12bfadd`), les 3 unités `pokeboy-prod-{api,web,worker}` `active`, `pokeboy.lol` 200, `/api/health` ok,
`pokeboy.acx-connect.com` redirige 308 ; voisins canoniques `200 200 308 200 307`. Accès jeu inchangé
(privé, D11). Public non concerné.

**Correctif, précisé (allège la crainte « décision sensible » de la 1ʳᵉ passe).** La relecture des
docstrings de `journal/modele.py` **et des sites d'émission** montre que les sept sont **publics par
construction** — le correctif est donc bien défini, pas un arbitrage de non-fuite ouvert :

| Événement | Pourquoi public | Projecteur |
|---|---|---|
| `energie_attachee` | la carte quitte la main (cachée) pour une zone publique (attachée) | `_public` |
| `main_revelee` | R-4.4 : seul moment où une main est **volontairement** montrée à l'adversaire | `_public` |
| `mulligan` | nombre de mulligans + carte bonus due = faits publics | `_public` |
| `mise_en_place_prete` | résumé public de la phase (compteurs) | `_public` |
| `placement_cache` | n'émet **que** `{"joueur": jid}` — aucun contenu (vérifié `mise_en_place/transitions.py:327`) | `_public` |
| `mise_en_place_revelee` | R-4.2/R-4.3 : révélation **simultanée** publique des deux placements | `_public` |
| `fin_tour` | joueur + phase quittée | `_public` |

Mais cela **reste un changement du moteur** (`apps/game`), donc un **lot de code gaté** (worktree +
branche `roadmap/*` + PR + CI + intégration par l'ordonnanceur) — pas un correctif posé depuis une
session de livraison, et de toute façon la livraison ne pourrait pas se conclure ici (devAI ne fusionne
pas lui-même). Le lot de suite doit : (1) ajouter les sept entrées à `PROJECTEURS` ; (2) poser un
**test de parité** qui échoue si **un** type d'`Evenement` journalisé par le moteur n'a pas d'entrée
dans `PROJECTEURS` (c'est lui qui couvre l'exhaustif — d'autres types internes existent côté effets/DSL,
à vérifier qu'ils ne transitent pas par la projection) ; (3) un test qui **exerce le chemin de sortie**
(`projeter_resultat`/`resynchroniser`) sur une partie jouée, pas seulement `appliquer_action` — c'est le
trou de CI qui a laissé passer le bug. Une fois ce lot `integre`, relancer `livraison-jeu-coups`.

## Livraison des coups du joueur — 03/10/2026 — **RÉUSSIE** (la partie se joue vraiment en PROD)

Troisième passe de `livraison-jeu-coups`, cette fois le correctif est en place. Mise en PROD de
`j-coups-joueur` (mise en place interactive, poser, attacher une énergie, attaquer, enchaînement des
tours, victoire par les récompenses) **plus** le correctif `fix-projection-evenements` qui débouche
les deux tentatives bloquées du 03/10 (13:07, 13:22) : les sept (puis quatorze) projecteurs manquants
qui faisaient répondre 500 au premier vrai coup. Release **`20261003-182045`**, commit figé
**`733aff8adf287feb1b9f2c019996dd2ffb85e198`**, précédente `20261003-033245` (`12bfadd`, J1). Livré
depuis **devAI** en session autonome ; CI « CI » verte sur `733aff8` (passage push, success, 15:56Z).
Le jeu reste **privé** (D11) : JF et Aymeric uniquement.

### Besoins de la livraison, relevés AVANT de toucher au serveur (`git diff 12bfadd..733aff8`)

- **Migrations** : **aucune**. Aucun fichier sous `apps/api/migrations/versions/` ne change ; la tête
  reste `d4e1f2a3b5c6`. `alembic upgrade head` à la préparation = **NO-OP** (tête identique avant/après).
- **Variables d'environnement** : **aucune** ajoutée (aucun `getenv`/`Settings` nouveau dans `apps/api`
  ni `apps/game`). `/srv/pokeboy/prod/config/.env` **non modifié**.
- **Nouveau processus** : **aucun**. Le temps réel reste le WebSocket servi par l'API uvicorn existante.
  Le lot `j-simulation-bots` (présent dans `733aff8`) ajoute le paquet `apps/game/src/pbm_sim` — un
  **outil CLI** de campagnes de masse (vue seule), **pas un service** : aucune unité, aucune dépendance
  d'exécution nouvelle (diff `pyproject` vide).
- **Caddy** : **non touché**. Le WebSocket `wss://pokeboy.lol/api/games/{id}/ws` passe par le
  `reverse_proxy` `/api` existant (upgrade transparent), déjà prouvé en J1.
- Changent : `apps/api` + `apps/game` (code pur), `apps/web` (commentaires `doc-web` + fixtures de test,
  **aucun changement de comportement**), et de la doc/roadmap.

### Ce qui a réellement été exécuté

```bash
# 0. Portes : CI « CI » verte sur 733aff8 (push, success) ; voisins AVANT 200 200 308 200 307 ;
#    serveur sain (charge 0.12, 2403 Mo dispo). PROD de départ : J1 20261003-033245 (12bfadd), tête d4e1f2a3b5c6.
# 1. chimera : worktree de build (dépôt relais) checkout --detach 733aff8, HEAD vérifié (733aff8) ;
#    apps/game présent, dép. editable ../game déclarée ; pbm-build-lol.sh (game-aware) ; build détaché
#    (setsid), sondé → BUILD_DONE. TS=20261003-182045. Artefact web : 4 .woff2, 0 googleapis/gstatic
#    dans le CSS servi (les 2 occurrences de l'artefact sont l'outillage @next/font de node_modules,
#    jamais chargé par le navigateur — vérifié sur la page LIVE), 15 pokeboy.lol, 0 acx-connect.
# 2. transfert chimera → devAI → kailo-srv, SHA-256 IDENTIQUES aux TROIS étapes :
#    web 3cd72aaa…b5bcf8 · api c44c8d3f…14c0c4e · game 1629f378…bd45f6
# 3. point de restauration frais AVANT toute écriture :
ssh kailo-srv 'sudo -n -u pokeboy bash /srv/pokeboy/prod/backups/backup.sh'  # pokeboy_prod-20261003-162435.dump (46,5 Mo / 32 tables), photos 1053
# 4. préparation (extrait web+api+game, uv sync, alembic = NO-OP ; l'ancienne release sert encore) :
ssh kailo-srv 'TS=20261003-182045 COMMIT=733aff8… LOT=livraison-jeu-coups bash /tmp/prep-lol.sh'  # → PREPARATION_OK, tête d4e1f2a3b5c6 avant ET après
# 4b. contrôle AVANT bascule (venv de la release, l'ancienne sert encore) : parité des projecteurs
#     — les 7 types qui faisaient 500 (placement_cache, energie_attachee, mulligan, main_revelee,
#     mise_en_place_prete, mise_en_place_revelee, fin_tour) ont tous un projecteur ; seuls dsl_choix
#     et dsl_primitive restent nommément DIFFÉRÉS (effets de carte, aucune partie J1 ne les émet).
# 5. bascule, retour arrière automatique sur échec de santé :
ssh kailo-srv 'TS=20261003-182045 bash /tmp/deploy-switch.sh'  # → BASCULE_OK (api=200 web=200 au 1er contrôle)
```

**Preuve de mise en ligne** : `app/ -> releases/20261003-182045` ; `RELEASE_INFO` porte
`commit=733aff8adf287feb1b9f2c019996dd2ffb85e198`, `lot=livraison-jeu-coups` ; les 3 unités `active` ;
`https://pokeboy.lol/api/health` → 200 et `/` → 200. **Voisins inchangés** du début à la fin
(`200 200 308 200 307`). Serveur après : charge 0.06, 2478 Mo dispo, 3 unités `active`. CSS servi :
**0** `fonts.googleapis`/`gstatic`, **4** `.woff2` locaux en 200 (polices embarquées).

### Accès ouvert à JF et Aymeric — et à personne d'autre

Commande (hors ligne, venv de la release) :
`cd /srv/pokeboy/prod/app/api && .venv/bin/python -m pbm_api.admin set-game-access <email> on`.

- **`aymeric.fonteray@gmail.com`** : `game_access=true` déjà en place → **laissé tel quel** ✔.
- **`jfonteray@gmail.com`** : **aucun compte en PROD** (4 comptes au total, lu en base) → **rien créé**,
  conformément à la règle (jamais de succès silencieux). JF doit **d'abord s'inscrire** sur
  https://pokeboy.lol, puis on lancera la commande ci-dessus avec son adresse.
- Audit après livraison : un **seul** compte a `game_access=true` (aymeric).

### Preuves de fonctionnement en PROD — partie complète par HTTP + WebSocket (27/27 PASS)

Script de preuve exécuté dans le venv déployé, dirigé contre le **serveur uvicorn LIVE**
(`127.0.0.1:8100`) : 2 comptes jetables **avec** accès + decks jouables réels (attaquant « Charge »
60 dégâts + énergies ; cibles Duo Tag 60 PV à 3 récompenses, graine et UUID fixes → mulligan
reproductible), 1 compte jetable **sans** accès. Puis **suppression de tout** (aucun vrai compte
touché).

- **Fermeture** (compte sans droit) : `GET /me` `game_access=false` ; `GET /games`,
  `GET /games/{id}`, `GET /matchmaking/presence` → **404** (jamais 403 : pas de fuite d'existence).
- **WebSocket** : les deux joueurs ouvrent `WS /api/games/{id}/ws` (Origin exigé — un canal **sans
  Origin est refusé**, anti-CSWSH) et reçoivent la **resync du coup #0**, qui projette précisément les
  événements de mise en place (`mulligan`, `main_revelee`, `mise_en_place_prete`, `cartes_piochees`,
  `pioche_melangee`) — **le chemin qui répondait 500** aux deux tentatives bloquées : plus de 500.
- **Partie complète jouée par l'API** : `placer_mise_en_place` (le coup même qui faisait 500),
  `attacher_energie` (émet `energie_attachee`, naguère 500), `declarer_attaque`, `poser`, `promouvoir`,
  `avancer_phase` — **tous HTTP 200** — jusqu'à la **victoire par les six récompenses**
  (`raison_fin=derniere_recompense`, vainqueur = A). Chaque coup **diffusé aux DEUX joueurs** sur le
  WebSocket (13 diffusions).
- **Non-fuite**, contrôlée par destinataire sur des vues post-coup simultanées : aucun joueur ne voit
  la main courante de l'autre (dans sa réponse HTTP, son état, sa diffusion WS) ; la main adverse n'est
  qu'un **nombre** ; la **graine** ne sort jamais (`/sync`).
- **Rejeu depuis le journal** : `GET /games/{id}/sync?depuis=0` (200) pour chaque joueur, et
  `reprendre_partie` reconstruit l'état final (terminée, vainqueur A) avec vérification d'empreinte.
- **Suppression prouvée** : 0 compte de test, 0 partie, 0 deck, 0 carte/set restants.

### Périmètre réellement jouable aujourd'hui

Une partie se crée, se joue **vraiment** à deux (mise en place, poser, attacher, attaquer,
enchaînement des tours) jusqu'à la victoire par récompenses, en temps réel et sans fuite, et se rejoue
depuis son journal. **Pas encore** : les cartes **Dresseur** et les **talents/effets de carte** (le
système d'effets — `dsl_choix`, `dsl_primitive`, `demande_*` — est nommément **différé** au lot des
effets ; aucune partie J1 ne les émet, et le moteur refuse — 500 bruyant, jamais une fuite — tout
événement d'effet tant que leur projection par destinataire n'est pas livrée).

### Pièges rejoués / notés

- **Worktree de build (dépôt relais) resté sur `eb0ecfc`** : `checkout --detach 733aff8` +
  vérification du HEAD avant le build — piège n°1, toujours réel.
- **PATH non-interactif de chimera** : `~/.local/node/bin`, `~/.local/bin` ajoutés au lancement du build.
- **Cookie de session PROD `Secure`** : un client HTTP sur `http://127.0.0.1:8100` ne le renvoie pas
  tout seul — la preuve porte le jeton en en-tête `Cookie` explicite (sinon 401 au lieu de 404/200).
- **Trace** écrite dans un worktree **transitoire** `~/dev/wt-livraison-coups` (disque système),
  **pas** le clone `~/dev/pokeboy` de la file de lots, supprimé juste après le push. `graphify update`
  non exécuté (doc seule ; le code `733aff8` est déjà graphifié sur `main` par son lot de fusion).

## Livraison de l'entraînement et de l'IA — 03/10/2026 — **RÉUSSIE** (on joue contre le bot en PROD)

Mise en PROD de `livraison-jeu-solo-ia` : quatre lots du jeu solo/IA fusionnés dans `main` —
`j-simulation-bots`, `j-mode-solo` (entraînement contre un bot), `j-adversaire-ia` (l'IA du joueur
comme adversaire, sur **sa** clé), `j-coach-ia` (conseil sur demande + bilan de fin de partie).
Release **`20261003-204554`**, commit figé **`c5084ad0dd0a78250d6954bb0f84eda7fc2fb4f5`**,
précédente `20261003-182045` (`733aff8`, coups du joueur). Livré depuis **devAI** en session
autonome ; CI « CI » verte sur `c5084ad` (passage push, success). Le jeu reste **privé** (D11) :
JF et Aymeric uniquement.

### Besoins de la livraison, relevés AVANT de toucher au serveur (`git diff 733aff8..c5084ad`)

- **Migrations** : **trois**, toutes **additives**, chaîne linéaire → tête unique **`b2c3d4e5f6a7`**
  (`d4e1f2a3b5c6` → `f1c0b07a1d02` mode-solo → `a1b2c3d4e5f6` adversaire-ia → `b2c3d4e5f6a7`
  coach-ia). Colonnes avec `server_default` (`games.entrainement`, `game_players.bot_niveau`/
  `adversaire_ia`, `games.ia_appels`/`ia_tokens`/`conseils_utilises`, `users.coach_actif`,
  `game_events.commentaire`) + **un compte bot réservé** inséré par `f1c0b07a1d02`
  (`pokebot@system.pokeboy.invalid`, `password_hash='!'` inconnectable, `game_access=false`,
  `ON CONFLICT DO NOTHING`). `alembic upgrade head` à la préparation : **appliqué** (NO-OP la fois
  précédente, cette fois trois révisions jouées), rollback sûr (additif).
- **Variable d'environnement** : **une** nouvelle, optionnelle — `COACH_MAX_CONSEILS` (défaut `3`,
  plafond de conseils par partie). **Non ajoutée** à `/srv/pokeboy/prod/config/.env` : le défaut
  convient, `.env` **non modifié**.
- **Nouveau processus** : **aucun**. Le temps réel reste le WebSocket servi par l'API uvicorn.
  `pbm_sim` (lot `j-simulation-bots`) est un **outil CLI** de campagnes de masse, pas un service.
- **Routes nouvelles** (toutes sous `/api`, aucun changement Caddy) : `POST /matchmaking/entrainement`
  (choix `adversaire` bot/ia + `niveau`), `GET /matchmaking/presence` (champ `ia_disponible`),
  `POST /games/{id}/conseil`, `GET /games/{id}/bilan`, et `GET /games/{id}` enrichi
  (`entrainement`, `bot_niveau` au siège, `ia_cout`). Vérifiées **présentes dans le schéma servi**.
- **Caddy** : **non touché** (le `reverse_proxy /api` relaie déjà le WebSocket, prouvé en J1).
- **front `apps/web`** : aucun changement de comportement (les lots J-SRV n'ont pas câblé le front ;
  le bundle ne cite que `pokeboy.lol`, 0 ancien domaine).

### Ce qui a réellement été exécuté

```bash
# 0. Portes : CI verte sur c5084ad (push) ; voisins AVANT 200 200 308 200 307 ; serveur sain
#    (charge 0.02, 2480 Mo dispo). PROD de départ : 20261003-182045 (733aff8), tête d4e1f2a3b5c6.
# 1. chimera : worktree de build (dépôt relais) checkout --detach c5084ad, HEAD vérifié ; apps/game
#    présent, dép. editable ../game ; pbm-build-lol.sh (game-aware) ; build détaché (setsid), sondé →
#    BUILD_DONE. TS=20261003-204554. Bundle : 15 fichiers pokeboy.lol, 0 ancien domaine.
# 2. transfert chimera → devAI → kailo-srv, SHA-256 IDENTIQUES aux TROIS étapes :
#    web 0bbd2874…11ea80 · api 77e26e19…d542da · game 041daf70…1beef4
#    (⚠ décodage base64 sur macOS : `base64 -D`, pas `-d` — `-d` rend un fichier vide en silence)
# 3. point de restauration frais AVANT toute écriture :
ssh kailo-srv 'sudo -n -u pokeboy bash /srv/pokeboy/prod/backups/backup.sh'  # 20261003-184940.dump (46,5 Mo / 32 tables), photos 1053
# 4. préparation (extrait web+api+game, uv sync, alembic upgrade head → 3 révisions jouées) :
ssh kailo-srv 'TS=20261003-204554 COMMIT=c5084ad… LOT=livraison-jeu-solo-ia bash /tmp/prep-lol.sh'  # → PREPARATION_OK, tête d4e1f2a3b5c6 → b2c3d4e5f6a7
# 5. bascule, retour arrière automatique sur échec de santé :
ssh kailo-srv 'TS=20261003-204554 bash /tmp/deploy-switch.sh'  # → BASCULE_OK (api=200 web=200 au 1er contrôle)
```

**Preuve de mise en ligne** : `app/ -> releases/20261003-204554` ; `RELEASE_INFO` porte
`commit=c5084ad…`, `lot=livraison-jeu-solo-ia` ; les 3 unités `active` ; `https://pokeboy.lol/api/health`
→ 200 et `/` → 200 ; tête Alembic **LIVE** = `b2c3d4e5f6a7`. **Voisins inchangés** du début à la fin
(`200 200 308 200 307`). Serveur après : charge 0.18, 2472 Mo dispo.

### Accès ouvert à JF et Aymeric — et à personne d'autre

Commande (hors ligne, venv de la release) :
`cd /srv/pokeboy/prod/app/api && .venv/bin/python -m pbm_api.admin set-game-access <email> on`.

- **`aymeric.fonteray@gmail.com`** : `game_access=true` déjà en place ; commande rejouée (idempotente) → **reste ouvert** ✔.
- **`jfonteray@gmail.com`** : **aucun compte en PROD** (5 comptes au total, dont le bot réservé) → la
  commande **refuse** (`Erreur : Aucun compte pour jfonteray@gmail.com.`, rc=1 — jamais de succès
  silencieux). **Rien créé** : JF doit d'abord s'inscrire sur https://pokeboy.lol, puis on lancera
  la commande avec son adresse.
- Audit après livraison : **un seul** compte humain a `game_access=true` (aymeric).

### Preuves de fonctionnement en PROD — 14/14 PASS, puis suppression de tout

Script de preuve exécuté dans le venv déployé, dirigé contre le serveur uvicorn **LIVE**
(`127.0.0.1:8100`) : comptes jetables (A avec accès + deck possédé jouable « Charge » 60 ; B **sans**
accès ; C 2ᵉ humain), sessions forgées en base (l'e-mail de vérification part par Resend en PROD,
illisible ici — on ne passe donc pas par `register/verify`), jeton de session en cookie explicite +
CSRF. Puis **suppression de tout**.

- **Fermeture** (B, sans droit) : `/me` `game_access=false` ; `GET /games`, `GET /games/{id}`,
  `GET /matchmaking/presence` → **404** (jamais 403 : pas de fuite d'existence).
- **Présence** (A, sans clé IA) : `ia_disponible=false`.
- **Adversaire IA sans clé** : `POST /matchmaking/entrainement {adversaire:"ia"}` → **422** nommant
  la clé **et** le bot (« … pour jouer contre ton IA. Tu peux jouer contre le bot en attendant »).
- **Partie d'entraînement contre le bot, jouée jusqu'au bout** : `POST /matchmaking/entrainement`
  (201, bot au siège 1, `bot_delai_ms=800`), marquée `entrainement=true` ; jouée par HTTP
  (`/games/{id}/state` → coups légaux → `/games/{id}/actions`, tous 200), le bot répond côté serveur,
  jusqu'à une **fin méritée** (`raison_fin=plus_de_pokemon`, jamais `abandon`). **WebSocket** :
  resync du coup #0 reçue, **9 trames** reçues (resync + diffusions des coups).
- **Non-fuite** : la main adverse n'est qu'un nombre, la graine n'apparaît jamais dans `/state`.
- **Anti-CSWSH** : un WebSocket **sans en-tête `Origin`** est **refusé** (`InvalidStatus`).
- **Coach** : `GET /games/{id}/bilan` sans clé → **422** (nomme la clé) ; `POST /games/{id}/conseil`
  en partie d'entraînement sans clé → **422** (nomme la clé) ; `POST /games/{id}/conseil` dans une
  partie **entre deux humains** → **409** (« un conseil n'est disponible qu'en partie d'entraînement »)
  — la garde « hors entraînement » tombe **avant** la garde de clé (prouvé même sans clé).
- **Suppression prouvée** : `comptes_restants=0 parties_restantes=0 cartes_restantes=0` ;
  `COMPTES_TOTAL_APRES=5` (les comptes réels + le bot réservé, intacts). Voisins inchangés après.

### Périmètre réellement jouable aujourd'hui

On lance « S'entraîner » et on joue **vraiment** une partie contre le **bot** (mise en place, poser,
attacher, attaquer, enchaînement des tours) jusqu'à la victoire, en temps réel et sans fuite. L'IA
adversaire et le coach sont **branchés et gardés** ; **sans clé IA de plateforme sur devAI**
(`~/.pokeboy-secrets/platform-anthropic-key` **absente** ; la clé d'Aymeric **jamais** utilisée), on
a prouvé le **chemin sans clé** (422 qui nomme la clé et renvoie au bot) plutôt que de dépenser la
clé d'un tiers. **Pas encore** : les cartes **Dresseur** ni les **talents/effets** (différés) ; le
**front du salon** (bouton « S'entraîner », choix bot/IA, rendu des conseils) n'est pas câblé — les
quatre lots étaient couloir serveur (J-SRV).

### Pièges rejoués / notés

- **Worktree de build resté sur `733aff8`** : `fetch github` + `checkout --detach c5084ad` +
  vérification du HEAD avant le build — piège n°1, toujours réel.
- **chimera en WSL/PowerShell** : lancer le build via `wsl -u upgreg -- bash -l -s` sur **stdin**
  (jamais la ligne de commande, que PowerShell mâche) ; handshake SSH qui `reset` → réessayer.
- **Décodage base64 sur macOS** : `base64 -D` (pas `-d`, qui rend un fichier **vide sans erreur** —
  le SHA-256 trahit alors un fichier vide `e3b0c442…`). Le `.b64` était intact ; seul le décodage
  local était faux — inutile de retransférer.
- **Trace** écrite dans un worktree **transitoire** `~/dev/wt-livraison-solo-ia` (disque système),
  **pas** le clone `~/dev/pokeboy` de la file de lots, supprimé juste après le push. `graphify update`
  non exécuté (doc seule ; le code `c5084ad` est déjà graphifié sur `main` par ses lots de fusion).

## Livraison des scripts d'effets IA — 2026-10-04 — **périmètre réduit, signalé** (code + données, pas les scripts IA)

Lot `livraison-effets-ia`. Mise en PROD du chantier effet fusionné dans `main` (`j-cartes-attaques-effets`,
`j-cartes-objets`, `j-cartes-supporters`, `j-cartes-regles-speciales`, `j-cartes-talents`,
`j-effets-catalogue-compilation`, `j-effets-couverture-outil`, `j-effets-assistance-ia`,
`j-plateau-decisions`, `cat-stades`) **plus** l'import flotte des données d'effet du catalogue.
Release **`20261004-161201`**, commit figé **`5efffd3`**
(`5efffd33f0416f8e9c54c4f0d62cee33a86c769c`), précédente `20261003-204554` (`c5084ad`, solo/IA).
Livré depuis **devAI** en session autonome ; CI « CI » verte sur `5efffd3` (push, success). Jeu
privé (D11) : JF et Aymeric uniquement.

### ⚠️ Le cœur attendu — les scripts d'effet écrits par l'IA — N'A PAS pu être livré

Le passage IA (décision **DJ8**, plafond 50 €) qui écrit les scripts de cartes **n'a jamais été
lancé** : `j-effets-assistance-ia` a livré l'**outillage** mais, à la lettre de DJ8, **aucune dépense
réelle** (« le passage réel est une opération à lancer depuis devAI »). Vérifié : **aucun
`card_scripts`** n'existe nulle part (table absente en PROD avant ce lot, table absente de la
référence `pbm_catalogue_ref` de chimera, aucun grand livre `var/assistance_scripts/ledger.json` sur
devAI). **Ce lot de livraison n'a pas lancé ce passage** : mon prompt m'instruit de *lire* son rapport
et de *livrer* des scripts existants, pas d'exécuter une génération IA de 50 € ; et DJ8 veut un
**rapport par famille remis à JF pour arbitrage** avant mise en jeu, impossible en session autonome.

**Conséquence, mesurée par le tableau de couverture LIVE** : 181 effets distincts dans les
collections des deux joueurs, **0 scripté**, cartes à effet **0 % jouables**. Les vraies cartes à
effet (et les collections d'Aymeric et de JF, qui en sont faites) **restent non jouables** tant que le
passage n'a pas tourné. Ce qui est livré ici est la **fondation** (moteur, registre, couverture,
règles spéciales, données du catalogue) : une fois le passage lancé et ses familles validées par JF,
les `card_scripts` s'importent en PROD **par SQL flotte, sans redéploiement de code**.

### Besoins relevés AVANT de toucher au serveur (`git diff c5084ad..5efffd3`)

- **Migrations** : **3**, additives, tête unique `b2c3d4e5f6a7 → c3a7f1e9d2b4 → b7d3f1a2c9e4 →
  c9d4e7a1b3f8` (`card_scripts`, `card_play_requests`, colonnes de revue IA + contrainte CHECK
  `ck_card_scripts_scripte_gate`). `j-cartes-talents` : aucune migration.
- **Variables d'environnement** : **aucune obligatoire**. `assistance_budget_eur`/`assistance_model`
  (défauts) servent l'outillage **sur devAI**, pas la PROD. `.env` **non modifié**.
- **Nouveau processus** : **aucun**. Temps réel = WebSocket de l'API uvicorn existante.
- **Routes** : `/me/demandes-cartes` (file de demandes), sous `/api`. **Caddy non touché**.
- **Parité de projection** : le défaut qui a bloqué la livraison « coups » est désormais couvert par
  `test_parite_evenements_projecteurs.py` en CI ; `dsl_choix`/`dsl_primitive`/`demande_*` restent
  nommément différés (émis seulement par une carte scriptée, donc jamais tant que `card_scripts` est vide).

### Le catalogue de PROD porte désormais les données d'effet (import flotte)

AVANT (PROD) : Pokémon avec stade **2 425**, cartes avec effet **0**, Dresseurs avec effet **0**.
Export `infra/fleet/export_cards.sql` depuis `pbm_catalogue_ref` (chimera) → `cards.tsv` (22 653
lignes, sha `ed228452…`, SHA-256 vérifié chimera→devAI→kailo-srv), puis `infra/fleet/backfill_cards.sql`
(NULL-only, clé `tcgdex_id`, idempotent) après backup frais. APRÈS : stade **19 368** (+16 943),
effet **3 043**, Dresseurs avec effet **2 849**. Écart résiduel assumé : 833 sans stade / 921 sans
`element_type` (cartes absentes du bundle de référence ou vides des deux côtés). Ce backfill débloque
la jouabilité des cartes **vanille** (un Pokémon sans stade était bloqué, R-7).

### Ce qui a réellement été exécuté

```bash
# 0. Portes : CI verte sur 5efffd3 ; voisins AVANT 200 200 308 200 307 ; serveur sain (charge 0.25, 2397 Mo).
# 1. chimera : worktree de build (dépôt relais) checkout --detach 5efffd3, HEAD vérifié ; apps/game
#    présent ; pbm-build-lol.sh (game-aware) ; build détaché (setsid), sondé → BUILD_DONE. TS=20261004-161201.
#    Artefact web : 4 .woff2, 0 googleapis/gstatic dans le CSS servi, 15 pokeboy.lol, 0 acx-connect.
# 2. transfert chimera → devAI → kailo-srv, SHA-256 IDENTIQUES aux TROIS étapes :
#    web 299945cd… · api 5ec2e933… · game a1249dac…
# 3. backup frais : pokeboy_prod-20261004-141539.dump (48,9 Mo / 32 tables), photos 1053.
# 3b. import flotte : backfill_cards.sql (cards.tsv sha ed228452…) → stades 2425→19368, effet 0→3043.
ssh kailo-srv 'sudo -u postgres psql -d pokeboy_prod -f /tmp/backfill_cards.sql'
# 4. préparation (extrait web+api+game, uv sync, migration) :
ssh kailo-srv 'TS=20261004-161201 COMMIT=5efffd3… LOT=livraison-effets-ia bash /tmp/prep-lol.sh'  # → PREPARATION_OK, b2c3d4e5f6a7→c9d4e7a1b3f8
# 5. bascule, retour arrière automatique sur échec de santé :
ssh kailo-srv 'TS=20261004-161201 bash /tmp/deploy-switch.sh'  # → BASCULE_OK (api=200 web=200)
```

**Migration appliquée** : `b2c3d4e5f6a7 → c9d4e7a1b3f8` (3 révisions, additives). Tête LIVE `c9d4e7a1b3f8`.

### Preuves (code déployé + vraie base PROD)

- **Mise en ligne** : `app/ -> releases/20261004-161201` ; `RELEASE_INFO` commit=`5efffd3`,
  lot=`livraison-effets-ia` ; 3 unités `active` ; `pokeboy.lol/api/health` 200, `/` 200 ; tête Alembic
  en base `c9d4e7a1b3f8` ; `card_scripts` (0 ligne) et `card_play_requests` existent.
- **Tableau de couverture LIVE** : 181 effets, **0 scripté**, 0 % de cartes à effet jouables,
  blocueurs **nommés** (« aucun script écrit pour ce texte d'effet »), jamais un 500. bibi 105/0 jouable,
  jf 21/0 jouable.
- **Partie réelle en PROD — 14/14 PASS** (venv déployé, base PROD, 2 comptes jetables avec accès + 1
  sans, puis suppression de tout, **0 résidu vérifié**) : la **porte D9** refuse un deck à carte-effet
  en nommant la carte (« aucun script pour ce texte d'effet — effet non implémenté, carte refusée ») et
  laisse passer un deck vanille ; la **projection** (`resynchroniser` depuis 0, le chemin qui faisait
  500 à la livraison « coups ») projette la mise en place **sans 500 ni fuite** pour les deux joueurs,
  la partie vanille va jusqu'à la **victoire par les récompenses** (`placer_mise_en_place` joué), la
  graine ne sort jamais, non-fuite vérifiée par ÉGALITÉ d'`instance_id` ; **fermeture** (compte sans
  accès → routes jeu 404, code inchangé). *(La preuve « ≥3 cartes au script IA » exigée par le prompt
  est impossible faute de scripts : on prouve à la place le refus propre d'une carte à effet.)*
- **Accès jeu** : **aymeric.fonteray@gmail.com** (bibi) laissé ouvert ; **jfonteray@gmail.com** (jf),
  **inscrit depuis le 03/10**, a déjà `game_access=true` → confirmé idempotent. Audit : **2 comptes**
  ouverts (eux deux), **personne d'autre** (6 comptes au total).
- **Voisins inchangés** du début à la fin (`200 200 308 200 307`). Serveur après : charge 0.08, 2451 Mo
  dispo, 3 unités `active`.

### Reste à faire (nommé, non masqué)

1. **Lancer le passage IA DJ8 (50 €)** depuis devAI (clé posée `~/.pokeboy-secrets/platform-anthropic-key`),
   remettre le **rapport par famille à JF** pour arbitrage, puis importer `card_scripts` en PROD par SQL
   flotte (sans redéploiement). **C'est ce qui rendra jouables les vraies cartes à effet** — y compris
   les collections d'Aymeric et de JF, aujourd'hui à 0 carte jouable.
2. **833 Pokémon sans stade / 921 sans element_type** en PROD : absents du bundle ou vides des deux côtés.
3. **Front du salon** (bouton « S'entraîner », badge « Effet non géré », bouton « Je voudrais jouer
   cette carte ») : câblage front à finir.

### Pièges rejoués / notés

- **Worktree de build (dépôt relais) resté sur `c5084ad`** : `fetch github` + `checkout --detach 5efffd3`
  + **vérification du HEAD** avant le build — piège n°1, toujours réel.
- **`main` avançait sous la session** : une file parallèle fusionnait `j-cartes-talents` dans le clone
  partagé pendant la préparation → on fige le **commit SHA** (`5efffd3`) et on build CE commit, jamais
  le HEAD mouvant du clone.
- **Détecteur de non-fuite** : comparer par **égalité** d'`instance_id`, jamais par sous-chaîne (`:d1`
  est un préfixe de `:d15`) — une première passe criait à tort à la fuite.
- **Trace** écrite dans un worktree **transitoire** `~/dev/wt-livraison-effets-ia` (disque système),
  **pas** le clone `~/dev/pokeboy` de la file de lots, supprimé juste après le push. `graphify update`
  non exécuté (doc seule ; le code `5efffd3` est déjà graphifié sur `main` par ses lots de fusion).

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
