# Compte rendu — `j-stats-joueur`

**Lot** Mes parties : historique, statistiques et ce que ça dit de mes decks · jalon **J4** ·
piste Compte & progression · couloir J-UI (chimera) · **P1**, taille M.

**Session** autonome (`claude -p`), pilotée depuis **devAI**, travail sur **chimera**
(WSL Ubuntu-24.04, worktree `~/dev/wt-j-stats-joueur`, branche `roadmap/j-stats-joueur` depuis
`github/main` à `5e4495f`). Garde-fou d'ordre : `suivi.py verifier j-stats-joueur` → **code 0**
(« ordre tenu »).

## Résumé

Deux routes en lecture — `GET /jeu/mes-parties` (historique filtrable et paginé) et
`GET /jeu/mes-statistiques` (agrégats par deck et par adversaire) — alimentées par un module
**pur** qui ne connaît ni base ni HTTP, l'écran `/jeu/parties`, et un bloc « Ce deck en partie » sur
la fiche de deck du gestionnaire. Rien n'est stocké : tout est recalculé à chaque appel depuis
`game_result_players`, comme le classement privé — il n'existe donc aucun agrégat à réparer.

La réponse au risque du lot est **structurelle**, pas cosmétique : `taux()` est la seule porte vers
un pourcentage, et elle rend `significatif` + `parties_manquantes` dans le même objet. Un écran ne
peut pas obtenir un taux sans obtenir de quoi dire qu'il ne vaut rien encore ; tout futur appelant
(badges, profil de joueur) héritera de la garde sans y penser.

## Livrables

| Livrable attendu | Où |
|---|---|
| page « Mes parties » | `apps/web/src/app/jeu/parties/{page,mes-parties-view}.tsx` |
| agrégats par deck et adversaire | `apps/api/src/pbm_api/jeu/stats_joueur.py` (pur) + `stats_joueur_service.py` (lecture) |
| routes HTTP | `apps/api/src/pbm_api/routers/stats_joueur.py`, montées dans `main.py` |
| liaison avec la fiche de deck | `apps/web/src/app/jeu/decks/[id]/deck-parties-panel.tsx`, monté dans `deck-builder-view.tsx` |
| client API front | `apps/web/src/lib/api/stats-joueur.ts` |
| doc technique | `docs/jeu/STATS-JOUEUR.md` + entrée dans la carte des fiches de `CLAUDE.md` |
| tests | `apps/api/tests/test_jeu_stats_joueur.py` (26) · `apps/web/src/app/jeu/parties/mes-parties-view.test.tsx` (12) |

## Les trois critères d'acceptation, mesurés

**1. « Les agrégats correspondent aux parties réellement jouées (vérifié sur un jeu de données de
test). »** ✅ `test_les_agregats_correspondent_aux_parties_jouees` écrit six parties comptées sur
deux decks et un adversaire, plus une d'entraînement, et confronte **chaque** nombre rendu par la
route à ce que le test a posé : totaux (6 parties, 3 V / 2 D / 1 N, 50 %), ligne Brasier (75 %),
ligne Marée (0 %, 1 égalité), croisement deck × adversaire, et `parties_entrainement = 1`. Doublé par
`test_les_colonnes_du_taux_se_recomptent`, qui vérifie que **tout** taux rendu se recompte depuis
ses propres colonnes — un chiffre qu'on ne peut pas refaire à la main n'est pas contestable.

**2. « Un taux calculé sur moins de cinq parties est signalé comme non significatif. »** ✅ Aux
**deux bords** du seuil : `test_sous_le_seuil_un_taux_est_marque_non_significatif` (paramétré 0→4,
`significatif=False`, `parties_manquantes` exact) et
`test_a_cinq_parties_le_taux_devient_significatif` (5 parties → `True`) — tester les deux bords est
ce qui attrape une inégalité posée au mauvais sens. De bout en bout par la route :
`test_la_route_marque_les_taux_non_significatifs` (trois victoires sur trois sortent à 100 % **et**
marquées, sur les totaux comme sur la ligne du deck). Côté écran : le test
« marque les taux calculés sur moins de cinq parties et dit ce qui manque » vérifie la phrase
affichée (« Sur 3 parties seulement — encore 2… ») et que **aucun** bloc de taux n'est présenté
comme significatif.

**3. « La page se charge en moins d'une seconde avec cent parties. »** ✅ **0,183 s** mesurées sur
chimera (15/10/2026) pour les **deux** appels que la page fait réellement — l'historique de 100
lignes *et* les agrégats, qui ne sont pas paginés et portent donc bien sur les cent parties. Le test
`test_cent_parties_tiennent_la_seconde` garde le budget d'une seconde ; chronométrer la seule liste
aurait laissé passer un agrégat quadratique. Trois requêtes SQL au total, aucune par ligne.

## Preuves

| Vérification | Résultat |
|---|---|
| `uv run ruff check .` (apps/api, chimera) | **All checks passed** |
| `uv run pytest tests/test_jeu_stats_joueur.py -q` | **26 passed** en 7,7 s |
| `uv run pytest -q` (suite API complète, chimera) | **1492 passed, 2 failed** — les 2 échecs sont `test_catalogue_seed.py`, **reproduits sur `main`** (`789f879`) au même endroit : `pg_dump: command not found` dans la WSL de chimera. Outil absent de la machine, sans rapport avec ce lot ; la CI l'a. |
| `vitest run` (suite front complète, devAI) | **95 fichiers, 856 tests passed** |
| `vitest run …/mes-parties-view.test.tsx` | **12 passed** |
| `tsc --noEmit` (devAI) | aucun diagnostic |
| `eslint` sur les fichiers du lot (devAI) | aucune sortie (vert) |
| CI GitHub Actions — branche | SHA `32ffad9` → **verte (`success` sur l'événement `push` — le passage `pull_request` reste en `action_required`, approbation exigée par le dépôt, ce n'est pas un échec)** |
| CI GitHub Actions — `main` après fusion | SHA `8a4a440` → **verte (`success`)** |

