# `j-mise-en-ligne-jeu` — Mettre le jeu en ligne sur le serveur partagé

**Livré en PROD le 19/10/2026.** Release `20261019-133755`, commit `f46dc76`, précédente
`20261005-134110` (`ab77675`). Conduit **à la main depuis devAI** (la PROD n'est pas scriptée dans
la file de lots, et l'en-tête des lots chimera leur interdit tout déploiement). Jeu **privé** (D11) :
JF et Aymeric uniquement.

## Ce que cette livraison emporte

Les **22 lots du jeu** fusionnés depuis le 05/10 : de `j-anim-socle` à `j-profil-jeu`. Diff
`ab77675..f46dc76` : **392 fichiers, 65 452 insertions**.

Relevé fait **avant** de toucher au serveur, et c'est lui qui a rendu la livraison sans surprise :

| Besoin | Verdict |
|---|---|
| Migrations | **12**, et une **seule tête** (`d7f2a9c3e1b6`) — les lots parallèles avaient fusionné les leurs (deux migrations de fusion) |
| Variables d'environnement | **aucune obligatoire** : `SUPERVISION_EMAIL` et `JEU_PARTIES_SIMULTANEES_MAX` ont un défaut dans `config.py`. `/srv/pokeboy/prod/config/.env` **non modifié** |
| Nouveau processus / unité systemd | **aucun** |
| Caddy | **non touché** |
| Dépendances | `onnxruntime` est en `optional-dependencies` (`decoupe`), **délibérément hors production** ; `axe-core` est en dev |

## Ce qui a réellement été exécuté

```bash
# 0. Portes : CI « CI » verte sur f46dc76 ; voisins AVANT 200 200 308 200 307 ; serveur sain
#    (charge 0,14 · 2 369 Mo dispo · disque 63 %). PROD de départ : 20261005-134110, tête c9d4e7a1b3f8.
# 1. chimera construit — worktree de build (dépôt relais) checkout --detach f46dc76, HEAD VÉRIFIÉ.
ssh chimera 'wsl … -- bash -s' < lance-build.sh     # setsid, survit à la coupure SSH → BUILD_DONE
#    TS=20261019-133755 · web 25,1 Mo · api 1,16 Mo · game 503 Ko
#    Artefact web contrôlé : 4 .woff2, 0 googleapis/gstatic dans le CSS, 18 fichiers pokeboy.lol, 0 acx-connect.
# 2. transfert chimera → /mnt/c/tmp/pbm → devAI (/Volumes/Data/DevAI/pokeboy/tmp/) → kailo-srv.
#    SHA-256 IDENTIQUES aux TROIS étapes : web 45a268b3…c906 · api 22e69ceb…2369 · game c5819a83…9f34
# 3. point de restauration frais AVANT toute écriture :
ssh kailo-srv 'sudo -n -u pokeboy bash /srv/pokeboy/prod/backups/backup.sh'
#    → pokeboy_prod-20261019-222026.dump (85 044 648 octets, 34 tables), photos 1 139 entrées (275 Mo)
# 4. préparation (n'engage rien : l'ancienne release sert encore) :
ssh kailo-srv 'sudo -n -u pokeboy bash …/.livraison/prep-lol.sh 20261019-133755 f46dc76… j-mise-en-ligne-jeu'
#    → PREPARATION_OK · tête c9d4e7a1b3f8 → d7f2a9c3e1b6 (les 12 migrations, dont 2 de fusion)
# 5. bascule, retour arrière automatique sur échec de santé :
ssh kailo-srv 'bash …/.livraison/deploy-switch.sh 20261019-133755'
#    → BASCULE_OK, santé revenue au 2e essai (~5 s), 3 unités actives
```

### ⚠️ Les scripts de livraison avaient disparu

`/tmp/prep-lol.sh` et `/tmp/deploy-switch.sh` ont été **purgés avec `/tmp`** du serveur. Aucune
copie : ni sur kailo-srv, ni sur chimera, ni sur devAI. Seul `pbm-build-lol.sh` avait survécu,
parce qu'il vit dans `~/dev` de chimera.

Ils ont été **réécrits depuis leur comportement**, que `docs/LIVRAISON.md` consignait livraison
après livraison — c'est ce report qui a rendu la reconstruction possible, et c'est l'argument pour
continuer à le faire. Ils sont désormais **dans le dépôt** (`infra/livraison/`) et copiés dans la
release qu'ils servent (`releases/<TS>/.livraison/`), **jamais dans `/tmp`**.

Un détail qui aurait coûté une livraison : la santé interne se mesure sur **`/health`**, pas
`/api/health` — l'API est montée à la racine, Caddy retire le préfixe (`handle_path`). Un contrôle
sur `/api/health` rend 404 et aurait déclenché un retour arrière à chaque bascule.

### La fenêtre où le schéma est en avance sur le code

Entre l'étape 4 et l'étape 5, les 12 migrations sont appliquées **pendant que l'ancien code tourne**.
Mesuré à cet instant précis : `pokeboy.lol` 200, `/api/health` 200, trois unités actives. Les
migrations sont donc additives — vérifié, pas supposé. C'était le vrai risque de cette livraison.

## Preuve de mise en ligne

- `app/ -> releases/20261019-133755` ; `RELEASE_INFO` porte `commit=f46dc76…`, `lot=j-mise-en-ligne-jeu`.
- Les trois unités `active` ; `pokeboy.lol/` **200** (0,36 s), `/api/health` **200**.
- Tête Alembic **LIVE** : `d7f2a9c3e1b6 (head)`.
- **Le nouveau code est bien là**, pas seulement « ça répond » : `pbm_api/observabilite/` et
  `pbm_api/notifications/` sont présents dans la release en service.
- **Voisins inchangés** du début à la fin : `200 200 308 200 307`.
- Serveur après : charge 0,11 · 2 531 Mo dispo · disque 64 %.

### Une partie réellement jouée en production — gagnée dans les règles

Partie `7643a94b-af96-40d5-a1a3-b007cddb526f`, créée par la **file d'attente** (appariement réel),
**14 coups** de la mise en place à la fin, par **deux comptes** et par le chemin public
(`https://pokeboy.lol/api` → Caddy → uvicorn), pilotée par `scripts/prouver_partie_prod.py`.

**Vainqueur A, raison `plus_de_pokemon`** : son Actif mis K.O. et son banc vide, B n'a personne à
promouvoir — deuxième voie de victoire de **R-14.1** (adossée à **R-8.9**). Familles exercées :
`placer_mise_en_place` ×2, `attacher_energie` ×3, `jouer_objet` ×1, `avancer_phase` ×6,
**`declarer_attaque` ×2**. Le rendu de carte est passé aussi : l'Actif porte son `rendu`
(`origine: officielle`), donc `j-rendu-carte` fonctionne en PROD.

⛔ **Deux pièges de la preuve, qui l'auraient rendue creuse** :

1. **L'abandon est toujours légal.** Un pilote qui joue « le premier coup légal » abandonne au
   premier tour : première tentative « terminée en 4 coups, raison=abandon ». Une partie perdue
   volontairement ne prouve rien. Le pilote exclut donc l'abandon.
2. **Le coup s'appelle `declarer_attaque`, pas `attaquer`** — `attaquer` est le nom de la *famille*
   dans `pbm_game.actions.familles_jeu`. Deuxième tentative : **82 coups, zéro attaque**, partie
   finie par `pioche_impossible` (R-14.2). Une vraie fin de partie… où personne n'a jamais frappé.
   C'est le genre de preuve verte qui ne prouve pas ce qu'elle annonce.

Et **R-6.1** explique le reste : le joueur qui commence ne peut pas attaquer à son premier tour.

### Ce que la preuve a créé est supprimé, et c'est prouvé

`scripts/purger_preuve_partie.py` (bornes dures : motif d'adresse, extension `e2epartie`, plafond
de 6 comptes, `--a-blanc` d'abord). **APRÈS : 0 compte de preuve, 0 extension `e2epartie`** —
4 comptes, 4 parties, 4 decks, 5 cartes et l'extension retirés.

**Audit D11 après livraison** : 6 comptes au total, **2 accès au jeu** — `jfonteray@gmail.com` et
`aymeric.fonteray@gmail.com`, personne d'autre.

Artefacts en transit sur devAI supprimés (`/Volumes/Data/DevAI/pokeboy/tmp/`, règle de flotte).

## Retour arrière

`deploy-switch.sh` le fait **tout seul** si la santé ne revient pas en 60 s : il remet `app/` sur la
release précédente, redémarre, et le dit (`BASCULE_ANNULEE`). Si ni la nouvelle ni l'ancienne ne
répondent, il le hurle au lieu de le taire (`BASCULE_ANNULEE_ET_MALADE`, sortie 5).

À la main : `sudo -u pokeboy ln -sfnT /srv/pokeboy/prod/releases/20261005-134110 /srv/pokeboy/prod/app`
puis `sudo systemctl restart pokeboy-prod-{api,worker,web}`.

⚠️ **Écart assumé : le retour arrière n'a PAS été exécuté pour de vrai** sur cette livraison. Le
chemin automatique n'a pas été déclenché (la santé est revenue au 2e essai), et l'éprouver aurait
demandé de couper volontairement la production. Les 12 migrations étant additives, l'ancien code
tourne sur le nouveau schéma — c'est **mesuré** (voir la fenêtre ci-dessus), donc le retour arrière
est sûr sur le papier, mais il reste **à éprouver**. C'est le même point ouvert que `v5-prod`
laissait sur les sauvegardes, et il reste ouvert.

## Reste à faire

- **Éprouver le retour arrière pour de vrai**, sur une fenêtre choisie — pas en pleine livraison.
- **Éprouver une restauration de sauvegarde** : point ouvert depuis `v5-prod`. Tant qu'elle n'a pas
  été essayée, on a des fichiers, pas des sauvegardes.
- Le **bilan de fin de partie** exige une clé IA au compte (422 sans elle) : normal, mais la preuve
  ne l'exerce donc pas.
- `prouver_partie_prod.py` ne couvre pas le **WebSocket** (il joue en HTTP) : la diffusion temps
  réel n'est pas exercée par cette preuve, seule la résolution par le journal l'est.
