# DEMANDES.md — demandes de décision : quand le moteur doit attendre un joueur

> Lot `j-effets-choix` (jalon J2). Paquet `pbm_game.demandes`, **pur** (aucune E/S), comme tout le
> moteur. Il complète `EFFETS.md` : la pile d'effets (`effets/pile.py`) savait résoudre d'un seul
> trait ; ici elle sait **s'arrêter** pour réclamer un choix à un joueur — y compris à l'adversaire,
> en plein tour de l'autre — puis **reprendre**. Les règles citées (`R-x.y`) renvoient à
> `docs/jeu/REGLES.md` ; la décision modélisée sert surtout **R-9.3 étape D** (« choix imposés par
> l'attaque ») et tout effet de carte qui fait choisir.

## Le piège évité : une demande est une donnée, pas une attente de code

Le réflexe naïf serait de bloquer un fil d'exécution côté serveur le temps que le joueur réponde.
Une partie sur deux resterait alors figée à la première déconnexion. Ici, **la demande vit dans
l'état** (`EtatPartie.resolution`), sérialisée avec lui : une partie interrompue au milieu d'une
demande se recharge (F5, redémarrage, reprise de journal) **exactement à cette demande, temps
restant compris**. Rien n'attend en mémoire.

## Les six catégories de demande (`demandes/modele.py`)

| Catégorie | Ce qu'on réclame | Forme de la réponse (`choix`) |
|---|---|---|
| `carte` | **une** carte d'un ensemble | un id |
| `cartes` | **plusieurs** (de `minimum` à `maximum`) | plusieurs ids, sans doublon |
| `ordre` | **ordonner** un ensemble | une permutation de `options` |
| `oui_non` | **oui / non** | `("oui",)` ou `("non",)` |
| `type` | **un type** (énergie, Pokémon) | un id de `options` |
| `nombre` | **un entier** de `[minimum, maximum]` | `(str(n),)` |

Une `DemandeDecision` porte : `destinataire` (le joueur qui décide — **peut être l'adversaire**),
la catégorie, les `options`, les bornes, `obligatoire`, `ensemble_cache` (l'ensemble de choix est
caché → la projection ne montre qu'un **nombre**, jamais les identités : anti-triche), une
**réponse par défaut** calculée, et une **horloge** (`delai_ms` / `temps_restant_ms`). Catégorie
inconnue = refus (D9). Une réponse hors-ensemble, en doublon ou de mauvaise cardinalité est refusée
(`valider_reponse`) : **le serveur fait autorité**, un client ne « répond » jamais un id qu'il n'a
pas le droit de jouer.

### La réponse par défaut (à l'expiration du délai)

`reponse_par_defaut(demande)` — **déterministe** (donc rejouable) et toujours recevable :

- effet **facultatif** → **abandon** (`choix` vide) : on renonce à ce que la carte proposait ;
- `carte` / `type` / `oui_non` → la **première** option ;
- `cartes` → les `minimum` premières ; `ordre` → l'ordre identité ; `nombre` → la borne `minimum`.

## Le moteur de résolution suspendable (`demandes/moteur.py`)

`resoudre(etat, pile, registre, rng, gestionnaire)` résout la pile en LIFO **jusqu'à l'épuisement
ou jusqu'à une demande**. Points d'entrée :

- `demarrer_resolution(etat, pile, rng)` — un lot qui **déclenche** un effet (attaque, Dresseur)
  empile ses effets et appelle ceci ; la demande éventuelle se retrouve dans `etat.resolution` ;
- `repondre(etat, reponse, rng)` — applique la **réponse d'un joueur** et reprend ;
- `expirer(etat, rng)` — applique la **réponse par défaut** (délai écoulé) et reprend.

Les trois sont aussi des **coups journalisés** (`repondre_demande`, `expirer_demande`, voir
`JOURNAL.md`), donc rejouables.

### Comment la reprise peut être pure : le re-déroulé

On ne « reprend » pas une fonction Python figée en mémoire (insérialisable, perdue au premier F5).
On **re-déroule** la pile suspendue depuis le début de l'effet suspendu, le **gestionnaire**
(`demandes/gestionnaire.py`) fournissant les réponses déjà données et levant `SuspensionDemande`
sur la première décision neuve. Trois invariants rendent ce re-déroulé identique :

1. **État** — il progresse par effet ; l'effet qui se suspend voit son travail partiel **jeté** (on
   garde l'état des effets déjà terminés, pas le sien).
2. **Aléatoire** — il est **ramené en arrière** avant l'effet suspendu (`Rng.restaurer`) : à la
   reprise, ses tirages (pile ou face) retombent à l'identique — **aucun tirage compté deux fois**
   dans le journal d'anti-triche.
3. **Décisions** — chaque décision reçoit un indice global stable (`base` + compteur du
   gestionnaire → `d0`, `d1`…), donc une réponse s'apparie toujours à la bonne décision, même entre
   effets et à travers les re-déroulés.

Chaque effet terminé émet ses événements **une seule fois** (dans la passe où il aboutit). Les
**demandes imbriquées** (un effet qui, pour se résoudre, en déclenche un autre qui demande à son
tour) tombent naturellement dans le bon ordre : la pile est LIFO, les indices sont globaux.

Le moteur ne connaît **aucune horloge** (il est pur) : `expirer` applique le défaut *quand on le lui
dit* ; c'est l'extérieur (lot `j-timer`) qui tient le temps et décide *quand*. `temps_restant_ms`
vit dans l'état, donc une reprise retrouve le temps restant, pas le délai remis à neuf.

## La garde : rien d'autre qu'une réponse pendant une demande

Tant que `etat.resolution` n'est pas `None`, `journal.transitions.appliquer` **refuse toute
action** sauf `repondre_demande`, `expirer_demande` et `abandonner` (R-14.3, toujours permis). La
partie est en pause, le refus nomme la demande — jamais un repli silencieux.

## Ce que voit chaque joueur (`state/projection.py`)

Qu'une décision attende, et **de qui**, est **public** (personne ne reste devant un écran muet). Les
`options`, elles, ne vont qu'au **destinataire** — et, pour un `ensemble_cache`, sont réduites à un
**nombre** même pour lui (même frontière anti-triche que les zones cachées). La `vue` porte alors
une clé `demande`.

## Ce qui se branche ici ensuite

Le résolveur DSL **sachant se suspendre** (`resolveur_dsl_demandes`) est enregistré dans
`demandes.moteur.REGISTRE_EFFETS` : un `choisir` du langage d'effets (voir `DSL.md`) devient une
vraie demande, son `destinataire` étant par défaut le joueur qui joue l'effet. Les lots de cartes à
venir — Objets (appâts qui forcent l'échange de l'actif adverse), Supporters, talents, fenêtres de
décision, horloges — enregistreront leurs propres résolveurs et viseront l'adversaire quand la carte
le dit. Le mécanisme gère déjà un destinataire quelconque ; c'est éprouvé par les tests du moteur.
