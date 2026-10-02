# Lancement d'une partie — `j-lancement-partie`

> Entre le **salon d'attente à deux** (`j-invitations`) et la **partie en cours**
> (`j-partie-service`), l'étape que JF a nommée : *« qui commence »*. Le serveur fait autorité ;
> l'écran ne fait que montrer un résultat déjà tombé.

Code : `apps/api/src/pbm_api/games/lancement.py` (service), `apps/api/src/pbm_api/routers/lancement.py`
(routes `/lancements`), `apps/api/src/pbm_api/models/game_launch.py` (table `game_launches`). Le moteur
`pbm_game` reste **pur** : seul son `Rng` (pur) est sollicité pour le pile ou face.

## La machine à états (persistée)

Un lancement **par invitation** (`invitation_id` unique). Chaque étape est une écriture : un
rechargement (`GET /lancements/{invitation_id}`) reprend à la bonne étape.

| Statut | Ce qui s'y passe | Transition |
|---|---|---|
| `preparation` | chaque camp choisit son deck (ou garde l'annoncé) et se déclare **prêt** ; le deck est recontrôlé (propriété, scripts D9, possession) | `POST …/preparer` |
| `tirage` | les **deux** prêts → la graine est tirée, son **engagement** publié, le **pile ou face R-4.7** fait ; le gagnant doit choisir | automatique quand deux prêts |
| `lance` | le choix tranché (ou le défaut), les decks recontrôlés, la partie créée (`creer_partie`) : `game_id` la désigne | `POST …/choisir` ou défaut après délai |
| `abandonne` | un joueur quitte avant le lancement (déconnexion, renoncement) : figé, aucune partie | `POST …/abandonner` |

## Qui commence — R-4.7 et le livret (R-1.1)

- **R-4.7** fixe un **pile ou face** pour déterminer qui commence.
- Le **livret officiel** (source de vérité, R-1.1) laisse au **gagnant du tirage** le choix de
  commencer ou non.

On implémente les deux : le pile ou face désigne le **gagnant**, le gagnant **choisit** (`commencer`
oui/non), et **à défaut de choix dans le délai** (`DELAI_CHOIX`, 30 s) le **gagnant commence** — la
lecture littérale de R-4.7. Le premier joueur est assis au **siège 0** : le moteur fait du siège 0 le
joueur actif du tour 1, et « le tour 1 est celui qui commence » (invariant de `pbm_game.state.Tour`).

> **Écart signalé à JF.** R-4.7, tel qu'écrit dans `docs/jeu/REGLES.md`, dit « au hasard (pile ou
> face) qui commence » sans mentionner le choix laissé au gagnant. Le choix du gagnant vient du
> livret (R-1.1) et était explicitement demandé par le lot. Le **défaut** retombe exactement sur
> R-4.7 (le gagnant commence). Si JF préfère le pile ou face sec (sans choix), il suffit de forcer
> `commencer=True` : la mécanique du tirage, elle, ne change pas.

## Le tirage est vérifiable après coup (commit-reveal)

Mécanique portée par `pbm_game.rng` (voir `docs/jeu/ALEATOIRE.md`) :

1. **avant** le tirage, on publie l'**engagement** = empreinte de la graine (`engagement`) ;
2. le pile ou face est le tirage `0` du flux `FLUX_QUI_COMMENCE` sous cette graine, journalisé
   (`tirage`), **public** (son résultat et son gagnant le sont aussitôt) ;
3. la **graine** reste **secrète** tant que la partie tourne (la révéler rendrait la pioche
   prévisible) ; elle n'est révélée qu'une fois la **partie terminée**.

Les deux joueurs revérifient alors hors du serveur : `verifier_engagement(graine, engagement)` puis
`rejouer_tirage(graine, tirage)` — le résultat doit retomber à l'identique. **Convention de face** :
`face` = l'émetteur de l'invitation gagne, `pile` = l'invité.

## Deck devenu injouable entre la file et le lancement

À chaque préparation **et** au lancement final, les decks sont recontrôlés par `verifier_lancable` :

- **propriété** — le deck est bien le vôtre (sinon 404, pas de fuite) ;
- **scripts D9** — chaque carte se compile pour le moteur (sinon 422, cartes nommées) ;
- **possession** — chaque carte non-Énergie est possédée en quantité suffisante (**carte vendue** →
  422, cartes nommées). Même règle de possession que `pbm_api.decks.legality` (code `not_owned`).

Un deck devenu injouable **arrête le lancement** en nommant les cartes, **sans partie fantôme** (le
lancement reste en `tirage`, aucun `game_id`).

La **légalité de format / taille** (60 cartes, max 4) n'est **pas** imposée ici : au jalon J1 (« laid
mais juste »), c'est `j-initialisation` qui fera du deck complet l'unité de jeu — report explicite,
déjà documenté dans `pbm_api.games.entry`, pas un abandon silencieux.

## Vient après / débloque

- Après : `j-invitations` (salon d'attente), `j-aleatoire-determinisme` (graine, pile ou face).
- Débloque : `j-initialisation` (mélange, main de sept, mulligans, actif et banc, six récompenses) —
  qui part de la partie créée ici, avec sa graine et son premier joueur.
