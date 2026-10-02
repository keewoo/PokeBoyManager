# DSL.md — le langage d'effets du moteur de jeu

> Lot `j-effets-dsl` (jalon J2). Paquet `pbm_game.effets.dsl`, **pur** (aucune E/S), comme tout
> le moteur. Ce langage décrit **ce qu'une carte fait**, en données, sans écrire de code par
> carte. Il se pose **au-dessus de la pile d'effets** (`docs/jeu/EFFETS.md`). Les règles citées
> (`R-x.y`) renvoient à `docs/jeu/REGLES.md`.

## Pourquoi un langage, et pas une fonction par carte

Dix mille cartes ne s'écrivent pas en dix mille fonctions Python : on ne les relirait pas, on ne
les testerait pas en masse, et une IA ne pourrait pas en écrire sous contrôle. Un **script
d'effet** est une **donnée** — une version et une liste d'instructions — validée par un schéma,
sérialisable, rejouable.

**Il n'existe aucune primitive « code libre ».** C'est le piège central que la fiche du lot
nomme : la primitive fourre-tout qui exécute du code arbitraire apparaît au bout de trois jours,
et à partir de là plus rien n'est vérifiable ni générable. Une carte qui ne s'exprime pas avec le
**vocabulaire fermé** (`vocabulaire.py`) est déclarée **non supportée** à la construction du deck,
en disant pourquoi (D9) — jamais jouée de travers.

## D'où vient le vocabulaire : 500 textes réels

Le vocabulaire a été dégagé d'un **dépouillement de 500 textes d'effet** pris au catalogue
(`apps/game/tools/extraire_effets_dsl.sql` extrait, `classer_dsl.py` classe, gel dans
`apps/game/tests/donnees/echantillon_500_dsl.json`). Le test `test_dsl_couverture` **mord** en CI
si la couverture tombe sous 80 %.

**Résultat mesuré : 94,8 % des 500 textes** sont exprimables avec les primitives ci-dessous, sans
primitive « code libre ». Les 26 textes restants sont réellement exotiques (énergies spéciales à
fourniture conditionnelle, « votre tour ne se termine pas », dés-évolution, modificateurs de
Faiblesse/Résistance) : honnêtement hors v1, listés dans le fichier gelé plutôt que masqués.

> Ce que la mesure dit : le langage **a des mots** pour 94,8 % des effets réels. Ce qu'elle ne dit
> pas : que chaque carte est scriptée fidèlement — ça, c'est le travail des lots de cartes, carte
> par carte, test par test (D9).

## La forme d'un script

```json
{
  "version": 1,
  "cout":   [ <instruction>, … ],
  "effets": [ <instruction>, … ]
}
```

