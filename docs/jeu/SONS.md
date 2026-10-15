# Les sons du jeu

> Lot `j-son` (palier 15, jalon J3). Ce qu'on entend pendant une partie, d'où ça vient, et comment
> on le coupe. Le pendant sonore de `docs/jeu/ANIMATIONS.md` — et la même doctrine : **les effets
> suivent les événements, jamais l'inverse**.

## En une phrase

Il n'y a **aucun fichier audio** dans ce dépôt. Chaque son est une *recette* écrite en données
(`apps/web/src/lib/game/sons.ts`) que le navigateur fabrique au moment où on l'entend — donc rien à
créditer, rien à re-sourcer, et zéro octet expédié.

## Pourquoi pas des bruitages téléchargés

Le lot nommait le risque : *« des sons pris au hasard sur Internet, c'est un risque de droits pour
quelques kilo-octets d'effet »*. On ne l'a pas encadré par une liste de crédits à tenir à jour — on
l'a supprimé. Trois conséquences, et elles tiennent ensemble :

| | |
|---|---|
| **Droits** | une recette d'oscillateurs n'est l'œuvre de personne d'autre. Aucune licence à honorer, aucun fichier à remplacer le jour où un site d'échantillons ferme |
| **Poids** | le budget d'images d'une partie est contrôlé en CI (`docs/jeu/ASSETS.md`) ; dix-sept sons l'auraient entamé pour rien |
| **Tests** | une recette est de la donnée : volumes relatifs, file, rattrapage se vérifient en `vitest`, sans navigateur ni carte son |

⚠️ **La garde est dans le code, pas dans cette page.** `apps/web/src/__tests__/sons-origine-garde.test.ts`
refuse tout fichier audio dans `public/`, tout `decodeAudioData`, tout `new Audio(`, toute URL de
média dans la couche sonore. Si un fichier audio devient un jour légitime (une voix enregistrée, une
musique commandée), ce test se **modifie en connaissance de cause**, avec la licence écrite à côté
du fichier — il ne se supprime pas pour faire passer la CI.

## La banque — dix-sept sons

Tous dans `SONS` (`apps/web/src/lib/game/sons.ts`), et **écoutables** sur `/jeu/sons`.

| Groupe | Sons | Ce que l'oreille doit comprendre |
|---|---|---|
| Les mains | `pose`, `pioche`, `energie`, `objet`, `talent`, `evolution` | quelque chose se pose : court, mat. `pioche` est surtout du souffle — c'est le son le plus souvent entendu, une note en ferait un événement |
| Les coups | `attaque`, `impact`, `echec`, `ko`, `recompense` | `impact` est **retimbré par le type** et par les dégâts réels ; `ko` **tombe**, `recompense` **monte** |
| Le rythme | `piece`, `tour`, `minuterie` | `piece` a deux temps (le lancer, la retombée) — le hasard doit s'entendre pour être accepté (R-12.1) |
| La fin | `victoire`, `defaite`, `egalite` | `victoire` monte, `defaite` descend **sans se moquer** : pas de dissonance, pas de « buzzer » |

Chaque recette est bornée, et c'est vérifié :

- durée ≤ `DUREE_SON_MAX` (1200 ms), et ≤ `DUREE_COUP_MAX` (700 ms) pour tout son **de coup** —
  seule la fin de partie a le droit de durer, parce qu'elle ne couvre plus rien ;
- gain ≤ `GAIN_MAX` (0,4), bien en dessous de 1 : deux sons peuvent se chevaucher, et deux gains
  proches de 1 qui s'additionnent saturent ;
- montée et descente **non nulles** : une onde qui démarre à plein volume produit un claquement
  (le « clic » de l'audio numérique), le défaut qui fait qu'un son synthétisé paraît bon marché ;
- un passe-bas par recette, qui rabote les harmoniques aiguës — c'est lui qui rend une onde carrée
  supportable, plutôt que de renoncer au claquement de l'Éclair et au choc du Métal.

### La minuterie est le son le plus discret, et c'est un invariant

Le lot l'exigeait nommément (« qu'aucun son ne surprenne, la minuterie surtout »). Ce n'est pas une
préférence écrite ici : un test interdit qu'aucune autre recette descende sous son gain. Baisser un
son, ou monter la minuterie, casse la CI et nomme le fautif. La musique d'ambiance passe elle-même
**sous** la minuterie — un fond qui s'entend n'est plus un fond.

