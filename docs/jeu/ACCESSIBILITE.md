# Accessibilité et confort du jeu

> Lot `j-accessibilite-jeu` (jalon J3). Le public de ce jeu est **un enfant de onze ans et son
> entourage** : contraste, cibles, clavier, animations coupables et daltonisme ne sont pas des
> options tardives, ce sont les conditions pour que la partie se joue.
>
> Le socle attendu pour **tout** le produit est dans `docs/UI-UX.md` § « Accessibilité et confort ».
> Cette fiche porte ce qui est propre au jeu : l'audit, ce qu'il couvre, et les trois endroits où le
> plateau impose un compromis — nommé, mesuré, et compensé.

## Les trois réglages du joueur — `/jeu/confort`

| Réglage | Ce qu'il fait | Où il vit |
|---|---|---|
| **animations** | `completes` (défaut) ou `reduites` : plus aucune animation n'est rendue, l'état du plateau reste lisible | `jeu_confort_reglages.animations` |
| **taille du texte** | `normale` (défaut), `grande` (+12,5 %), `tres_grande` (+25 %) sur tout ce qui est en `rem` | `jeu_confort_reglages.taille_texte` |
| **temps rallongé** | **double** les trois horloges d'une partie (DJ4) | `jeu_confort_reglages.temps_rallonge` |

Ils sont **persistés côté serveur**, et c'est un choix : « ne pas animer » et « texte très grand »
sont des besoins de la personne, pas de son appareil. Un enfant qui les a posés sur la tablette du
salon ne doit pas les redemander sur l'ordinateur de sa chambre. Le navigateur n'en garde qu'une
**copie locale** (`localStorage`, clé `pbm.jeu.confort`) qui sert à une seule chose : appliquer les
réglages **avant le premier rendu**, par le script inline du `layout` — sinon on montrerait une
animation à qui a demandé qu'il n'y en ait pas, le temps d'un aller-retour serveur.

Le serveur fait autorité dès qu'il a répondu (il écrase le cache). Un **échec de lecture ne retombe
pas sur les défauts** : on garde ce qui était affiché et on expose l'erreur. Rallumer les animations
de quelqu'un parce qu'une requête a échoué serait pire que de ne rien savoir.

Vocabulaire fermé, validé à l'écriture (422 sur une valeur inconnue) : un réglage qui ne règle rien
est un mensonge fait au joueur.

### Les deux façons de couper une animation — elles se complètent

- **globalement** : le réglage ci-dessus. Il **s'ajoute** à `prefers-reduced-motion` du système, il
  ne le contredit jamais — l'un des deux suffit à tout arrêter, et aucune règle ne peut rallumer ce
  que le système demande d'éteindre. Le réglage du jeu existe parce que tout le monde ne sait pas où
  se trouve celui du système.
- **individuellement** : le bouton « Passer » de la couche d'animation saute l'animation en cours
  sans toucher aux suivantes ni à aucun réglage. Il était là avant ce lot ; il faisait 16 px de haut.

Côté CSS, `html[data-anim="reduites"] *` annule durées **et** `animation-iteration-count` : une
animation en boucle avec une durée de 0,01 ms tourne toujours — elle boucle juste très vite, et
c'est pire que de ne rien faire.

### Temps rallongé : lu au lancement, jamais pendant

Une partie **fige** sa configuration d'horloges à sa création (`docs/jeu/HORLOGES.md`). Le réglage
est donc lu dans `creer_partie`, et nulle part ailleurs : il vaut pour les parties **suivantes**, et
l'écran le dit au joueur. Un test le prouve dans les deux sens (une partie déjà créée ne bouge pas).

**Si l'un des deux joueurs l'a demandé, la partie entière l'obtient.** Dissymétrie assumée : DJ4
fixe un temps *par tour*, pas un temps par joueur et par tour — il faut donc trancher, et on tranche
en faveur de qui a demandé de l'aide. Le joueur rapide perd un confort ; le joueur lent, sans cela,
perdrait la partie. Les deux **marges** (tolérance réseau, grâce de déconnexion) ne sont pas
rallongées : elles compensent le réseau et une déconnexion, pas la lenteur de réflexion.

## L'audit — deux niveaux, et ce que chacun peut prouver

Avant ce lot il n'existait **aucun** audit : le socle était écrit en prose, sans outil derrière.

