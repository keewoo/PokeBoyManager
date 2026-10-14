# Emotes en partie — se parler sans chat libre

> Lot `j-echanges-emotes` (jalon J4), décision **DJ10**. Référence du catalogue fermé, du débit, de
> la coupure et de ce qui n'est **pas** conservé. Le code vit dans
> `apps/api/src/pbm_api/games/emotes.py` (pur : catalogue, débit, défauts),
> `apps/api/src/pbm_api/games/emotes_service.py` (réglage en base, limiteur en mémoire, diffusion),
> `apps/api/src/pbm_api/routers/jeu_emotes.py` (le réglage et le catalogue de référence),
> `apps/web/src/lib/game/emotes.ts` et `apps/web/src/components/game/emote-bar.tsx`.
> Le transport est celui de `docs/jeu/TEMPS-REEL.md`.

## La décision, et pourquoi elle tient

**DJ10 (JF, 14/10/2026)** : *« Emotes prédéfinies seulement ("bien joué", "oups", "ton tour"),
désactivables, jamais de texte libre. »*

Un jeu à deux sans aucun signe de vie est froid. Un **chat libre** entre un adulte et un enfant de
onze ans demande une modération que ce projet n'aura pas — et une modération qu'on n'assure pas est
pire que pas de chat du tout. Une liste fermée de phrases bienveillantes donne la chaleur sans la
charge.

⚠️ **Le risque, nommé dans le plan du lot : « ajouter juste un petit chat » plus tard.** Ce serait un
autre produit, avec une obligation de modération. Trois gardes mécanisent ce refus, et chacune dit
quoi faire quand elle rougit :

| Garde | Où | Ce qu'elle empêche |
|---|---|---|
| inventaire figé des champs de saisie du plateau | `apps/api/tests/test_jeu_emotes_parite.py` | un `input`/`textarea` qui apparaît sans que personne le remarque |
| aucun champ de saisie dans le DOM rendu, palette ouverte | `apps/web/e2e/emotes.spec.ts` | la même chose, mesurée dans un vrai navigateur |
| le canal n'accepte qu'un **code** du catalogue | `test_aucun_texte_ne_traverse` | un client bricolé qui enverrait une phrase |

## Le catalogue — dix phrases, et la règle qui les choisit

> **Une emote parle de son auteur, ou félicite l'autre. Jamais l'inverse.**

C'est la réponse au point 1 de la mission (« s'assurer qu'aucune ne peut servir à narguer ») :
« Oups… » dit *je me suis trompé*, pas *tu t'es trompé*, et il n'existe aucune emote qui commente le
coup de l'adversaire autrement que pour le saluer. Une emote ironique n'est pas une question de
goût : c'est une porte ouverte au harcèlement sans texte libre.

| code | phrase | | code | phrase |
|---|---|---|---|---|
| `bonjour` | Bonjour ! | | `merci` | Merci ! |
| `bonne_partie` | Bonne partie ! | | `oups` | Oups… |
| `bonne_chance` | Bonne chance ! | | `je_reflechis` | Je réfléchis… |
| `bien_joue` | Bien joué ! | | `un_instant` | Un instant, je reviens |
| `belle_carte` | Belle carte ! | | `ton_tour` | À toi de jouer |

La liste est **figée par un test** des deux côtés (`test_catalogue_ferme` côté serveur, un `toEqual`
côté écran) et tenue en **parité** par `test_jeu_emotes_parite.py`, qui lit `emotes.ts`. En ajouter
une n'est pas interdit : il faut passer par là, donc relire la règle ci-dessus. **JF peut en retirer
une d'un mot** — une ligne du tuple `CATALOGUE`, et le test qui le dit.

Le doublon serveur/écran est assumé : ouvrir la palette n'attend aucun réseau. Il ne peut pas
dériver sans faire rougir la CI, dans les deux sens (un code connu d'un seul côté donnerait soit une
emote refusée, soit une emote reçue que l'écran n'affiche pas).

## Le chemin d'une emote — et ce qu'il ne touche pas

```
palette → CanalPartie.envoyerEmote(code)   { "type": "emote", "code": "bien_joue" }
        → WS /games/{id}/ws  →  temps_reel._traiter_message_client
        → emotes_service.diffuser_emote  (catalogue → réglage de l'émetteur → débit → réglages des
                                          destinataires)
        → Hub.publier_emote  →  files des abonnés  →  { "type": "emote", "code", "de" }
```

`de` vaut `"moi"` pour l'émetteur (confirmation de son geste) et `"adversaire"` pour les autres :
l'écran n'a aucun identifiant de compte à manipuler, et ne peut donc pas se tromper de côté.