Elle sonne **une fois**, au passage de `SEUIL_MINUTERIE_MS` (10 s), et seulement quand c'est à
**moi** de décider. Un tic répété sur un enfant qui cherche son coup n'est pas de l'information,
c'est de la pression ; et prévenir quelqu'un de l'expiration d'un délai qu'il ne peut pas tenir n'a
aucun sens.

## Le son et l'image viennent du même événement

`planifierSons()` **part du plan d'animations** (`planifier()` de `lib/game/animations.ts`). Ce n'est
pas une commodité : c'est ce qui rend impossible qu'un son et son effet visuel se mettent un jour à
parler de deux événements différents. Il n'y a pas deux lectures des événements du serveur, il n'y
en a qu'une.

### Le timbre du type est sur `degats`, pas sur `attaque_declaree`

Repère d'implémentation, et c'est un test qui l'a trouvé : le socle d'animation ne typpe
`attaque_declaree` **que lorsque l'attaque a raté**. Pour un coup qui porte, c'est l'événement
`degats` qui porte le type, les dégâts réels, la faiblesse et la résistance. Un timbre posé sur
l'attaque déclarée serait donc resté muet sur **toutes** les attaques qui portent — c'est-à-dire
exactement quand ça compte — et le silence de ce défaut aurait été indistinguable d'un choix.

Conséquence : `attaque` est volontairement **neutre** (le geste), `impact` est **typé** (le coup).
`TIMBRES_TYPE` a une ligne par type de `SPECS`, et un test de parité le vérifie : un douzième type
d'énergie ajouté à l'effet visuel sans timbre casse la CI.

L'intensité vient de `intensiteDe()` — la même fonction qui dimensionne l'effet visuel. Un coup
faible est donc à la fois plus discret à l'écran et plus discret à l'oreille, sans qu'aucun seuil ne
soit recopié.

## Ce que la file garantit

`reduireSons` / `tirerSon` sont **purs** (`sons.test.ts`, 37 cas) :

| Garantie | Pourquoi |
|---|---|
| **rien ne se rejoue** (`vues`) | une resynchronisation qui recouvre ne refait pas entendre un K.O. déjà passé |
| **écart minimum** de `ECART_MIN` (90 ms) entre deux départs | en dessous, une rafale n'est plus une suite de sons, c'est un bourdonnement |
| **rattrapage** au-delà de `SEUIL_RATTRAPAGE_SONS` (4) en attente | on ne garde que le dernier — celui qui explique la situation présente |
| **un K.O. avec récompenses = deux sons** | le serveur les envoie sur un seul événement ; les fondre ferait disparaître l'information la plus importante de la partie |
| **couper est immédiat et mémorisé** | ce qui attendait ne sonnera pas, et ne sonnera jamais : un rétablissement ne déverse pas l'arriéré |

### Rien n'est perdu en silence

Un son volontairement non joué est **compté** (`FileSons.ignores`, exposé par `useFileSons().ignores()`).
C'est la différence entre un choix de conception et un repli silencieux, que ce dépôt interdit — et
la phrase de chacun de ces événements est de toute façon dans le journal de partie.

Trois raisons de ne pas jouer un son, toutes comptées : le rattrapage, la coupure, et **l'arrivée du
joueur**. Ce dernier cas mérite son explication : un F5 au quatre-vingtième tour fait livrer toute la
partie d'un bloc, et le navigateur interdit de sonner avant un geste. Les tenir en réserve ferait
entendre un K.O. d'il y a dix minutes au moment où le joueur touche l'écran. **Le son raconte ce qui
arrive, pas ce qui est arrivé avant qu'on écoute.**

## Aucun son avant une interaction — et aucun objet audio

Troisième critère du lot, tenu dans sa forme la plus forte : il n'existe **aucun** `AudioContext`
tant que le joueur n'a pas interagi. Ce n'est pas qu'une obéissance à la règle des navigateurs — un
contexte créé trop tôt naît *suspendu*, écrit un avertissement dans la console de chaque visiteur,
et déverse les sons en retard au premier clic.