| Niveau | Fichier | Ce qu'il couvre | Où il tourne |
|---|---|---|---|
| structure | `apps/web/src/__tests__/a11y-jeu.test.tsx` (`axe-core`, jsdom) | rôles, étiquettes, `aria-*` invalides, boutons sans nom accessible | job **web** de la CI, à chaque poussée (~0,2 s) |
| rendu réel | `apps/web/e2e/a11y-jeu.spec.ts` (`@axe-core/playwright`) | **contraste** effectif, **taille des cibles** mesurée, clavier, texte agrandi, animations coupées | job **e2e** de la CI |
| couleurs à la source | `apps/web/src/__tests__/contraste-jeu.test.ts` | le ratio WCAG des **onze** types d'énergie, calculé | job **web** |

Le partage n'est pas arbitraire : `axe` ne sait pas calculer un contraste sans peinture (jsdom n'a
ni couleur effective ni cascade appliquée), et un audit de navigateur ne voit que les pastilles
réellement affichées — jamais les onze types. D'où le troisième fichier, qui mesure les couleurs
**là où elles sont définies** (`lib/game/indicateurs.ts`).

Niveaux retenus : **WCAG 2.2 A et AA**. Les deux audits échouent en **nommant** le coupable
(sélecteur, dimensions, règle) : un test qui dirait seulement « trop petit » obligerait à tout
rouvrir à la main.

### Ce que l'audit a trouvé en s'installant

Aucun de ces défauts n'était visible à l'œil, et tous étaient réels :

| Défaut | Conséquence | Correctif |
|---|---|---|
| `aria-label` sur un `<span>` sans rôle (compteur de récompenses) | **interdit** par WCAG 4.1.2 : les lecteurs d'écran l'ignorent, donc le *score* de la partie n'était annoncé à personne | `role="img"` (`game-board.tsx`) |
| contraste « Psy » 3,99:1 et « Combat » 3,98:1 | sous le minimum AA, abréviations difficiles à lire | fonds éclaircis d'un cran (`indicateurs.ts`) |
| bouton d'ouverture du journal : 93 × **20** px | la plus importante cible du plateau, sous le minimum | `min-h-6` |
| boutons « Passer » / « Accélérer » : **16** px de haut | les deux contrôles d'animation, inatteignables au doigt | `min-h-6 min-w-6`, texte 11 px |
| pastille de type affichant `grass`, `lightning` | un mot **anglais** présenté à un enfant | `styleElement(t).label` → « Plante », « Électrique » |
| les quatre surcouches sans aucun clavier | au clavier, une modale ouverte était un **cul-de-sac** : rien ne la fermait, et le Tab parcourait le plateau derrière elle | `lib/game/use-modale.ts` |
| journal replié = partie **muette** pour un lecteur d'écran | la partie avançait sans qu'un mot soit annoncé | région `aria-live="polite"` (`journal-annonce`) |

## Le clavier

`lib/game/use-modale.ts` donne aux surcouches les trois comportements d'une boîte de dialogue :
**Échap** ferme, **Tab** reste dedans, le focus **revient** d'où il venait.

| Surcouche | Échap | Tab piégé | Pourquoi |
|---|---|---|---|
| fenêtre de décision | non | **oui** | elle est **obligatoire** : le moteur attend une réponse, et son horloge en donne une par défaut (DJ4). Une touche qui la ferait disparaître sans répondre laisserait un plateau bloqué |
| écran de fin | oui (replie) | oui | repliée, ce n'est plus qu'un bouton : le crochet est inactif |
| consultation d'une zone | oui | oui | modale (`aria-modal="true"`) |
| carte agrandie | oui | **non** | non modale : le plateau reste autoritaire derrière, en sortir au Tab est attendu |

⛔ **Le piège qui a failli coûter la navigation entière.** Le crochet restituait le focus au
démontage *dans tous les cas*. Or le zoom de carte s'ouvre **au focus** d'une carte et ne contient
aucun contrôle : en tabulant, il se démontait, ramenait le focus sur la carte quittée, et le Tab
suivant le rouvrait — la tabulation tournait en rond et n'atteignait **jamais** la barre d'actions.
Le crochet ne restitue donc le focus que s'il l'a réellement **pris**. C'est l'e2e « une partie se
joue au clavier seul » qui l'a trouvé ; aucun test unitaire ne l'aurait vu.

L'anneau de focus des éléments du plateau (cartes, piles) est dans `globals.css` — en
`:focus-visible` et non `:focus` : à la souris, ce serait du bruit.

## Les trois compromis du plateau — nommés, mesurés, compensés

