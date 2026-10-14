# L'e2e d'une partie — ce qu'il prouve, et les pièges qu'il a révélés

> Lot `j-e2e-deux-navigateurs`. Spec : `apps/web/e2e/partie-deux-navigateurs.spec.ts`.
> Seeds : `apps/api/scripts/seed_partie_e2e.py`, `apps/api/scripts/forcer_horloge_e2e.py`.

C'est la seule preuve qui vaut pour le jeu : **deux navigateurs, deux sessions, une partie menée de
la file d'attente à l'écran de fin, sans intervention** — puis les parcours dégradés, là où sont les
vraies pannes. Les cinq parcours tournent en CI à chaque modification (le job `e2e` exécute tout
`apps/web/e2e/`), et les **captures sont publiées** : l'étape d'envoi du rapport est en `always()`,
parce qu'une preuve qui n'existe qu'en cas d'échec n'est pas une preuve.

## Les cinq parcours

| Parcours | Ce qu'il prouve |
|---|---|
| **nominal** | file d'attente → appariement → mise en place (R-4) → plusieurs tours → énergies, Dresseurs, attaques → K.O. → écran de fin → **historique du compte à jour des deux côtés** |
| **F5 au milieu** | le journal rejoué redonne le même état (`numero` identique), et la partie **accepte encore des coups** après le rechargement |
| **abandon** | R-14.3 : les deux écrans l'annoncent, celui qui abandonne perd, l'historique le retient |
| **expiration d'horloge** | DJ4 : budget épuisé → `defaite_temps`, `raison_fin = temps_ecoule`, **sans que personne ne clique** |
| **déconnexion / repli en sondage** | WebSocket coupé → bandeau « connexion dégradée » → **la partie se joue entièrement** en interrogation périodique → reconnexion, bandeau retiré |

## Comment le pilote décide — le serveur fait autorité, le test ne rejoue aucune règle

À chaque coup, le test lit `GET /games/{id}/state` et prend un coup dans `actions_legales`, qui
porte déjà **tout** ce qu'il faut : `type`, l'`etiquette` exacte du bouton, ses `cibles`, et
`irreversible`. Il clique ce bouton dans l'interface, choisit une cible si le serveur en annonce,
confirme si le serveur dit le coup irréversible. L'écran est donc réellement traversé, mais rien
n'est codé en dur : si le moteur change une étiquette, le test suit.

⚠️ **La forme de `/state` piège.** La projection est **imbriquée** sous `vue`
(`actions_legales` y est posé par `vue_autoritaire`), tandis que `numero` et `horloges` sont ajoutés
à la **racine** par la route. Chercher `actions_legales` à la racine rend une liste vide — et on
croit alors que personne n'a de coup à jouer.

## Pourquoi la partie finit vite, et légitimement

`seed_partie_e2e.py` donne au joueur A un attaquant à 60 dégâts, et au joueur B **un seul** Pokémon
à 110 PV sans attaque. Deux attaques le mettent K.O. ; son banc étant vide **par construction**, il
n'a plus personne à promouvoir — deuxième voie de victoire de **R-14.1**, adossée à **R-8.9**. Une
vraie fin de partie, pas un abandon. Mesuré : **32 coups**, ~16 s.

Trois contraintes apprises en le construisant, chacune mesurée :

- **Un seul Pokémon dans le deck B, pas quatre.** Le générateur de mise en place propose de mettre
  au banc **tous** les Pokémon de base restants de la main : avec 60 bases en deck, la seule option
  offerte est « Actif + banc de 5 ». Vider un banc garni demanderait douze attaques, et c'est **A**
  qui épuiserait son deck le premier (**R-14.2**) — la partie finissait par un *deck out* de A,
  l'inverse de ce qu'on veut prouver.
- **Le mulligan ne coûte rien.** Avec un exemplaire unique il faut plusieurs mulligans, mais la
  boucle est résolue *dans* l'action système `mise_en_place_initiale`, en un seul coup journalisé,
  sans aller-retour HTTP. Les récompenses étant placées **après** la main (R-4.3), cette carte ne
  peut pas finir en récompense.
- **Un Objet qui pioche ne se rejoue pas à volonté.** Le pilote plafonne les Dresseurs (deux de
  chaque) : sans ce plafond, A rejouait l'Objet dès qu'il réapparaissait en main et brûlait son deck
  — 123 coups, et la victoire à B.

⚠️ **La mise en place se joue à deux.** Attendre que *A* n'ait plus de placement légal ne suffit
pas : B reste alors sans Actif, la partie n'est pas commencée, et les parcours qui comptent sur un
tour en cours (horloge, abandon) mesurent autre chose que ce qu'ils annoncent — l'expiration, elle,
ne se produit pas du tout. La condition porte sur **les deux** joueurs.

## L'expiration d'horloge : il n'y a pas de minuteur

Aucun cron ne surveille les horloges. Le **seul** déclencheur en production est le **battement de
cœur du WebSocket**, qui appelle `expirer_horloge` à chaque silence de 20 s
(`pbm_api.games.temps_reel.piloter_canal`). Ni `GET /state` ni `GET /sync` ne déclenchent quoi que
ce soit. Le test laisse donc les deux navigateurs ouverts et **attend** — exactement le scénario
d'un joueur qui s'en va.

