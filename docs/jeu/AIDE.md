# AIDE.md — L'aide en jeu : pourquoi je ne peux pas faire ça, et que puis-je faire

> Lot `j-plateau-aide` (jalon J3, palier 15). **Le jeu est celui d'un enfant de onze ans** : un jeu
> qui explique ses refus s'apprend en jouant, un jeu muet se désinstalle. Cette fiche dit où vivent
> les textes, ce qui les garde justes, et quoi faire quand ils doivent changer.

## Les quatre pièces, et où elles vivent

| Pièce | Fichier | Nature |
|---|---|---|
| Explications des règles, glossaire, coups proposés | `apps/web/src/lib/game/aide.ts` | module **pur** (ni React ni E/S) |
| Parcours de la première partie | `apps/web/src/lib/game/guide.ts` | module **pur** |
| Le tiroir à l'écran | `apps/web/src/components/game/aide-panel.tsx` | composant React |
| La garde de justesse | `apps/game/tests/test_parite_aide_front.py` | test du job CI `game` |

**Aucune route, aucune table, aucun appel réseau.** Tout ce que l'aide montre se déduit de la vue que
le serveur envoie déjà (`vue.actions_legales`, `vue.actions_refusees`, les zones) et des textes de
`aide.ts`. C'est voulu : pas de nouvelle surface d'attaque, pas de nouveau filtrage par `user_id` à
tenir, et l'aide reste disponible même quand le réseau vacille.

## La règle qui tient tout : le corpus fait foi, jamais le code

Le risque nommé par la fiche du lot : *« écrire l'aide à partir du code plutôt que du corpus de
règles : les deux divergent, et l'aide explique des règles qui ne sont pas celles appliquées. »*

La parade est mécanique. `test_parite_aide_front.py` lit les trois côtés et refuse quatre situations :

1. une règle que le moteur peut citer dans un refus **sans explication** dans `aide.ts` → le joueur
   reçoit un refus qu'il ne comprend pas (c'est le 1ᵉʳ critère d'acceptation du lot) ;
2. une explication qui cite un identifiant **absent de `docs/jeu/REGLES.md`** → l'aide a inventé une
   règle, ou recopié le code ;
3. une étape du parcours guidé qui enseigne un identifiant absent du corpus ;
4. une étape du parcours guidé dont la règle **n'est pas expliquée** → le guide fait obéir sans
   apprendre.

Le relevé côté moteur se fait par **analyse syntaxique** (`ast`), pas par `grep` : un appel
`refus(...)` s'écrit couramment sur plusieurs lignes (les messages sont longs) et une expression
régulière le manquerait. Le test relève `refus(<regle>, <message>)` **et** la construction directe
d'un `Verdict(accepte=False, regle=…)`. Une citation **calculée** à l'exécution (non littérale) fait
échouer le test : elle serait invérifiable, et un refus inexplicable est un refus muet déguisé.

Le module qui *définit* `refus()` (`pbm_game/actions/modele.py`) est écarté du relevé : il construit
un `Verdict` depuis son propre paramètre, sa citation est non littérale par construction. C'est la
fabrique, pas un site de refus.

### Ajouter une explication — la marche à suivre

```bash
# 1. Lire la règle DANS LE CORPUS, pas dans le code.
grep -n 'R-8\.2' docs/jeu/REGLES.md

# 2. Ajouter l'entrée dans EXPLICATIONS (apps/web/src/lib/game/aide.ts) :
#    titre court, explication en une ou deux phrases d'enfant, ALTERNATIVE, mots du glossaire.

# 3. Prouver la parité (job `game`, Python pur, aucune base).
cd apps/game && uv run pytest tests/test_parite_aide_front.py -q
cd ../web   && pnpm exec vitest run src/lib/game/aide.test.ts
```

Quatre contraintes, chacune tenue par un test de `aide.test.ts` :

- **l'`alternative` n'est pas facultative.** Un refus qui ne rouvre aucune porte est ce qui fait
  désinstaller un jeu. C'est la moitié utile de l'aide ;
- **aucun numéro de règle dans un texte montré au joueur.** `R-5.4` sert aux tests et au support, pas
  à l'enfant qui joue — le test l'interdit par expression régulière ;
- **tout mot cité dans `mots` a son entrée au `GLOSSAIRE`.** Expliquer une règle avec un mot qu'on
  n'explique pas ne fait que déplacer le problème ;
- **une explication tient en moins de 320 caractères.** Au-delà, c'est du corpus recopié.

### Le niveau cité : une règle, ou une section