Le plateau ne tolère **aucun défilement** (critère d'acceptation de `j-plateau-layout`, gardé par un
job e2e) et met neuf zones par joueur à l'échelle d'un écran de téléphone. Trois exigences
d'accessibilité s'y heurtent de front. On les tranche, on dit pourquoi, et on donne la voie de
remplacement.

1. **Taille des cibles dans l'arène (WCAG 2.5.8).** Mesuré : une carte de banc fait **4,7 × 6,5 px**
   à 844 × 390. L'agrandir casse le plateau. La règle `target-size` est donc désactivée **pour le
   plateau seulement** dans l'audit e2e, au titre de l'exception « *Equivalent* » du critère : tout
   coup jouable sur une carte est **aussi** un bouton de la barre d'actions, et ces boutons-là sont
   mesurés (≥ 24 px). S'y ajoutent le clavier (Tab + Entrée) et l'agrandissement au focus. Les
   contrôles **hors** arène (barre d'actions, journal, aide) restent mesurés sans exception.
2. **Taille de texte sur la page d'une partie.** Mesuré : en « très grande », le document passe à
   **432 px** de haut pour 390 disponibles — le plateau défile, c'est-à-dire une régression du
   critère. Compenser en réduisant l'arène la ramènerait à une cinquantaine de pixels : un plateau
   illisible au nom de la lisibilité. Le réglage est donc **neutralisé sur cette page**
   (`html[data-ecran="plateau"]`, posé par `partie-view.tsx`), et la lisibilité d'une carte passe par
   son **agrandissement**. L'écran de confort le dit au joueur plutôt que de le lui laisser
   découvrir. Un e2e prouve les deux moitiés : la police grossit hors partie, et le plateau ne
   défile pas.
3. **44 px (WCAG 2.5.5, niveau AAA).** Hors d'atteinte dans l'arène pour la même raison qu'au
   point 1. Les boutons hors plateau l'atteignent déjà (`components/ui/button`). On tient donc **AA
   partout**, et AAA là où c'est possible.

## Daltonisme : jamais la couleur seule

Règle posée par `j-plateau-etat-visuel` et maintenue ici : chaque type d'énergie porte une
**abréviation** (Pl, Fe, Ea, Él, Psy, Co, Ob, Mé, Dr, Fé, In) et un **nom français** ; chaque état
spécial une **icône** en plus de l'orientation de la carte. Un type inconnu du serveur retombe sur
un repère **neutre nommé** (« ? », « Type inconnu »), jamais une couleur devinée (D9).

Toute couleur ajoutée à `ELEMENTS` doit garder **4,5:1** entre fond et texte — le test le calcule et
nomme le fautif.

## Annonces pour lecteur d'écran

La région `journal-annonce` (`aria-live="polite"`, `sr-only`) annonce la **dernière phrase du
journal**, celle qui est déjà écrite en français par `lib/game/journal.ts` : une seule formulation
pour l'œil et pour l'oreille, donc jamais deux versions qui divergent. `polite` et non `assertive` :
une annonce ne doit pas couper un joueur qui lit ses options. Et c'est le **dernier** événement, pas
tout le coup — réciter huit lignes à chaque attaque rendrait l'annonce inutilisable.

Existaient déjà et restent : le bandeau de connexion dégradée (`role="status"`), les raisons de
refus de la barre d'actions (`aria-label` portant la règle citée), les panneaux d'aide.

## Où c'est écrit

| Quoi | Où |
|---|---|
| réglages purs (client) | `apps/web/src/lib/game/confort.ts` |
| fournisseur + cache local | `apps/web/src/lib/confort-provider.tsx` |
| écran | `apps/web/src/app/jeu/confort/` |
| clavier des surcouches | `apps/web/src/lib/game/use-modale.ts` |
| CSS (animations, échelle, focus) | `apps/web/src/app/globals.css` |
| réglages purs (serveur) + facteur de temps | `apps/api/src/pbm_api/jeu/confort.py` |
| persistance | `apps/api/src/pbm_api/jeu/confort_service.py`, `models/jeu_confort.py` |
| routes `GET|PATCH /jeu/confort/reglages` | `apps/api/src/pbm_api/routers/jeu_confort.py` |
| branchement sur les horloges | `apps/api/src/pbm_api/games/horloges.py`, `games/service.py` |
| migration | `apps/api/migrations/versions/c4f1a8b7e2d3_jeu_confort_reglages.py` |