`forcer_horloge_e2e.py` ne fait que rendre l'expiration *due*, sur **une** partie nommée : il pose
le budget du joueur actif à 0 et recule son compteur de 30 s. Pourquoi pas une variable
d'environnement : chaque partie **fige sa configuration d'horloges à sa création**, donc baisser
`HORLOGE_PAR_TOUR_S` ne raccourcit pas une partie déjà lancée — et le baisser pour toute l'instance
ferait expirer le parcours nominal en cours de route. Pourquoi 30 s : le budget est vérifié *en
premier* et n'expire qu'au-delà de la tolérance réseau (10 s), tout en restant sous la limite par
tour (90 s) — sans quoi la cause retenue serait `tour` et produirait un simple `fin_tour`.

## Cinq défauts que ce lot a trouvés — et pourquoi aucun test ne les voyait

Tous corrigés dans le lot, chacun avec un test qui **mord** (vérifié en cassant le correctif).

| Défaut | Effet réel | Pourquoi invisible |
|---|---|---|
| **La file d'attente ne démarrait pas la partie** (`games/matchmaking.py`) | deux joueurs appariés arrivaient sur un plateau resté au coup 0, où le seul coup légal est « Abandonner » | les trois autres chemins de création appellent `demarrer_partie` (invitation, entraînement, revanche) ; **toutes** les parties complètes de la suite sont fabriquées à la main (`creer_partie` + `demarrer_partie`) et sautent l'appariement |
| **La CSP bloquait le WebSocket** (`web/src/middleware.ts`) | le canal temps réel échouait, repliait en interrogation périodique, et le jeu tournait en **mode dégradé permanent** sans que rien n'échoue | une source `http://hôte` de `connect-src` ne couvre pas `ws://hôte` dans Chromium. Ne touche que les déploiements où l'API a sa **propre origine** (dev, CI, e2e) : en UAT/PROD l'API partage l'origine du site et `'self'` couvre déjà `wss:` |
| **Choisir une cible au clic était impossible à la souris** (`components/game/board-card.tsx`) | le survol *et* le focus ouvraient `CardZoom`, surcouche plein écran qui se referme au clic : elle apparaissait entre l'appui et le relâchement, et **aucun `click` n'atteignait la carte** | le réducteur (`lib/game/interactions.ts`) est pur, l'e2e du plateau ne mesurait que la mise en page, et au doigt un appui **court** n'ouvre pas le zoom — le défaut ne touchait que la souris |
| **Clés React dupliquées dans la barre d'actions** (`components/game/action-bar.tsx`) | plusieurs coups partagent type *et* étiquette (une Énergie par exemplaire en main) : mesuré 12 `attacher_energie` et 9 `jouer_objet` identiques. Après un coup en vol, une partie des boutons **gardait `disabled` définitivement** | React n'avertit des clés dupliquées qu'en **développement** ; l'e2e tourne sur un build de production, où l'avertissement est retiré |
| **Le canal annonçait un numéro de coup en retard** (`games/temps_reel.py`, `lib/game/realtime.ts`) | un coup de joueur enchaîne des coups **système** (pioche, phases, checkup). Le message ne portait que `numero`, le client en déduisait `numero + 1` : retard **constant de 3 coups**, coup suivant refusé en 409, et jusqu'à **20 s** d'attente avant que le battement ne rattrape | aucun test de bout en bout ne jouait deux coups de suite **depuis un navigateur** ; les tests d'API posent le numéro à la main |

Le message de diffusion porte désormais `courant`, le **prochain numéro attendu** par le serveur
(`None` → le client retombe sur `numero + 1`, un abonné d'une version antérieure n'est pas cassé).

## Ce qui reste ouvert

- **Les coups système ne sont pas diffusés un par un.** Le client les récupère par
  resynchronisation (au prochain coup diffusé, ou au battement). Son **journal** peut donc être
  momentanément incomplet, même si son numéro est juste depuis le correctif. À reprendre si le
  journal du joueur doit être exact à l'instant.
- **Conflit de numéro à la mise en place.** Les deux joueurs ont « placer » légal au **même** numéro
  (R-4) : le premier à soumettre prend le numéro, l'autre reçoit un 409 et l'écran lui montre la
  raison du serveur. Un joueur humain re-clique et ça passe — c'est ce que fait le pilote, avec un
  plafond de refus nommé. Une file d'attente côté client, ou un numéro par joueur pendant la mise en
  place, l'éviterait.
- **`games_ws.py` journalise une pile d'exception** (`WebSocketDisconnect`, code 1006) quand un
  onglet se ferme pendant un envoi. Sans conséquence fonctionnelle, mais c'est du bruit dans les
  journaux du serveur, et ça gênera la supervision (`docs/jeu/OBSERVABILITE.md`).

## Lancer les parcours

```bash
# Depuis apps/web, avec Postgres/Redis de test en service (voir docs/CODE.md).
pnpm exec playwright test partie-deux-navigateurs
```

⚠️ La base e2e doit être **à jour des migrations** (`uv run alembic upgrade head` dans `apps/api`) :
une colonne manquante fait échouer le seed, et le message parle de la colonne, pas du parcours.

**La CI fait foi** — pas une suite verte sur une machine. Le navigateur e2e ne s'installe pas sur
chimera (`libnspr4`, `sudo` requis) ; les suites front tournent sur devAI.