`EXPLICATIONS` est indexé sur ce que le **moteur cite**, qui n'est pas toujours une règle `R-x.y` :
quatre refus de la famille « talent » (`pbm_game/actions/familles_jeu.py`, autour de la ligne 1263)
citent la **section** `R-5` (« Déroulé d'un tour »). On explique donc le niveau cité tel qu'il est,
au lieu de deviner laquelle des six règles de la section vaut — ce serait une aide qui dit autre
chose que ce que le moteur applique. Le `message` du moteur, affiché juste au-dessus de
l'explication, porte de toute façon le détail précis (« Seul le joueur actif active un talent
(R-5.1). »).

⚠️ **Écart ouvert, à trancher par JF** : le docstring de `Verdict`
(`pbm_game/actions/modele.py`) annonce que `regle` porte un identifiant `R-x.y`. Ces quatre sites
dérogent. Les resserrer (`R-5.1` pour les deux premiers, `R-5.3` pour le talent non activable) est un
jugement sur la famille « talent » que le lot `j-plateau-aide` n'a pas pris seul. Tant que ce n'est
pas tranché, la garde accepte les deux niveaux et exige que les deux soient expliqués.

## Les deux formes d'un refus, et comment l'écran les rattrape

Le serveur dit « non » de deux façons, et l'aide doit savoir lire les deux :

| D'où | Forme | Ce que fait l'aide |
|---|---|---|
| **Grisage préventif** — `vue.actions_refusees[]` | `{regle: "R-5.4", message: "…"}`, champs séparés, HTTP 200 | lit `regle` directement |
| **Coup soumis puis refusé** — `POST /games/{id}/actions` | HTTP **422**, `{"detail": "<message du moteur> (R-5.4)"}` : les deux fondus en une chaîne | `regleDuRefus()` récupère l'identifiant par expression régulière |

`expliquerRefus()` accepte indifféremment l'une ou l'autre. Si l'identifiant est inconnu (ou absent),
elle rend `explication: null` et **garde le message du serveur** : on n'invente jamais une explication
au hasard, et on ne masque jamais la raison du moteur. Le serveur fait autorité sur le *pourquoi*
factuel ; l'aide n'ajoute que la règle en français d'enfant et la porte de sortie.

## « Que puis-je faire ? » — proposer sans jouer

