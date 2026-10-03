# Coach IA — un conseil sur demande, et un bilan de fin de partie

> Lot `j-coach-ia` (jalon J4, décision **DJ7**). Deuxième visage de l'IA du joueur, après
> l'adversaire de [`ADVERSAIRE-IA.md`](ADVERSAIRE-IA.md) : au lieu de jouer **contre** l'enfant, elle
> l'**aide**. Deux usages, tous deux sur **sa** clé (coffre `pbm_api.ai`) : un conseil pendant son
> tour, et un bilan une fois la partie finie.

## Ce que ça fait

- **Conseil sur demande** (`POST /games/{id}/conseil`). L'IA reçoit **sa** vue projetée
  (`pbm_game.state.vue`) et la liste de **ses** coups légaux numérotés ; elle choisit **un index** et
  explique en une phrase. Le serveur **n'applique rien** : c'est une suggestion, le geste reste celui
  du joueur (mission « aucun coup envoyé sans le geste du joueur »).
- **Bilan de fin de partie** (`GET /games/{id}/bilan`). À partir du **journal** (`game_events`, les
  coups réellement joués — pas l'état complet), l'IA dégage deux ou trois moments décisifs. Chaque
  moment cité est **vérifié** contre le journal : un numéro inventé est écarté (anti-hallucination).

## Les règles tenues (chacune un test)

- **Jamais un coup inventé (D9).** Le conseil choisit un **index** dans la liste légale du moteur →
  légal par construction. Un index hors bornes n'est pas approximé : le coach **dit** qu'il n'a pas
  trouvé (`coup=null` + `raison`). Pas de repli sur le bot (contrairement à l'adversaire) : un conseil
  absent se **dit**, il ne se remplace pas.
- **Réservé à l'entraînement.** Le conseil est refusé (409) dans une partie entre deux humains
  (`game.entrainement` faux) : un conseil d'IA fausserait un vrai match (critère du lot).
- **Le bilan ne cite que des coups réellement joués.** `resumer_partie` filtre les moments sur
  l'ensemble des numéros **réels** du journal (coups joués, hors coups système).
- **Désactivable et borné.** `users.coach_actif` (réglable via `PATCH /me/ai-settings`) éteint le coach
  entièrement (conseil **et** bilan → 409). Le nombre de conseils par partie est plafonné par
  `settings.coach_max_conseils` (défaut 3, réglable par l'environnement) et compté sur la partie
  (`games.conseils_utilises`) — survit aux coups et à un F5.
- **La clé ne sort jamais, l'accès est borné au participant.** `_game_pour_participant` → 404 pour un
  objet d'autrui (pas de fuite). La clé déchiffrée ne sert qu'à construire le fournisseur, refermé
  ensuite ; jamais journalisée.

## Où ça vit

| Rôle | Fichier |
|---|---|
| Moteur **pur** du coach (vue + coups → conseil ; journal → bilan) | `apps/api/src/pbm_api/games/coach_ia.py` |
| Service (garde-fous, base, clé, journal) | `apps/api/src/pbm_api/games/coach.py` |
| Routes HTTP | `apps/api/src/pbm_api/routers/games.py` (`get_conseil`, `get_bilan`) |
| Schémas de sortie | `apps/api/src/pbm_api/games/schemas.py` (`ConseilOut`, `CoupConseille`, `BilanOut`, `MomentBilanOut`) |
| Réglage par joueur | `users.coach_actif` + `/me/ai-settings` |
| Budget par partie | `games.conseils_utilises` |
| Migration | `apps/api/migrations/versions/b2c3d4e5f6a7_coach_ia.py` |
| Tests | `apps/api/tests/test_coach_ia.py` |

Le moteur du coach réutilise, sans les réécrire, les outils de l'adversaire IA (`etiqueter_coups`, le
nettoyage d'explication, la mise en phrase d'une raison d'échec) : conseil et adversaire parlent la
même langue au joueur.

## Codes de refus (route)

| Situation | Code |
|---|---|
| L'utilisateur ne participe pas à la partie | 404 |
| Aucune clé IA enregistrée | 422 |
| Coach désactivé / conseil hors entraînement / plafond atteint / partie close (conseil) / partie non terminée (bilan) | 409 |
| L'IA n'a rendu aucun bilan exploitable | 502 |
| Pas son tour, ou l'IA n'a pas trouvé de conseil | 200, `coup=null` + `raison` |

## Pas (encore) fait

- **Front** : comme `j-adversaire-ia`, l'écran reste à câbler dans un lot front (bouton « Un
  conseil ? », rendu du coup suggéré sans l'appliquer, panneau de bilan, réglage « coach activé »,
  régénération du client TypeScript `pnpm gen:api` — le schéma a gagné `/games/{id}/conseil`,
  `/games/{id}/bilan` et `coach_actif`).
- **Coût en euros** : non calculé (aucune table de tarification par modèle dans ce dépôt, limite déjà
  documentée) ; l'usage IA est compté (`ai_usage_monthly`), le prix reste à faire.
- **Bilan non persisté** : généré à la demande à chaque appel. Un lot ultérieur pourrait le mettre en
  cache sur la partie pour ne pas re-dépenser la clé à chaque consultation.
