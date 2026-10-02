# Compte rendu — `j-invitations` — Inviter quelqu'un à jouer : par pseudo ou par lien

**Jalon** J1 · **piste** Serveur de parties · **couloir** J-SRV (chimera) · **machine** devAI (pilote) + chimera (exécution)

## Résumé

Lot **serveur** (J-SRV) : on invite quelqu'un de précis plutôt que de chercher un inconnu dans la
file d'attente. Modélisation de l'**invitation** (par pseudo ou par lien à usage unique), de son
cycle de vie (envoyée → acceptée / refusée / annulée / expirée), et du **salon d'attente à deux**
que les deux joueurs partagent avant le lancement. L'écran du salon est le lot aval `j-salon-partie`
(J-UI) ; le choix/contrôle de deck et le tirage au sort sont `j-lancement-partie` : ici on **annonce**
un deck, on ne lance pas la partie.

## Livrables

- **Modèle** `GameInvitation` (`apps/api/src/pbm_api/models/invitations.py`) + migration
  `b9d4e2a7c1f0_game_invitations.py` (tête alembic unique). Jeton de lien stocké **haché** (SHA-256),
  decks annoncés en `SET NULL`.
- **Service** `pbm_api.games.invitations` : `inviter_par_pseudo`, `inviter_par_lien`, `accepter`,
  `accepter_par_lien`, `refuser`, `annuler`, `recues`, `envoyees`, `salon`. Expiration paresseuse.
  Moteur `pbm_game` **non touché** (aucune règle de jeu ici — lot d'infrastructure).
- **Routes** `/invitations` (`pbm_api.routers.invitations`), toutes gardées par `require_game_access`
  (D11), écritures sous CSRF ; branchées dans `main.py`.
- **Relais e-mail** de l'invitation reçue (pseudo) via l'`EmailSender` existant ; in-app =
  `GET /invitations/recues`. PWA prévue pour `j-notifications-jeu`.
- **Doc** : section « Inviter quelqu'un à jouer » dans `docs/ARCHITECTURE.md`.

## Preuves

- **Tests du lot** : `tests/test_invitations_service.py` (12) + `tests/test_invitations_routes.py`
  (5) → **17 passés**. Base de test dédiée `pbm_j_invitations_test` (motif des lots précédents),
  `alembic upgrade head` OK, tête unique `b9d4e2a7c1f0`.
- **Suite complète api** sur chimera : **961 passés, 2 échecs** — les deux dans
  `test_catalogue_seed.py`, cause `pg_dump: command not found` (binaire absent de la WSL de chimera),
  **sans rapport avec ce lot** ; la CI GitHub (qui a les outils client Postgres) les exécute.
- **ruff** : `All checks passed!` sur toute l'api.
- **Critères d'acceptation** :
  - *Un lien ne sert qu'une fois et expire* → `test_lien_usage_unique` (service + route, second usage
    = 409) et `test_invitation_expiree` (échéance passée = non acceptable).
  - *Une invitation n'ouvre aucun droit au-delà de la partie (D11)* → `test_lien_nouvre_aucun_droit`
    (`game_access` inchangé) et `test_lien_nouvre_aucun_acces` (compte non invité → 404).
  - *Les deux joueurs voient le même salon et le même deck annoncé* → `test_salon_symetrique`
    (service, vues strictement égales) et `test_pseudo_bout_en_bout_meme_salon` (route, `salon_a == salon_b`).
  - *Isolation (accès croisé)* → `test_salon_tiers_404` / `test_salon_tiers_introuvable` (un tiers → 404).

## Grille des tâches

| Tâche | État | Preuve |
|---|---|---|
| `dev` | fait | service + routes + modèle + migration ; branché dans `main.py` |
| `tests` | fait | 17 tests du lot verts ; suite complète 961 verts (2 échecs pg_dump hors sujet) |
| `securite` | fait | `require_game_access` (D11) sur toutes les routes, CSRF sur les écritures, accès croisé → 404, jeton de lien jamais en clair ni journalisé, `game_access` jamais modifié |
| `maquette` | sans objet | lot **serveur** (J-SRV) ; l'écran du salon est le lot aval `j-salon-partie` (J-UI) |
| `doc_tech` | fait | section dans `docs/ARCHITECTURE.md` ; docstrings françaises sur tous les ajouts |
| `release_uat` | fait | recette locale sur chimera (base `pbm_j_invitations_test`) |
| `release_prod` | sans objet | aucun déploiement dans ce lot (la PROD se livre à part, par devAI) |
| `backlog` | n/a | tenu par la file (etat.json non touché) |
| `compte_rendu` | fait | ce fichier |

## Écarts au plan

- **Pas d'écran** : `j-invitations` est un lot J-SRV. La « Maquette du jeu » / le salon visuel sont
  `j-salon-partie` (J-UI). Le salon est livré comme **API symétrique**, socle des lots aval.
- **TTL d'invitation** : défaut pilote de 7 jours (`TTL_INVITATION`), modifiable ; aucune décision
  JF ne le fixe. À confirmer si besoin.
- **2 tests `test_catalogue_seed.py`** rouges sur chimera faute de `pg_dump` dans la WSL — gap
  d'environnement, pas une régression ; la CI fait foi.

## Reste à faire (hors périmètre, lots aval)

- `j-lancement-partie` : à partir d'un salon accepté, choix/contrôle de deck, prêt à jouer, tirage au
  sort, création de la `Game` (`pbm_api.games.service.creer_partie` prend déjà deux `(user, deck)`).
- `j-salon-partie` (J-UI) : l'écran du salon qui consomme `GET /invitations/{id}/salon`.
- `j-notifications-jeu` : relais PWA de l'invitation reçue (le seam e-mail est déjà posé).