**Ce que ça ne touche pas**, et c'est le cœur du lot :

- **le journal numéroté** — une emote n'est **pas un coup**. Elle ne porte aucun numéro de séquence,
  n'entre pas dans le journal, ne change pas l'état, n'apparaît pas dans un replay. Un test le
  prouve en vérifiant que `games.current_numero` n'a pas bougé après une emote
  (`test_emote_nentre_pas_dans_le_journal`) ;
- **le moteur** (`pbm_game`) — il n'en entend jamais parler, et un test interdit même le mot
  « emote » dans le paquet. Aucune règle `R-x.y` du corpus (`docs/jeu/REGLES.md`) ne s'applique aux
  emotes : elles sont **à côté** des règles du jeu, pas dedans ;
- **la base** — rien d'une emote n'y est écrit. Le seul octet persisté est le **réglage** du joueur.

**Corollaire : une emote n'est pas rattrapable.** C'est une conséquence assumée, pas un trou. Les
coups ont le journal pour filet (un message perdu se rattrape par une resynchronisation, qui détecte
le trou par le numéro) ; une emote, non. Une file d'abonné saturée la perd — et l'écrit dans le
journal technique, jamais en silence. L'alternative serait d'afficher « Bien joué ! » dix secondes
trop tard, sur un coup qui n'est plus le bon.

### Pas de route HTTP, et pas de repli dégradé

Il n'existe **aucune** route HTTP pour envoyer une emote, et ce n'est pas un oubli : pas de route
veut dire pas de file d'attente, donc rien à stocker. `test_aucune_route_http_nenvoie_une_emote`
le garde sur le schéma OpenAPI réel.

Conséquence visible : en **connexion dégradée** (le WebSocket est impossible, le client interroge
`GET /games/{id}/sync`), les emotes ne circulent pas. La palette est alors **désactivée et le
dit** (« Les emotes demandent la connexion directe ») plutôt que de faire semblant.

## Le débit

| Règle | Valeur | Pourquoi |
|---|---|---|
| intervalle minimal entre deux emotes | **1 s** | la fenêtre seule laisserait passer cinq emotes en un dixième de seconde : un clignotement, pas un message |
| quota par fenêtre glissante | **5 par 20 s** | un rythme de conversation ; au-delà c'est du spam |

La règle est **pure** (`debit_autorise(envois, maintenant)`) : elle reçoit une liste d'instants et
rend `(autorisé, attente)`. Elle se teste donc en décrivant des instants, sans faire dormir la suite
une seule seconde. Le refus **dit le délai** (« Doucement — attends 2 s avant la prochaine emote. »)
arrondi à la seconde supérieure : sur un jeu d'enfant, un refus sans raison se lit comme une panne.

Un refus **n'est pas compté** comme un envoi : cliquer une fois de trop ne repousse pas sa propre
autorisation. Les deux limites sont publiées par `GET /jeu/emotes/catalogue`, pour que l'écran
puisse griser la palette **avant** le refus.

⚠️ **Portée : un process.** Le compteur (`LimiteurEmotes`) vit en mémoire, exactement comme le
`Hub` dont il partage la portée — et c'est cohérent : les emotes d'un joueur passent toutes par le
process qui tient *sa* WebSocket. Une reconnexion sur un autre process repartirait sur un budget
neuf : borne connue, assumée pour un jeu privé entre comptes invités (D11), à revoir le jour où
l'API tournera en plusieurs réplicas. Le compteur d'une partie est **effacé** quand son dernier
abonné s'en va (`LIMITEUR.oublier`), ce qui tient la promesse « rien au-delà de la partie » et
empêche le limiteur de grossir au fil des parties servies.

## Couper les emotes

`GET|PATCH /jeu/emotes/reglages` → `{ "recevoir_emotes": true }` (défaut DJ10).

**Un seul interrupteur pour les deux sens** : coupé, le joueur n'en reçoit plus *et* n'en envoie
plus. C'est un choix, et il se défend — un demi-réglage (« je ne te lis pas mais je te parle ») est
précisément la position qui sert à narguer, et un interrupteur unique se comprend d'un coup d'œil.
L'écran masque alors la palette entière.

Les deux mots du critère d'acceptation, et où chacun est tenu :

- **immédiat** — la diffusion **relit le réglage à chaque emote** (`comptes_ayant_coupe`), jamais
  une seule fois à l'abonnement : basculer l'interrupteur agit sur l'emote suivante, sans rouvrir la
  partie ni rafraîchir la page. Côté écran, le repli est optimiste (la palette disparaît au clic) et
  revient en arrière **en le disant** si le serveur refuse ;