`suggestions(vue, maximum)` prend `vue.actions_legales` — **calculées par le serveur** — les trie
dans un ordre **pédagogique** (ce qui bloque la partie d'abord : une décision en attente, une pioche
obligatoire ; l'accessoire ensuite), en garde trois au plus, et met une phrase sur chacune.

Deux décisions à connaître :

- **`abandonner` n'est jamais suggéré.** Il est légal à tout instant (R-14.3) et serait donc la
  première suggestion de toutes les parties difficiles. Le bouton reste dans la barre d'actions : on
  ne le cache pas, on ne le recommande pas. (`deserter` non plus.)
- **Une `Suggestion` ne porte pas de `params`.** Elle a de quoi *afficher* un coup (`type`,
  `etiquette`, `pourquoi`), rien de quoi le *soumettre*. L'aide ne peut donc pas jouer à la place du
  joueur, même par accident d'un futur appelant — c'est le 3ᵉ critère d'acceptation tenu par la
  **structure des données**, pas par une intention. Les coups sont rendus en lignes de texte, jamais
  en boutons.

**Hésitation.** Le tiroir ne propose rien avant **12 s** (`delaiSuggestionMs`) : une aide qui parle
avant qu'on réfléchisse empêche d'apprendre. Le minuteur repart à chaque changement de plateau — il
mesure l'attente **du joueur**, pas l'âge de la page — et ne court ni hors de son tour ni sur une
partie terminée. Replié, il se contente d'un appel discret (« Tu hésites ? ») : on n'ouvre rien
par-dessus le plateau d'un joueur qui réfléchit.

## La première partie guidée

`ETAPES_GUIDE` (`guide.ts`) décrit cinq étapes — poser l'Actif, remplir le banc, attacher une
énergie, attaquer, prendre une récompense. Le parcours s'arrête là : le joueur a fait le tour complet
de la boucle du jeu et sait comment on gagne ; continuer serait du bavardage.

Trois propriétés, chacune née d'un piège réel :

- **le guide constate, il ne pilote pas.** Une étape porte une consigne et un prédicat `accompli(vue)`
  — aucune action. Le joueur joue lui-même, par la barre d'actions habituelle ;
- **la progression ne recule jamais.** `accompli` lit l'état courant, et un état peut redevenir faux
  (l'Actif adverse blessé est remplacé, ses dégâts disparaissent de la vue). `avancerGuide(vue,
  atteint)` ne part donc **jamais** de zéro : elle avance depuis l'étape mémorisée. Sans cela le guide
  renverrait le joueur à « attaque » alors qu'il a déjà attaqué — pire qu'une absence de guide ;
- **une vue illisible ne casse pas l'écran.** `separerCamps` lève sur une vue incohérente (et c'est
  bien : un plateau à moitié défini doit se signaler). Le guide attrape et se tait : il est un décor
  posé sur le jeu, il ne fait pas tomber la partie pour une aide.

**Mémoire du navigateur** : `estPremierePartie(stockage)` / `marquerGuideVu(stockage)`, clé
`pbm.jeu.guide-vu`. Le stockage est **injecté** (testable sans navigateur, `null` au rendu serveur).
**Stockage illisible = on guide** : entre proposer un guide à qui n'en a plus besoin (il le replie) et
le refuser à un enfant qui débute (il reste bloqué), le choix est fait — et il est écrit, pas caché
dans un `catch` muet. `partie-view.tsx` tranche **une fois, au montage** : la réponse ne doit pas
changer en cours de partie, sinon le guide se refermerait sous les doigts du joueur.

## Où le tiroir est posé, et pourquoi ce coin-là

**En haut à GAUCHE, borné à 15rem.** C'est une contrainte, pas un goût : les quatre coins du plateau
sont déjà pris, et deux portent des boutons que l'e2e clique vraiment.

| Coin | Qui l'occupe |
|---|---|
| **haut gauche** | **libre** — le statut de connexion est centré (`game-board.tsx`) |
| haut droite | `anim-accelere` / `anim-sauter` (`animation-layer.tsx`, `absolute right-2 top-2`) |
| bas, pleine largeur | le journal de partie (`journal-panel.tsx`) |
| bas gauche | l'écran de fin replié (`fin-partie.tsx`) |

Posé en haut à droite — le réflexe naturel pour un bouton d'aide — le tiroir **recouvrait
`anim-sauter`** sur l'écran de référence du jeu (**844 × 390**, téléphone en paysage) :
`anim-fluidite.spec.ts` le clique, et Playwright aurait échoué sur une interception de clic. Défaut
invisible en vitest comme en `tsc` — le mode de panne que ce dépôt connaît déjà (voir
`docs/UI-UX.md` § Plateau). La largeur est bornée pour la même raison : à 15rem, le flanc droit de
l'arène reste cliquable en paysage comme en portrait.

Et comme tous ses voisins, le tiroir est **`fixed`** : la page `/jeu/parties/{id}` ne tolère aucun
défilement (`e2e/plateau-responsive.spec.ts`), et un panneau en flux normal la casserait. Un test de
`aide-panel.test.tsx` garde les deux invariants (hors du flux, ancré à gauche, largeur bornée) avec
le message qui explique la conséquence — pour que le prochain lot ne les redécouvre pas par une CI
rouge.

## « Je ne comprends pas pourquoi mon coup est refusé »

1. **Le message vient-il bien du moteur ?** Le tiroir affiche la chaîne du serveur telle quelle,
   au-dessus de l'explication. Si elle est générique (« Coup impossible. Réessaie dans un
   instant. »), c'est que l'appel a échoué **sans** `ApiError` — ce n'est pas un refus de règle, c'est
   un incident réseau (`game-board.tsx`).
2. **L'explication manque-t-elle ?** Alors la règle citée n'est pas dans `EXPLICATIONS` — ce qui ne
   doit pas arriver : le job CI `game` casse dans ce cas. Si ça arrive quand même, c'est que le refus
   cite une règle **calculée** (le test ne peut pas la voir statiquement). Lire le `regle` reçu dans
   `vue.actions_refusees` et ajouter l'entrée.
3. **L'explication dit-elle autre chose que le moteur ?** C'est le risque du lot. Comparer à
   `docs/jeu/REGLES.md` — le corpus l'emporte (R-1.3) — et corriger le texte, pas le moteur.

## Ce qui reste à faire

- **Relire les textes avec JF** (mission 4 du lot : « c'est le lot où le ton compte plus que le
  code »). Les 26 explications, les 28 mots du glossaire et les 5 consignes du guide sont écrits mais
  **n'ont pas encore été relus** par JF, et un enfant de onze ans n'a pas encore essayé le parcours.
- **Le passage du parcours guidé par un vrai débutant** : le 2ᵉ critère d'acceptation (« se termine
  sans aide extérieure par un joueur qui n'a jamais joué ») est prouvé mécaniquement — on rejoue la
  suite des états qu'un débutant produit et le guide va de la première étape à la fin sans
  cul-de-sac — mais pas encore humainement.
- **Les mots du glossaire ne sont pas cliquables depuis une explication.** `motsDuTexte()` sait les
  repérer dans un texte (sur le mot entier : « Objet » ne se déclenche pas sur « objectif ») ; le
  tiroir ne s'en sert pas encore pour relier une explication à son glossaire.