**Isolation (exigence du dépôt).** `test_je_ne_vois_pas_les_parties_d_un_autre_compte` : l'autre
compte a six victoires et un pseudo, le compte de la session une seule défaite — la liste comme les
agrégats ne rendent que la défaite. Le filtre `user_id` est posé dans la **seule** fonction que les
deux chemins partagent (`_appliquer`), et aucun paramètre de route ne désigne un autre compte : il
n'existe pas de route « les parties de X » à attaquer. D11 vérifié aux deux routes
(`test_un_compte_sans_acces_au_jeu_recoit_404`), et côté écran (`notFound()` sans `game_access`).

**Aucun secret** n'apparaît dans le code, les tests ou les sorties. Aucun déploiement n'a été fait
(la PROD se livre à part, par devAI).

## Écarts au plan — nommés, pas tus

Deux fonctionnalités annoncées en section 2 du prompt **ne sont pas livrées**, et l'absence est un
choix motivé, écrit dans `docs/jeu/STATS-JOUEUR.md` § « Ce que ce lot ne sait pas encore dire » :

1. **« Cartes les plus jouées » et « attaques les plus décisives »** demandent le détail du journal
   (`game_events`), que la purge supprime au bout de trente jours. Un palmarès calculé sur les
   journaux survivants **rétrécirait tout seul** — un joueur verrait sa carte préférée quitter son
   palmarès sans explication, soit exactement la statistique trompeuse que ce lot doit empêcher.
   Les rendre justes demande de **cumuler ces compteurs à la clôture** dans `game_result_players`
   (une colonne qui survit à la purge, comme le reste de la trace) : c'est une colonne à ajouter du
   côté de `j-fin-effets-compte`, pas un calcul à deviner ici (D9).
2. **« Ce deck gagne surtout contre les decks Eau »** : le type du deck **adverse** n'est pas
   conservé — `game_result_players` porte le deck du joueur, pas celui d'en face — et le déduire de
   la collection de l'adversaire serait deviner. Le croisement livré nomme donc l'**adversaire**
   (« ce deck gagne surtout contre aymeric »), pas une couleur qu'on n'a pas.

Ce qui est livré à la place des deux palmarès : les **six compteurs** du récapitulatif, cumulés et
moyennés par partie (dégâts, K.O., récompenses, cartes jouées, énergies, coups) — ceux-là sont déjà
écrits par partie et survivent à la purge, donc ils ne mentent pas.

**Autre écart, mineur :** le lot n'applique **aucune règle de jeu** (il compte des résultats déjà
écrits), donc aucun test ne cite de `R-x.y` — l'exigence de la section 7 ne s'applique pas ici ; les
règles de fin (R-14) sont couvertes par le moteur et `test_games_fin_compte`.

## Décisions prises en séance (pas d'arbitrage disponible, session autonome)

- **Seuil de significativité = 5 parties**, valeur du critère d'acceptation, rendue par l'API
  (`seuil_significativite`) pour que l'écran écrive la règle sans la recoder : la changer un jour ne
  demandera pas de retoucher le front.
- **`player_stats` n'est pas lu** : les totaux sont recalculés depuis les mêmes lignes que la liste,
  pour qu'un cache en retard ne puisse pas contredire l'historique affiché juste en dessous.
- **L'entraînement est visible par défaut** dans la liste (et exclu des taux) : le masquer d'office
  ferait croire à un historique amputé.
- **Pas de route d'écriture, donc pas de « remise à zéro »** : rien n'étant stocké, il n'y a rien à
  remettre à zéro — effacer son historique, c'est supprimer son compte.

## Reste à faire

- **Colonnes de palmarès à la clôture** (cartes jouées par carte, attaques décisives) : à porter par
  `j-fin-effets-compte` ; l'écran les affichera sans changer de route. À soumettre à JF, c'est une
  migration.
- **Entrée de menu vers `/jeu/parties`** : la page existe et est atteignable depuis la fiche de deck
  (« Voir toutes mes parties ») ; la place dans la navigation du jeu appartient à `j-profil-jeu`,
  qui pose le profil de joueur et son menu.
- **Badges et classement** liront ces mêmes agrégats : `taux()` leur donne la garde de
  significativité gratuitement — ne pas la contourner.
- **Capture d'écran de conformité à la maquette** : non produite (session autonome sans navigateur
  sur chimera ; l'e2e Playwright tourne sur devAI). L'écran suit la structure et les jetons des
  écrans voisins du jeu (`/jeu/notifications`, `/jeu/confort`) : mêmes cartes à bordure
  `rgba(157,0,255,0.3)`, titre `font-heading … text-gold`, et le violet `#9D00FF` n'est jamais
  utilisé en texte (`#C77DFF` pour les mises en garde, charte `apps/web/CLAUDE.md`). Écart assumé,
  à confirmer à l'œil par JF.
