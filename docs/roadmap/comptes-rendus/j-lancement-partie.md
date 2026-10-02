# Compte rendu — `j-lancement-partie`

**Lot** : Lancement — choix du deck, contrôle, prêt à jouer, tirage au sort du premier joueur.
**Jalon** J1 · piste Serveur de parties · couloir J-SRV (exécuté sur **chimera**, piloté depuis devAI).
**Branche** `roadmap/j-lancement-partie` · base `github/main` (`f5d512c`).

## Résumé

Entre le **salon d'attente à deux** (`j-invitations`) et la **partie en cours** (`j-partie-service`),
ce lot pose la **machine de lancement persistée** qui conduit deux joueurs jusqu'au coup d'envoi :

1. **préparation** — chaque camp choisit son deck parmi les siens et se déclare prêt ; le deck est
   recontrôlé (propriété, scripts D9, **possession**) à chaque étape ;
2. **tirage** — dès que les deux sont prêts, le serveur tire la graine, **publie son engagement**
   *avant* le pile ou face R-4.7 (`FLUX_QUI_COMMENCE`), puis fait le tirage ; le gagnant choisit de
   commencer ou non (livret R-1.1), avec un **délai** et un **choix par défaut** (le gagnant commence) ;
3. **lancé** — le choix tranché, les decks recontrôlés une dernière fois, la partie est créée
   (`creer_partie`) avec **cette** graine et le premier joueur assis au siège 0 ;
4. **abandonné** — un joueur quitte avant le lancement : figé, aucune partie fantôme.

Le serveur fait autorité (le tirage tombe côté serveur, l'écran ne montre que l'animation). Le tirage
est **vérifiable après coup** : engagement publié avant, graine révélée seulement à la fin de partie,
pile ou face recalculable hors du serveur.

## Livrables

| Fichier | Rôle |
|---|---|
| `apps/api/src/pbm_api/models/game_launch.py` | table `game_launches` (machine à états persistée) |
| `apps/api/migrations/versions/c7e2b1a9f4d3_game_launch.py` | migration (down_revision `b9d4e2a7c1f0`, tête unique) |
| `apps/api/src/pbm_api/games/lancement.py` | service : préparation, tirage, choix, défaut, abandon, vérif légalité+possession |
| `apps/api/src/pbm_api/routers/lancement.py` | routes `/lancements` (GET + preparer/choisir/abandonner) |
| `apps/api/src/pbm_api/models/__init__.py`, `main.py` | export du modèle, enregistrement du routeur |
| `apps/api/tests/test_lancement_service.py` (14) · `test_lancement_routes.py` (4) | preuves |
| `docs/jeu/LANCEMENT.md` | fiche : machine, R-4.7/R-1.1, commit-reveal, contrôle deck |

## Preuves

- **Tests du lot** : `17 passed in 5.58s` (`tests/test_lancement_service.py tests/test_lancement_routes.py`).
- **Suite API complète** : `978 passed, 2 failed` en 4 min 21 s. Les **2 échecs sont étrangers au lot**
  (`tests/test_catalogue_seed.py`, 0 référence à mon code) : ils tombent sur `pg_dump: command not
  found` — l'outil client PostgreSQL n'est pas installé dans la WSL de chimera ; en CI il l'est. Mes
  modèles/routeur/main n'ont rien cassé.
- **ruff** : `All checks passed!` sur tous les fichiers du lot.
- **Migration** : `alembic upgrade head` applique `c7e2b1a9f4d3` sur une base vierge, **tête unique**
  (`alembic heads` → `c7e2b1a9f4d3`).
- **Tirage vérifiable** (critère) : `test_tirage_verifiable_apres_la_partie` — après fin de partie, la
  graine révélée permet `verifier_engagement(graine, engagement)` et `rejouer_tirage(graine, tirage)`
  à l'identique ; `verifier_journal` ne relève aucune anomalie. Avant la fin, `graine is None`.
- **Reprise après F5** (critère) : `test_preparation_puis_tirage_etape_par_etape` — chaque `GET`
  rend le statut courant ; `test_choix_par_defaut_apres_le_delai` prouve la reprise + défaut.
- **Deck devenu injouable, sans partie fantôme** (critère) : `test_deck_vendu_arrete_le_lancement_sans_partie`
  et route `test_deck_vendu_422` — une carte vendue (possession retirée) arrête le lancement en 422
  nommant la carte ; le lancement reste en tirage, `game_id is None`, **aucune ligne `games`**.