`creerMoteur` n'est donc appelé qu'à **un seul endroit** (`eveiller`, dans `lib/sons-provider.tsx`),
branché sur les trois gestes : `pointerdown`, `keydown`, `touchstart`. Un test de garde vérifie
l'unicité de cet appel et la présence des trois gestes — en oublier un laisserait un appareil entier
muet sans que rien ne le dise. Et si tout est coupé sur cet appareil, **on n'ouvre même pas** de
contexte audio : on n'en fabrique pas un pour quelqu'un qui a demandé le silence.

Corollaire : `jouer()` n'ouvre jamais le moteur. Un coup du serveur n'est pas un geste du joueur.

## Le mode silencieux du système est respecté en ne le contournant pas

Il n'existe aucune interface web qui dise « cet appareil est en silencieux ». L'exigence du lot
s'obtient donc en laissant le navigateur faire : sur iOS, Web Audio suit l'interrupteur matériel, et
le volume système s'applique partout.

Le contournement classique — un élément `<audio>` muet joué en boucle pour basculer la page sur le
canal « lecture de média », où l'interrupteur ne s'applique plus — est **délibérément absent**, et un
test de garde vérifie qu'il n'apparaît pas. Forcer un son sur un appareil mis en silencieux, c'est
passer outre une demande explicite de son propriétaire.

## Les réglages — par **appareil** (DJ9)

> *« Bruitages activés, musique coupée, réglage mémorisé par appareil »* — JF, 15/10/2026.

`localStorage`, clé `pbm.jeu.sons`. **Pas** le serveur, contrairement au confort
(`docs/jeu/ACCESSIBILITE.md`) et aux emotes (`docs/jeu/EMOTES.md`), qui suivent le compte. La raison
tient : le volume supportable dépend de l'endroit et de l'appareil, pas de la personne. Le même
enfant veut du son sur la tablette du salon et le silence sur le téléphone emprunté dans le train.

Conséquences voulues :

- **aucune route HTTP**, donc rien à isoler par `user_id` — et rien de ce réglage ne quitte
  l'appareil. C'est pourquoi ce lot n'a pas de test d'accès croisé : il n'a rien à croiser ;
- `/jeu/confort` **dit** où est le son, et pourquoi il n'y est pas. Sans ça, quelqu'un cherche
  pendant dix minutes pourquoi « son coupé » ne l'a pas suivi sur la tablette.

| Réglage | Défaut | Où |
|---|---|---|
| `bruitages` | **activé** | `/jeu/sons`, et un clic sur le plateau |
| `musique` | **coupée** | `/jeu/sons` seulement |
| `volume` | 0,7 | `/jeu/sons` |

Le volume part à 0,7 et non à 1 : le plafond de gain des recettes est déjà calculé pour ne pas
saturer, et 0,7 laisse de la marge **vers le haut** — un réglage qui ne peut que baisser s'entend
comme une panne.

### La musique d'ambiance

Cinq notes sur une gamme pentatonique — l'échelle qui ne produit aucun intervalle dissonant, quel
que soit l'ordre des notes. C'est ce qui permet de la faire tourner pendant une partie de vingt
minutes sans qu'elle agace : il n'y a pas de tension à résoudre, donc pas d'attente qu'on déçoit à
chaque tour de boucle. Coupée par défaut : on ne met pas de musique à quelqu'un qui n'en a pas
demandé.

## Où vivent les choses

| Fichier | Rôle |
|---|---|
| `apps/web/src/lib/game/sons.ts` | **tout ce qui décide** : la banque, les timbres, le registre événement → son, la file, les réglages. Pur — ni React, ni DOM, ni `AudioContext` |
| `apps/web/src/lib/sons-moteur.ts` | la synthèse Web Audio : oscillateurs, bruit blanc, enveloppes, passe-bas. Le seul fichier qui touche le navigateur |
| `apps/web/src/lib/sons-provider.tsx` | les réglages par appareil, et le **moment** où le son s'ouvre |
| `apps/web/src/components/game/son-layer.tsx` | `useFileSons` (le branchement sur les coups), `useMinuterieSonore`, `BoutonSon` / `BarreSon` |
| `apps/web/src/app/jeu/sons/` | l'écran de réglage et la banque écoutable |

