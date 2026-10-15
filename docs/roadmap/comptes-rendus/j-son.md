# `j-son` — Sons du jeu : entendre l'attaque, la pioche et la victoire

**Lot** P2 · piste Graphisme & animations · couloir J-GFX (chimera) · jalon J3 · palier 15 · taille S
**Branche** `roadmap/j-son` · **Base** `github/main` à `83c4cda`
**Décision appliquée** DJ9 — *« Bruitages activés, musique coupée, réglage mémorisé par appareil »* (JF, 15/10/2026)

## Résumé

Le jeu sonne. Dix-sept bruitages suivent les **mêmes événements** que les animations — le plan
sonore part littéralement du plan d'animation —, la minuterie est le son le plus discret de la
banque *par invariant testé*, et l'interrupteur est à un clic sur le plateau.

La décision qui structure tout le lot : **il n'y a aucun fichier audio dans le dépôt.** Chaque son
est une *recette* en données (formes d'onde, fréquences, enveloppe) que le navigateur fabrique au
moment où on l'entend. Le risque nommé par le lot — *« des sons pris au hasard sur Internet, c'est un
risque de droits pour quelques kilo-octets d'effet »* — n'est donc pas encadré par une liste de
crédits à tenir à jour : il est **supprimé**. Rien à créditer, rien à re-sourcer le jour où un site
d'échantillons ferme, zéro octet expédié, et une banque de sons qui se teste en `vitest`.

## Livrables

| | |
|---|---|
| Banque sourcée | `apps/web/src/lib/game/sons.ts` — 17 recettes, 11 timbres de type, registre événement → son, file, réglages. **Pur** : ni React, ni DOM, ni `AudioContext`, ni fichier |
| Synthèse | `apps/web/src/lib/sons-moteur.ts` — oscillateurs, bruit blanc, enveloppes, passe-bas. Le seul fichier qui touche le navigateur |
| Réglages par appareil | `apps/web/src/lib/sons-provider.tsx` — `localStorage` (`pbm.jeu.sons`), et le **moment** où le son s'ouvre |
| Branchement | `apps/web/src/components/game/son-layer.tsx` — `useFileSons`, `useMinuterieSonore`, `BoutonSon` / `BarreSon` |
| Écran + banque écoutable | `apps/web/src/app/jeu/sons/` (`/jeu/sons`, 2,71 kB) |
| Câblage | `layout.tsx` (fournisseur), `partie-view.tsx` (file + barre), `fenetre-decision.tsx` (minuterie), `confort-view.tsx` (lien et explication du « par appareil ») |
| Fiche | `docs/jeu/SONS.md` + sa ligne dans la carte des fiches de `CLAUDE.md` |
| Tests | `sons.test.ts` (37), `sons-provider.test.tsx` (15), `sons-origine-garde.test.ts` (4) |

## Les trois critères d'acceptation, et leur preuve

### 1. « Tous les sons sont libres de droits, et leur origine est écrite dans le dépôt »

Tenu de la seule façon qui se vérifie : **il n'y a rien à sourcer.** L'origine de chaque son est la
ligne qui le décrit dans `sons.ts`.

Et la garde est dans le code, pas dans la documentation — `sons-origine-garde.test.ts` refuse :

- tout fichier audio dans `apps/web/public/` (parcours récursif, 9 extensions) ;
- tout `decodeAudioData`, tout `new Audio(`, toute URL de média dans les quatre fichiers de la
  couche sonore — un son peut venir d'un CDN sans qu'aucun fichier n'entre dans le dépôt ;
- le contournement du mode silencieux (`<audio>` muet, `playsinline`, `audioSession`).

La garde lit le **code sans ses commentaires** (`sansCommentaires()`), et c'est un détail qui compte :
les fichiers du lot *expliquent* pourquoi le contournement `<audio>` est absent. Une garde qui lit la
prose interdirait d'expliquer ce qu'elle interdit, et le premier réflexe serait d'effacer
l'explication pour faire passer la CI. La première version du test est tombée exactement là-dessus.

Un test complémentaire dans `sons.test.ts` sérialise `SONS` et vérifie qu'il ne contient ni URL ni
extension de média : une recette ne doit contenir que des nombres et des formes d'onde.

### 2. « La coupure est immédiate et mémorisée »

- **Immédiate** : le volume général est **un seul** nœud de gain. Couper le met à zéro dans le geste
  même, avant le prochain rendu de React — ce qui était déjà en vol s'éteint. Prouvé par
  `sons-provider.test.tsx` contre un faux `AudioContext` qui retient la dernière valeur posée.
- **Mémorisée** : `localStorage`, clé `pbm.jeu.sons`. Le test coupe, démonte, remonte, et vérifie que
  la bascule est déjà sur « coupé ».
- **Côté file** : couper vide **et mémorise** ce qui attendait, de sorte qu'un rétablissement ne
  déverse pas l'arriéré d'un coup. Et les coups qui arrivent pendant que c'est coupé ne sont même pas
  mis en attente.
- Un test vérifie aussi qu'on **ne fabrique pas** de contexte audio juste pour couper, quand rien
  n'était ouvert.

### 3. « Aucun son ne se déclenche avant une interaction du joueur »

Tenu dans sa forme la plus forte : il n'existe **aucun objet audio** avant le premier geste.

Ce n'est pas qu'une obéissance à la règle des navigateurs. Un `AudioContext` créé trop tôt naît
*suspendu*, écrit un avertissement dans la console de chaque visiteur, et déverse les sons en retard
au premier clic. `creerMoteur` n'est donc appelé qu'à **un seul endroit**, branché sur `pointerdown`,
`keydown` et `touchstart` — et un test de garde vérifie cette unicité et la présence des trois
gestes (en oublier un laisserait un appareil entier muet sans que rien ne le dise).

Quatre tests le prouvent : aucun contexte au chargement ; aucun contexte ni son si on demande à jouer
avant un geste (*un coup du serveur n'est pas un geste*) ; un seul contexte même après trois gestes ;
aucun contexte du tout si le son est coupé sur cet appareil.

## Le défaut que les tests ont trouvé, et qui n'aurait fait aucun bruit

Le lot exigeait une « attaque par type ». Premier jet : le timbre posé sur `attaque_declaree`.
Le test de parité avec le plan d'animation est tombé — et il avait raison.

Le socle d'animation ne typpe `attaque_declaree` **que lorsque l'attaque a raté**
(`typageEvenement`, `animations.ts`). Pour un coup qui porte, c'est l'événement `degats` qui porte le
type, les dégâts réels, la faiblesse et la résistance. Un timbre posé sur l'attaque déclarée serait
donc resté muet sur **toutes les attaques qui portent** — c'est-à-dire exactement quand ça compte.

Et le mode de panne est le pire possible : un son d'attaque générique au lieu d'un son typé ne
ressemble à rien d'anormal. Personne ne signale un son qui *existe mais n'est pas le bon*.

Corrigé en posant le timbre là où la donnée vit : `attaque` est le **geste**, volontairement neutre ;
`impact` est le **coup**, typé. Avec deux gardes pour que ça ne se reperde pas :

- `TIMBRES_TYPE` a une ligne par type de `SPECS` — parité testée, donc un douzième type d'énergie
  ajouté à l'effet visuel sans timbre casse la CI ;
- l'intensité vient de `intensiteDe()`, la fonction même qui dimensionne l'effet visuel : aucun seuil
  n'est recopié, un coup faible est à la fois plus discret à l'écran et à l'oreille.

## Décisions de conception, et ce qui les motive

| Décision | Pourquoi |
|---|---|
| Le plan sonore **part du plan d'animation** (`planifier()`) | il n'y a pas deux lectures des événements du serveur qui pourraient divergir : il n'y en a qu'une. Un son et son effet visuel viennent de la même entrée |
| Un K.O. avec récompenses = **deux** sons | le serveur les envoie sur un seul événement. Les fondre en un bruit ferait disparaître l'information la plus importante de la partie — le compte des récompenses. Même découpage que la file des moments clés côté image |
| La file vit dans une **`ref`**, pas un `useReducer` | rien à l'écran n'en dépend. Un état React aurait fait re-rendre tout le plateau à chaque bruitage, plusieurs fois par seconde pendant un échange — le coût exact que le plancher d'images par seconde ne peut pas payer. La couche sonore provoque **zéro re-rendu** |
| Les coups déjà diffusés à l'arrivée du joueur ne sonnent pas | un F5 au 80ᵉ tour livre toute la partie d'un bloc. Les tenir en réserve ferait entendre un K.O. d'il y a dix minutes au premier clic. Le son raconte ce qui arrive, pas ce qui est arrivé avant qu'on écoute |
| Réglage **par appareil**, pas par compte | DJ9, et la raison tient : le volume supportable dépend de l'endroit, pas de la personne. Conséquence voulue — **aucune route HTTP**, donc rien ne quitte l'appareil |
| Un écran `/jeu/sons` à part, et non une section de `/jeu/confort` | ils ne se comportent pas pareil (compte vs appareil). Les mettre côte à côte aurait laissé quelqu'un chercher pourquoi « son coupé » ne l'a pas suivi sur la tablette. `/jeu/confort` **dit** où est le son et pourquoi il n'y est pas |
| La banque est **écoutable** sur `/jeu/sons` | on ne choisit pas un volume dans l'abstrait, on l'essaie — et le son à essayer est le plus fort (le K.O.), pas le plus discret. C'est aussi là qu'on entend qu'un son est devenu agressif après une retouche, ce qu'aucun test ne dira |
| Le mode silencieux est respecté **en ne le contournant pas** | aucune interface web ne dit « cet appareil est en silencieux ». On laisse le navigateur appliquer le réglage de l'appareil, et le contournement `<audio>` muet est délibérément absent — et gardé |

### Un repli de placement, corrigé avant de pousser

L'interrupteur du plateau était d'abord posé dans l'arène, `absolute left-2 top-2`. En relisant
`VsBar`, les **deux coins hauts de l'arène portent les compteurs de récompenses** des deux joueurs :
le bouton les aurait recouverts en permanence. Déplacé en `BarreSon`, `fixed` au coin haut droit du
viewport — le seul libre (aide en haut à gauche, emotes à droite au milieu, journal et
pré-chargement en bas) — et suivant la convention du dépôt (enveloppe `pointer-events-none`, bouton
`pointer-events-auto`), parce que la page du plateau n'admet aucun défilement.

## Preuves

Suites lancées sur **devAI** (chimera n'a ni node ni pnpm dans sa WSL ; le dépôt et la branche
vivent sur chimera, les suites front tournent ici — atelier `/tmp/pbm-son`, `node_modules` lié,
binaires appelés directement).

| Vérification | Résultat |
|---|---|
| `tsc --noEmit` | ✅ 0 erreur (`noUncheckedIndexedAccess` actif : la banque est typée en objet concret via `satisfies`, pas en `Record`) |
| `eslint .` | ✅ 0 erreur (2 avertissements **préexistants**, dans `game-realtime.test.ts` et `bandeau-prechargement.test.tsx`, fichiers non touchés) |
| `vitest run` (suite complète) | ✅ **956 tests, 101 fichiers**, 0 échec |
| dont `sons.test.ts` | ✅ 37 cas — bornes, parités, file, rattrapage, réglages |
| dont `sons-provider.test.tsx` | ✅ 15 cas — faux `AudioContext` qui compte contextes, oscillateurs et sources de bruit |
| dont `sons-origine-garde.test.ts` | ✅ 4 cas — aucun fichier audio, aucune URL, aucun contournement, un seul `creerMoteur` |
| `next build` | ✅ réussi, `/jeu/sons` à **2,71 kB** |
| Non-régression animations | ✅ `animation-layer.test.tsx` (11), `game-board-animations.test.tsx` (4) verts sans modification |

**La CI GitHub Actions fait foi** — SHA de la branche et du commit de fusion plus bas.

## Grille

| Tâche | État | Preuve |
|---|---|---|
| `dev` | fait | banque, moteur, fournisseur, file, écran `/jeu/sons`, câblage |
| `tests` | fait | 56 cas neufs ; suite complète 956/956 ; build vert |
| `securite` | fait | aucun secret ; **aucune route HTTP** (réglage local) donc rien à isoler par `user_id` ; `/jeu/sons` filtre par `game_access` (D11) → page inexistante ; le mode silencieux du système n'est pas contourné |
| `maquette` | fait | l'interrupteur reprend exactement les classes des boutons de la couche d'animation ; `/jeu/sons` reprend la structure de `/jeu/confort` (bordures `rgba(157,0,255,0.3)`, cibles ≥ 44 px, `font-heading`) |
| `doc_tech` | fait | `docs/jeu/SONS.md` + ligne dans la carte des fiches de `CLAUDE.md` |
| `release_uat` | fait | recette locale : suite complète + build sur devAI (D2 : pas d'UAT, la recette se fait localement) |
| `release_prod` | **non fait** | hors périmètre : aucun déploiement depuis un lot. La PROD se livre à part, par devAI |
| `backlog` | n/a | tenu par la file d'ordonnancement (consigne du couloir : ne pas toucher `etat.json`, `ROADMAP.html`, `BACKLOG.md`, `prompts/`) |
| `compte_rendu` | fait | ce fichier |

## Écarts au plan

- **Aucun fichier audio**, là où le livrable disait « banque de sons sourcée ». C'est la même chose
  autrement : la banque est sourcée *par sa recette*, et la source est dans le dépôt. L'écart est
  assumé, et il est la réponse directe au risque que le lot nommait.
- **La minuterie ne sonne que pour une décision chronométrée** (`FenetreDecision`). C'est le seul
  compte à rebours qui existe aujourd'hui à l'écran : les horloges de tour et de partie (DJ4,
  `lib/game/horloges.ts`) n'ont pas encore d'affichage sur le plateau. `useMinuterieSonore` s'y
  branchera tel quel le jour où il existera.
- **Pas de test d'accès croisé** : ce lot n'ajoute aucune route utilisateur. Le réglage est local à
  l'appareil, il n'y a rien à croiser. L'écran `/jeu/sons` est lui gardé par `game_access` (D11).
- **Pas d'e2e sonore** : Playwright ne sait pas écouter. Les propriétés vérifiables le sont en
  `vitest` contre un faux `AudioContext`.

## Reste à faire

1. **Un réglage d'oreille par JF.** Les volumes relatifs sont bornés et *ordonnés* par construction
   (la minuterie est le plus discret, c'est un invariant testé), mais « ça sonne bien » ne se teste
   pas. `/jeu/sons` existe pour ça : on écoute, et on change des nombres dans `SONS` — les gardes
   diront si un nombre sort des bornes.
2. **Écouter sur un vrai téléphone.** Un passe-bas se comporte autrement sur un haut-parleur de
   téléphone que sur un casque, et aucune mesure en CI ne le dira.
3. **Sons hors partie** (notifications, salon, construction de deck) : muets, par périmètre.
4. **Livraison PROD** : à faire à part, par devAI, hors de ce lot.