- **Isolation** : `test_tiers_ne_voit_pas_le_lancement` (service) et `test_tiers_404` (route, compte C
  **avec** accès au jeu mais sans rôle → 404). `test_sans_acces_404` (D11).

## Critères d'acceptation

- [x] Le tirage est vérifiable après coup par les deux joueurs.
- [x] Un rechargement pendant la mise en place reprend à la bonne étape.
- [x] Un deck devenu injouable arrête le lancement avec sa raison, sans partie fantôme.

## Écarts / décisions (à l'attention de JF)

1. **R-4.7 vs livret (R-1.1) — choix laissé au gagnant.** `docs/jeu/REGLES.md` R-4.7 dit « au hasard
   (pile ou face) qui commence », sans mentionner de choix. Le lot demandait explicitement « le choix
   laissé au gagnant du tirage (commencer ou non) », qui vient du **livret officiel** (source de vérité
   R-1.1). J'ai implémenté le choix du gagnant, **avec le gagnant qui commence comme choix par défaut**
   — ce qui retombe exactement sur la lecture littérale de R-4.7. Si JF préfère le pile ou face sec
   (sans choix), il suffit de forcer `commencer=True` côté client : la mécanique du tirage ne change pas.
   Détail dans `docs/jeu/LANCEMENT.md`.
2. **Légalité de format / taille (60 cartes, max 4) non imposée au lancement.** Le contrôle du lot est
   **propriété + scripts D9 + possession** (exactement « carte vendue, script retiré »). La légalité
   tournoi reste déférée à `j-initialisation` (report déjà documenté dans `pbm_api.games.entry`) — pas
   un abandon silencieux. Au J1 (« laid mais juste »), l'imposer rendrait les decks minimaux injouables.
3. **Observation hors lot — persistance des invitations.** `pbm_api.games.invitations` ne **commit**
   jamais (il ne fait que `flush`), alors que `get_session` ne commit pas non plus ; en production les
   écritures d'invitation risqueraient de ne pas être persistées (les tests ne le voient pas : ils
   partagent la session et roulent en savepoint). **Mon service commit explicitement** (contrat suivi
   par `pbm_api.games.service`). À vérifier / corriger dans un lot dédié — je n'ai pas élargi le mien.
4. **Écran (maquette).** Lot **serveur** (couloir J-SRV) : l'écran de lancement (choix de deck,
   animation du pile ou face, compte à rebours) est une pièce **front** d'un lot UI ultérieur. L'API
   est dessinée pour l'alimenter : `LancementOut` porte `engagement`, `tirage`, `tirage_gagnant`,
   `premier_joueur`, `choix_expire_at` (échéance pour le compte à rebours) et `game_id` (bascule).

## Reste à faire

- Écran de lancement (lot UI) : consommer `/lancements/{invitation_id}` et ses transitions, animer le
  pile ou face et le compte à rebours à partir de `choix_expire_at`.
- Reprise gracieuse si un deck devient injouable **pendant** le tirage : aujourd'hui le choix renvoie
  422 et le lancement reste en tirage (recours : `abandonner`). Un retour en préparation serait plus doux.
- `j-initialisation` partira de la partie créée ici (graine + premier joueur) pour la vraie mise en
  place (mélange, main de sept, mulligans, actif/banc, six récompenses).

## Grille

| Tâche | État | Preuve |
|---|---|---|
| `dev` | fait | service + routeur + modèle + migration (tête unique) |
| `tests` | fait | 17/17 du lot verts ; suite API 978 passed (2 échecs `pg_dump` hors lot) |
| `securite` | fait | isolation 404 (service + route), D11, graine jamais exposée avant fin, autorité serveur |
| `maquette` | déféré | lot serveur ; API dessinée pour l'écran (voir écart 4) |
| `doc_tech` | fait | `docs/jeu/LANCEMENT.md` + docstrings françaises (le *pourquoi*) |
| `release_uat` | fait | recette locale sur chimera (base `pbm_jlp_test`, migrations + pytest) |
| `release_prod` | n/a | aucun déploiement dans ce lot (la PROD se livre à part, par devAI) |
| `backlog` | n/a | état tenu par la file (je ne touche pas etat.json/ROADMAP/BACKLOG/prompts) |
| `compte_rendu` | fait | ce fichier |
