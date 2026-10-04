# COMPILATION.md — du catalogue aux cartes jouables : le registre des scripts

> Lot `j-effets-catalogue-compilation` (jalon J2). Paquet `pbm_api.jeu.scripts` + table
> `card_scripts`. C'est le **pont** entre les trente mille cartes du catalogue et les cartes
> réellement *jouables* : il relie un **texte d'effet** (catalogue) à un **script DSL**
> (`docs/jeu/DSL.md`), gère les versions et les errata, et **refuse** une carte non scriptée à la
> construction de la partie (D9). Les règles citées (`R-x.y`) renvoient à `docs/jeu/REGLES.md`.

## Un script par texte, pas par carte

On ne scripte pas trente mille cartes : on scripte leurs **textes d'effet**. Des centaines de
cartes portent le même talent (« Fouille ») ou le même texte de Dresseur (« Piochez 2 cartes. ») ;
un seul script les couvre toutes. La clé d'une ligne de `card_scripts` est donc l'**empreinte
SHA-256 du texte d'effet normalisé** (`text_fingerprint`), jamais une carte.

**Mesuré sur le catalogue de référence (22 653 cartes, 04/10/2026)** : 19 723 cartes portent au
moins un effet ; la voie naïve (un script par couple carte+effet) demanderait **28 407** scripts,
la voie groupée n'en demande que **12 153** — soit **16 254 scripts économisés, 57,2 %**. C'est le
critère n°2 du lot, chiffré sur du réel (`scripts/scripts_effets.py mesurer`).

Le **grain** est l'effet, pas la carte : un talent et chaque attaque à effet sont des unités
scriptables distinctes (un `Programme` du DSL décrit *un* effet). `effets_scriptables(card)` lit
les mêmes champs que l'étude du langage — `abilities[].effect`, `attacks[].effect`, et le `effect`
des Dresseurs/Énergies spéciales. Une carte **sans** aucun de ces textes (Pokémon à dégâts secs,
Énergie de base) n'a aucune empreinte à exiger : rien ne la bloque côté scripts.

## La normalisation décide de ce qui « change »

`normaliser_texte` met hors du calcul les variations purement cosmétiques — forme Unicode (NFC),
espaces et retours à la ligne réduits à une espace, casse repliée. Deux textes qui ne diffèrent que
par la mise en forme sont **le même** effet (regroupement maximal). En revanche, un mot ou un
nombre qui change — une vraie **errata** — change l'empreinte. Ce choix est délibéré : un reformatage
du catalogue ne doit pas déclencher de fausse alerte d'errata, du bruit qui use la relecture.

## Les quatre états d'un script, et le refus D9

Une ligne de `card_scripts` porte un `statut` :

| statut | ce que ça veut dire | la carte qui porte ce texte |
|---|---|---|
| `scripte` | validé, tests au vert, version lisible | **jouable** |
| `a_revoir` | jamais validé, ou texte modifié depuis (errata) | **refusée**, le deck le dit |
| `non_supporte` | hors du langage v1, décision explicite (`notes` dit quoi) | **refusée**, le deck le dit |
| *(aucune ligne)* | effet jamais scripté | **refusée**, le deck le dit |

Le **chargeur** (`chargeur.refus_scripts_deck`) résout chaque carte d'un deck vers son script :
pour chaque effet, il calcule l'empreinte du texte *vivant* et cherche une ligne `scripte` lisible.
Une ligne `scripte` est en plus **rechargée par l'interprète** (`charger_programme`) avant d'être
acceptée — une version future, un `op` disparu du vocabulaire, une clé devenue invalide sont
attrapés là. Au moindre effet non résolu, la carte est **refusée, nommée** (D9 : « je ne sais pas
jouer cette carte » plutôt que la jouer de travers — jamais de repli « effet neutre »).

Ce refus est câblé dans `pbm_api.games.entry.verifier_deck`, donc il mord **à l'entrée de la file**
et **au lancement** (`verifier_lancable`), toujours **avant la mise en place** — jamais en plein
milieu d'une partie (critère n°3).

## Les errata : un texte qui change fait repasser son script « à revoir »

Le catalogue vit (correction d'import, errata officielle). Quand le texte d'une carte change, son
empreinte ne correspond plus à celle du script qui la couvrait. `errata.detecter_errata` réconcilie
le registre avec le catalogue vivant : un script `scripte` dont le texte source n'est **plus porté
par aucune carte** repasse `scripte` → `a_revoir` (il ne se joue plus tant qu'une relecture ne l'a
pas reconfirmé contre le nouveau texte). Deux garde-fous tombent alors sans rien de plus :

- la carte dont le texte a changé exige une **nouvelle** empreinte, sans script → le chargeur la
  refuse déjà (versant carte du critère n°1) ;
- on ne « rebascule » **jamais** un `a_revoir` en `scripte` automatiquement : la revalidation est un
  acte explicite (`valider`), jamais deviné (D9). La détection ne fait que **soulever** le doute.

## La commande de maintenance

`apps/api/scripts/scripts_effets.py` opère sur la base pointée par `DATABASE_URL` :

| sous-commande | ce qu'elle fait |
|---|---|
| `lister` | l'état du registre, compté par statut |
| `importer <fichier.json>` | enregistre un ou plusieurs scripts (idempotent par empreinte) |
| `valider <empreinte> --auteur X` | passe un script existant à `scripte` (refuse s'il n'a pas de programme) |
| `diffuser` | la portée de chaque script `scripte` : combien de cartes vivantes il rend jouables |
| `errata [--a-blanc]` | réconcilie le registre avec le catalogue (`--a-blanc` montre sans écrire) |
| `mesurer` | le regroupement chiffré (critère n°2), lisible sur une base en lecture seule |

`mesurer` et `diffuser` ne lisent que le catalogue : ils peuvent viser la base de référence
`pbm_catalogue_ref` de la flotte. `importer`/`valider`/`errata` exigent une base où la table
`card_scripts` existe (`alembic upgrade head`).

## Ce que ce lot ne fait pas (D9, hors périmètre nommé)

Il **n'écrit aucun script de carte réel** : ça, c'est le travail de `j-effets-assistance-ia` (l'IA
propose script + tests, une seconde IA contredit) et des lots de cartes, priorisés par **DJ2**
(cartes possédées d'abord, puis les plus fréquentes). Ce lot livre le **registre, le chargeur,
l'errata, le regroupement et l'outillage** — la mécanique dans laquelle ces scripts viendront se
ranger. Le tableau de couverture (ce qui manque pour rendre un deck jouable, et pour qui) est le
lot `j-effets-couverture-outil`, que ce registre débloque.