- **mémorisé** — la ligne `jeu_emote_reglages` persiste côté **compte**, pas dans le navigateur :
  le choix vaut pour la partie suivante et sur un autre appareil. La ligne n'est créée qu'à la
  première modification (même convention que `jeu_rendu_reglages`) : son absence vaut le défaut.

Le serveur fait autorité : l'écran masque la palette, mais c'est le **refus serveur**
(`emotes_coupees`) qui compte — un client bricolé ne contourne pas un réglage.

**Ce qu'on ne dit pas à l'émetteur** : que l'adversaire l'a coupé. L'emote part, elle n'est
simplement délivrée à personne, et l'émetteur reçoit son écho comme d'habitude. Annoncer
« l'adversaire t'a coupé » transformerait un réglage de confort en information sociale, donc en
reproche.

## La palette, à l'écran

`apps/web/src/components/game/emote-bar.tsx`. Un bouton `💬` qui ouvre dix lignes, et un
interrupteur `couper` / `emotes coupées` toujours visible (couper doit être à un clic, rétablir
aussi). Une emote reçue s'affiche en **bulle, 4 s**, puis disparaît — il n'y a ni historique, ni
compteur : la même promesse que côté serveur.

⚠️ **Flanc droit, à mi-hauteur, et `fixed` — c'est une contrainte, pas un goût.** La page
`/jeu/parties/{id}` ne tolère **aucun** défilement (e2e `plateau-responsive`), et ce dépôt a déjà
payé un panneau posé en flux normal. Les autres emplacements sont pris, et deux portent des boutons
que l'e2e clique vraiment :

| Emplacement | Qui l'occupe |
|---|---|
| haut gauche | le tiroir d'aide (`aide-panel.tsx`, borné à 15rem) |
| haut centre | le statut de connexion (`game-board.tsx`) |
| haut droite | `anim-accelere` / `anim-sauter` (`animation-layer.tsx`) |
| bas, centré | le journal de partie (`journal-panel.tsx`) |
| bas gauche | l'écran de fin replié (`fin-partie.tsx`) |
| **flanc droit, mi-hauteur** | **la palette d'emotes** |

Un code inconnu de cet écran (serveur plus récent que le navigateur) **n'affiche rien** : replier
sur une autre emote ferait dire à l'adversaire ce qu'il n'a pas dit.

## « Je ne vois pas les emotes »

Dans cet ordre — les trois premières causes sont des réglages, pas des pannes :

1. **tu les as coupées** → l'interrupteur de la palette affiche « emotes coupées » ;
   `GET /jeu/emotes/reglages` le confirme ;
2. **l'adversaire les a coupées** → tu ne le sauras pas, et c'est voulu (voir plus haut). Rien à
   diagnostiquer ;
3. **connexion dégradée** → le bouton `💬` est désactivé et porte l'explication en infobulle ; le
   statut de connexion du plateau affiche « dégradé ». Les emotes reviennent avec le direct ;
4. **refus de débit** → un message rouge apparaît quelques secondes avec le délai à attendre ;
5. **rien de tout ça** → l'emote a pu être perdue sur une file d'abonné saturée. Elle est alors
   dans le journal technique du serveur (`file de diffusion saturée … emote … perdue`). Il n'y a
   **rien à rejouer** : une emote n'est pas journalisée.

## Tests

| Fichier | Ce qu'il tient |
|---|---|
| `apps/api/tests/test_jeu_emotes.py` | débit pur, catalogue figé, limiteur (par joueur/partie, oubli), réglage en base, diffusion (côtés, refus, coupure immédiate), hub, et l'emote absente du journal |
| `apps/api/tests/test_jeu_emotes_routes.py` | catalogue et réglage par HTTP, CSRF, D11, **accès croisé**, et l'absence de route d'envoi |
| `apps/api/tests/test_jeu_emotes_parite.py` | parité serveur ↔ écran, inventaire figé des champs de saisie du plateau, moteur sans emotes, module de règles pur |
| `apps/web/src/lib/game/emotes.test.ts` | catalogue fermé, traduction sans deviner |
| `apps/web/src/__tests__/game-realtime.test.ts` | le canal porte l'emote **hors** du mécanisme des coups (pas de numéro, pas de `onCoup`) |
| `apps/web/src/__tests__/emote-bar.test.tsx` | aucun champ de saisie, envoi, bulle, coupure immédiate + mémorisée, refus affiché, dégradé |
| `apps/web/e2e/emotes.spec.ts` | dans un vrai navigateur : palette ouverte sans champ de saisie, sans défilement, code envoyé sur le canal, bulle reçue, coupure qui survit à un F5 |