### La couche sonore ne provoque aucun re-rendu

La file vit dans une `ref`, pas dans un `useReducer` — parce que **rien à l'écran n'en dépend**. Le
socle d'animation doit se rendre (il y a une pastille à dessiner) ; un son, non. Un état React
aurait fait re-rendre tout le plateau à chaque bruitage, plusieurs fois par seconde pendant un
échange : exactement le coût que le plancher d'images par seconde ne peut pas payer
(`PLANCHER_FPS`, mesuré par `e2e/anim-fluidite.spec.ts`).

### L'interrupteur du plateau est `fixed`, et hors de l'arène

La page `/jeu/parties/{id}` **n'admet aucun défilement** (`docs/jeu/ACCESSIBILITE.md`, mesuré par
`e2e/plateau-responsive.spec.ts`) : un bouton en flux normal l'aurait fait défiler, ce qui ne se voit
ni en `vitest` ni au `type-check`. `BarreSon` suit donc la convention du dépôt — `fixed`,
enveloppe `pointer-events-none`, bouton `pointer-events-auto` — comme le tiroir d'aide, la palette
d'emotes, le journal et le bandeau de pré-chargement.

Coin **haut droit** : c'est le seul libre (aide en haut à gauche, emotes à droite au milieu, journal
et pré-chargement en bas). Et surtout **hors de l'arène** : un bouton posé dans un coin de l'arène
aurait recouvert en permanence le compteur de récompenses d'un des deux joueurs — les deux coins
hauts sont occupés par le bandeau `VsBar`.

## « Je n'entends rien »

Dans l'ordre, du plus fréquent au plus rare :

1. **tu n'as pas encore cliqué** — c'est voulu, et c'est la règle des navigateurs. Le premier
   geste (souris, clavier, ou doigt) ouvre le son. Sur `/jeu/sons`, le texte le dit ;
2. **l'appareil est en silencieux** — le jeu le respecte et ne le contourne pas. Vérifie
   l'interrupteur matériel (iPhone) ou le volume média ;
3. **les bruitages sont coupés sur cet appareil** — en haut à droite du plateau, ou `/jeu/sons`.
   Souviens-toi que ce réglage **ne suit pas le compte** : l'avoir activé sur l'ordinateur ne
   l'active pas sur la tablette ;
4. **l'onglet est en arrière-plan** — la file se vide. Un onglet qui bruite en arrière-plan est la
   façon la plus sûre de faire couper le son pour de bon ;
5. **tu viens d'arriver sur une partie en cours** — les coups déjà diffusés ne sonnent pas (voir
   « rien n'est perdu en silence »). Le prochain coup sonnera ;
6. **le navigateur n'a pas Web Audio** — le jeu reste entièrement jouable, simplement muet. Aucun
   message : un son est un agrément, et le journal porte déjà tout en texte.

## Ce que ce lot n'a pas fait

- **Aucune mesure sur un appareil réel.** Les volumes relatifs sont bornés et ordonnés par
  construction (la minuterie est le plus discret, c'est testé), mais « ça sonne bien » ne se teste
  pas : `/jeu/sons` existe pour qu'on l'écoute. Un réglage d'oreille par JF est attendu, et il se
  fait en changeant des nombres dans `SONS` — les gardes diront si un nombre sort des bornes.
- **Aucun son hors partie.** Les notifications (`docs/jeu/NOTIFICATIONS.md`), le salon et la
  construction de deck restent muets. C'est le périmètre du lot, pas un oubli.
- **La minuterie ne sonne que pour une décision chronométrée** (`FenetreDecision`). Les horloges de
  tour et de partie (DJ4, `lib/game/horloges.ts`) n'ont pas encore de compte à rebours affiché sur
  le plateau : le jour où il existera, `useMinuterieSonore` s'y branche tel quel.
- **Aucun e2e sonore.** Playwright ne sait pas écouter. Les propriétés vérifiables (aucun contexte
  avant un geste, coupure immédiate et mémorisée, comptage des sons passés) le sont en `vitest`
  contre un faux `AudioContext` qui compte ce qu'on lui demande.