- `version` (**obligatoire**) : la version du langage. L'interprète lit `1 … DSL_VERSION` ; une
  version **future** est refusée (jamais chargée « au mieux »). Un script v1 reste lisible quand la
  v2 sort (critère d'acceptation n°4).
- `cout` (facultatif) : des instructions **payées d'abord, atomiquement**. Si le coût ne peut pas
  être payé (p. ex. défausser 2 cartes quand il n'y en a qu'une), le script ne fait **rien** et le
  dit (`dsl_cout_impayable`) — jamais un demi-effet gratuit.
- `effets` (**obligatoire**) : la séquence d'instructions du corps.

Le chargement passe par `charger_programme(dict) -> Programme`, **seule** porte d'entrée. Un script
non conforme est refusé **là** (`ProgrammeInvalide`), pas en pleine partie (critère n°3). Le
validateur est **strict** : une clé inconnue est une erreur, jamais ignorée en silence.

Le **schéma JSON** formel (Draft 2020-12) est `src/pbm_game/effets/dsl/schema.json` ; un test
(`test_dsl_schema_json`) garantit qu'il rend le **même verdict** que le validateur Python sur une
batterie de scripts — on ne tient pas deux spécifications qui divergent.

## Une instruction

Une instruction est un objet `{"op": "<nom>", …}`. L'`op` est une **primitive** ou une
**structure de contrôle**. Les champs non pertinents pour un `op` restent absents (le chargement
refuse ceux qui n'ont pas de sens).

| champ | pour | sens |
|---|---|---|
| `cible` | la plupart | le sélecteur principal (destination pour `attacher`/`deplacer`) |
| `source` | `attacher`, `deplacer`, `repeter` | l'origine (ou le compteur « pour chaque ») |
| `nombre` | `piocher`, `poser_compteurs`, `infliger_degats`, `pile_ou_face`, `repeter`, … | un entier |
| `etat` | `poser_etat`, `retirer_etat` | un des cinq états spéciaux (R-11.1) |
| `verrou` / `portee` | `empecher` | nom et portée du verrou (cf. `EFFETS.md`) |
| `condition` | `si` | le test |
| `alors` / `sinon` | `si`, `pile_ou_face`, `choisir` | les branches / le corps |
| `regle` | toutes | l'identifiant `R-x.y` servi (journal) |

## Le sélecteur — *quelles* cartes

```json
{"zone": "banc", "proprietaire": "moi", "categorie": "pokemon", "stade": "base",
 "nombre": 1, "position": "au_choix"}
```

- `zone` : `actif`, `banc`, `en_jeu` (actif + banc), `main`, `pioche`, `defausse`, `recompenses`,
  `zone_perdue`, `stade`.
- `proprietaire` : `moi`, `adversaire`, `les_deux` (relatif au joueur qui joue l'effet).
- `categorie` : `pokemon`, `energie`, `dresseur`, `outil` (facultatif).
- `stade` : `base`, `stade1`, `stade2` (facultatif).
- `nombre` : combien en prendre (absent = **toutes** celles qui correspondent).
- `position` : dans une zone **ordonnée**, d'où prendre — `dessus`, `dessous`, `au_choix`.

Les filtres `categorie`/`stade` lisent les **métadonnées de catalogue** fournies par le contexte
(`ref → {categorie, stade, type}`) : l'état d'une partie ne connaît qu'`instance_id` et `ref` — le
reste vit au catalogue (D9). Une `ref` sans métadonnée n'est **pas** retenue par un filtre (jamais
devinée).

« Un Pokémon de base dans ma pioche » :
`{"zone": "pioche", "proprietaire": "moi", "categorie": "pokemon", "stade": "base", "nombre": 1}`.
« Une carte Objet de ma défausse » :
`{"zone": "defausse", "proprietaire": "moi", "categorie": "dresseur", "nombre": 1}`.

## Les primitives

Chaque primitive a sa fonction pure (`primitives.py`) et son test (positif + « aucune cible »).
Le cas **aucune cible** est traité partout : la primitive ne bloque pas la partie, elle émet
`effet_sans_cible` en nommant la raison (critère n°2). Dégâts (R-10.4/R-10.6, cf. `DEGATS.md`) :
`compteurs_degats` compte en PV ; `poser_compteurs`/`soigner` comptent en **marqueurs**
(1 = 10 PV) ; `infliger_degats` compte en **dégâts** (PV, multiple de 10).

| `op` | ce qu'elle fait | champs | exemple de carte réelle |
|---|---|---|---|
| `piocher` | pioche N cartes du sommet vers la main (R-5.2) | `nombre` | *Dedenne* (« piochez des cartes… ») |
| `chercher` | déplace les cartes trouvées (deck/défausse) vers la main | `cible` | *Poké Ball*, *Recherche d'énergie* |
| `defausser` | défausse les cartes désignées | `cible` | coûts de nombreux Objets |
| `attacher` | attache une Énergie/Outil de la source à un Pokémon | `source`, `cible` | *Défenseur* (Outil), énergies |
| `deplacer` | déplace N énergies d'un Pokémon à un autre | `source`, `cible`, `nombre` | *Transfert d'Énergie* |
| `soigner` | retire des marqueurs (ou tout), plancher 0 | `cible`, `nombre?` | *Potion*, *Pleine Santé* |
| `poser_compteurs` | place N marqueurs directs (R-10.6) | `cible`, `nombre` | *Polichombr*, *Funécire* |
| `infliger_degats` | dégâts d'effet directs (R-10.6) | `cible`, `nombre` | « inflige 20 dégâts à… » |
| `melanger` | mélange une zone (R-4.1) | `cible?` (défaut pioche) | « mélangez votre deck » |
| `reveler` | rend des cartes publiques (journal) | `cible` | « montrez-la à votre adversaire » |
| `regarder` | regarde des cartes cachées (info **privée** : refs non journalisées) | `cible`, `nombre?` | « regardez les 5 du dessus » |
| `choisir` | point de décision : retient N options, son `alors` agit sur elles | `cible`, `nombre?`, `alors` | « choisissez 1 de vos Pokémon… » |
| `pile_ou_face` | lance N pièces ; `alors` par face, `sinon` si zéro face | `nombre?`, `alors`, `sinon?` | « lancez une pièce. Si c'est face… » |
| `changer_actif` | échange forcé Actif ↔ banc (R-8.8) | `cible` (banc) | *Écaïd*, *Furaiglon* |
| `poser_etat` | pose un état spécial (un seul d'orientation, R-11.8) | `cible`, `etat` | « l'Actif est maintenant Empoisonné » |
| `retirer_etat` | retire un état, ou tous | `cible`, `etat?` | « n'est plus Confus » |
| `empecher` | pose un **verrou** nommé (cf. `EFFETS.md`) | `verrou`, `portee`, `cible?` | « pas de Supporter ce tour » |
| `annuler` | lève le drapeau « dégâts annulés » que la résolution lit | — | « prévenez tous les dégâts » |

## Les structures de contrôle

- **`si`** — `{"op": "si", "condition": {…}, "alors": [...], "sinon": [...]}`.
- **`repeter`** — `{"op": "repeter", "nombre": 3, "alors": [...]}` (N fois) ou
  `{"op": "repeter", "source": {…}, "alors": [...]}` (**une fois par candidat** de la source —
  « pour chaque Pokémon de banc… »).
- **`choisir`** — sélectionne `nombre` options parmi `cible` (défaut 1) et exécute `alors` **sur
  les choisis** : dans le corps, une instruction sans `cible` agit sur la sélection.
- **`pile_ou_face`** — lance `nombre` pièces (défaut 1) ; `alors` s'exécute **une fois par face**,
  `sinon` une fois si **zéro** face. Pour une seule pièce, c'est exactement « si face … sinon … ».

### Les conditions (`si`, et les coûts)

- `resultat_pile` : le dernier pile ou face est tombé sur `attendu` (`face`/`pile`).
- `zone_non_vide` : le sélecteur `cible` trouve au moins une carte/Pokémon.
- `a_etat` : un Pokémon de `cible` porte `etat`.
- `a_degats` : un Pokémon de `cible` porte au moins `minimum` marqueurs.

## Le choix d'un joueur : une stratégie injectable

`choisir` (et toute position `au_choix`) passe par une **stratégie** injectée — une fonction pure
qui, parmi des candidats, en retient N. Par défaut, `strategie_canonique` est **déterministe**
(donc rejouable et testable **dès maintenant**). Ce n'est **pas** une approximation d'effet (D9) :
la primitive `choisir` est bel et bien implémentée ; c'est la *politique* de décision qui est
branchable. Le lot `j-effets-choix` remplacera le défaut par une vraie demande de décision
(suspension de la pile) ; le lot `j-simulation-bots` injectera une stratégie de bot.

## Le pont vers la pile d'effets

`compiler_en_effet(programme, ctx, libelle=…, regle=…)` emballe un script en
`EffetEnAttente` de type `dsl` ; `resolveur_dsl` le résout, et `registre_dsl()` donne le registre
à fusionner avec celui d'un lot de cartes. Un script devient alors un effet comme un autre :
journalisé avec sa source (`effet_resolu`), résolu en LIFO, et un jour **suspendable** (script et
contexte sont sérialisables). `executer_programme(...)` rend en plus les **verrous** posés — un
script qui pose un verrou s'exécute par cette voie, le temps que le `JeuDeVerrous` rejoigne l'état
(hors de ce lot).

## Exemples complets

**Poké Ball** — « Lancez une pièce. Si c'est face, cherchez un Pokémon dans votre deck, montrez-le,
puis ajoutez-le à votre main. Mélangez. »

```json
{"version": 1, "effets": [
  {"op": "pile_ou_face", "nombre": 1, "regle": "R-5.2", "alors": [
    {"op": "chercher", "cible": {"zone": "pioche", "proprietaire": "moi",
                                  "categorie": "pokemon", "nombre": 1}},
    {"op": "melanger", "cible": {"zone": "pioche", "proprietaire": "moi"}}
  ]}
]}
```

**Potion** — « Soignez 30 dégâts (3 marqueurs) d'un de vos Pokémon. »

```json
{"version": 1, "effets": [
  {"op": "choisir", "cible": {"zone": "en_jeu", "proprietaire": "moi", "nombre": 1},
   "alors": [{"op": "soigner", "nombre": 3, "regle": "R-10.4"}]}
]}
```

**Un effet d'attaque à coût** — « Défaussez 1 Énergie de ce Pokémon. Infligez 20 dégâts à
chacun des Pokémon de banc adverses. »

```json
{"version": 1,
 "cout": [{"op": "deplacer", "nombre": 1,
           "source": {"zone": "actif", "proprietaire": "moi"},
           "cible": {"zone": "defausse", "proprietaire": "moi"}}],
 "effets": [{"op": "repeter", "source": {"zone": "banc", "proprietaire": "adversaire"},
             "alors": [{"op": "infliger_degats",
                        "cible": {"zone": "banc", "proprietaire": "adversaire"},
                        "nombre": 20, "regle": "R-10.6"}]}]}
```

## Ce qui vient après

- `j-cartes-attaques-effets` — câble les scripts d'attaque entre `avant_degats` et `apres_degats`.
- `j-effets-choix` — remplace la stratégie déterministe par une vraie demande de décision.
- `j-effets-catalogue-compilation` — compile le texte du catalogue en scripts, versionnés + errata.
- `j-simulation-bots` — injecte des stratégies de bot pour jouer des milliers de parties.
