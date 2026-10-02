# Compte rendu — `j-salon-partie`

**Salon de jeu : jouer, inviter, reprendre, s'entraîner.** Écran d'où part tout le jeu (jalon J1),
construit sur chimera, piloté depuis devAI.

## Résumé

Livré l'écran `/jeu/salon` qui rassemble, dans cet ordre de priorité : la **reprise** d'une partie
en cours (en tête, l'action la plus urgente), l'entrée en **file d'attente** avec choix du deck et
affichage de sa **jouabilité avant d'entrer**, l'état réel de la file (attente avec rang/temps,
annulation, interrogation périodique ; « adversaire trouvé » à rejoindre), la **présence** des
joueurs et, quand personne n'est là, un repli **concret** (générer un lien d'invitation, ou
s'entraîner contre le bot — annoncé « bientôt », lot `j-mode-solo` non livré, jamais approximé D9),
les **invitations reçues** acceptables/refusables, et le rappel du **dernier résultat**.

L'entrée « Jouer » (navigation + salon) n'est montrée qu'aux comptes ayant le droit d'accès au jeu
(`game_access`, D11) ; un compte sans ce droit reçoit une **page inexistante** (`notFound()`) et ne
voit aucune porte vers le jeu — l'API, elle, répond déjà 404 partout (`require_game_access`).

## Livrables

- **Écran salon** : `apps/web/src/app/jeu/salon/page.tsx` + `salon-view.tsx` (reprise, file, présence,
  invitations, dernier résultat ; sections empilées en une colonne, lisibles sur téléphone).
- **Entrée en file avec deck + jouabilité** : sélecteur de deck, verdict de jouabilité affiché avant
  l'entrée, entrée bloquée tant que le deck n'est pas jouable (cartes en cause nommées, D9).
- **Reprise visible** : les parties `en_cours` en tête, « Reprendre » en un clic vers
  `/jeu/parties/{id}` (le plateau est le lot aval `j-plateau-layout`, que ce lot débloque).
- **Gating `game_access`** : lien « Jouer » conditionné dans `app-shell.tsx` ; `game_access` exposé par
  `GET /me` (`ProfileResponse`) ; salon rendu inexistant sans le droit.
- **Endpoint serveur** `GET /matchmaking/decks/{deck_id}/jouabilite` : dit si un deck est jouable
  avant l'entrée en file (même contrôle que l'entrée, `entry.verifier_deck`), 404 si deck d'autrui.
- **Wrappers API front** : `lib/api/games.ts`, `matchmaking.ts`, `invitations.ts`.

## Preuves

- **Tests web** : suite complète verte sur chimera — **182 tests, 41 fichiers**, lint 0 erreur,
  `tsc --noEmit` vert. Nouveaux : `salon-view.test.tsx` (8), `app-shell-jeu.test.tsx` (3),
  `app-shell-decks.test.tsx` mis à jour (4). Couvrent : page inexistante sans accès, reprise en
  tête + lien, jouabilité affichée avant l'entrée (jouable → entrée permise ; refus nommé → entrée
  bloquée), repli « personne en ligne » (inviter / s'entraîner bientôt), partie trouvée à rejoindre,
  invitations reçues, dernier résultat.
- **Tests API** : `test_profile_game_access.py` (2) et `test_matchmaking_jouabilite.py` (4 : jouable,
  refus nommé, deck d'autrui → 404, sans accès → 404). `ruff check .` vert.
- **CI GitHub Actions** : fait foi pour la suite API (Postgres 16 migré à head + Redis + SeaweedFS).
  La recette locale API sur chimera n'a pas pu valider ces tests : la base de test partagée de
  chimera (`pbm_v2_catalogue_complet_test`) est **antérieure à la migration `game_access`** (colonne
  absente) et **Redis n'y tourne pas** — infra de recette, pas un défaut du code. C'est pourquoi on
  s'en remet à la CI, qui recrée une base propre et démarre Redis.

## Écarts au plan

- **Reprise / rejoindre** pointent vers `/jeu/parties/{id}`, page que construira `j-plateau-layout`
  (lot aval, débloqué par celui-ci) : d'ici là, le lien est présent et correct mais mène à une page
  pas encore écrite. Choix assumé : le salon surface la partie et offre l'entrée ; il ne fabrique pas
  un faux plateau (D9), et l'ordre du plan place le salon avant le plateau.
- **Entraînement contre le bot** : annoncé « bientôt » (bouton désactivé), car `j-mode-solo` n'est pas
  livré. Jamais simulé.
- **Invitations reçues** : n'affichent que l'existence (le mode), pas le pseudo de l'inviteur —
  `InvitationOut` ne porte que des identifiants (pas de pseudo), par conception anti-fuite du lot
  `j-invitations`.

## Reste à faire (lots aval)

- `j-plateau-layout` : la table de jeu (reprise/rejoindre aboutissent là).
- `j-mode-solo` : l'entraînement contre le bot (remplacera le bouton « bientôt »).

## Recette / livraison

Aucun déploiement (la PROD se livre à part, par devAI). Pas de migration ajoutée. Pas de secret.
