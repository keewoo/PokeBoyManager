# COUVERTURE.md — ce qui est jouable, ce qui manque, et pour qui

> Lot `j-effets-couverture-outil` (jalon J2). Prolonge `COMPILATION.md` (le registre `card_scripts`,
> le chargeur, le regroupement) : là où la compilation dit *comment* une carte devient jouable, la
> couverture dit *combien* le sont déjà, *pour qui*, et *quoi scripter ensuite*. Code :
> `pbm_api.jeu.scripts.couverture` (cœur **pur** + adaptateur base) et `pbm_api.jeu.scripts.demandes`
> (la file de demandes). À ne pas confondre avec `DEMANDES.md`, qui décrit les *demandes de décision*
> du moteur en pleine partie — un tout autre objet.

## La règle qui gouverne tout : on mesure les collections réelles

Une couverture calculée sur les trente mille cartes du catalogue — dont 99 % que personne ne possède
— donne un chiffre flatteur et inutile. L'**univers mesuré** est donc volontairement réduit : les
cartes **possédées par un joueur du jeu** (compte `game_access`) ou **présentes dans l'un de leurs
decks**. Rien d'autre. Un compte sans `game_access` n'y entre pas (ce n'est pas un joueur du jeu).
Quand cet univers est vide, le rapport le **dit** (`univers_vide`) au lieu d'afficher un `0 %`
trompeur : il n'a alors aucune collection réelle à mesurer.

## Deux grains de lecture

- au grain de l'**effet** (texte distinct) — combien de textes d'effet sont `scripté`, et combien
  restent (`non_supporté`, `à revoir`, ou jamais écrit = `absent`). C'est la mesure du *chantier* ;
- au grain de la **carte** — une carte n'est jouable que si **tous** ses effets le sont (porte D9).
  Le `pct` d'une couverture carte se calcule sur les cartes **porteuses d'effet**, jamais sur le
  total : une extension pleine de Pokémon à dégâts secs afficherait sinon 100 % sans un seul script.

Le cœur (`couverture.py`) est **pur** : il reçoit des `CarteCouverture` (identité + empreintes
d'effet) et un registre `empreinte → statut`, et rend des agrégats. Le choix de l'univers vit dans
l'**adaptateur** `charger_couverture(db)`, seul à lire la base — jamais éparpillé.

## Ce que le rapport porte (`RapportCouverture`)

| Section | Ce qu'elle dit |
|---|---|
| global (effets + cartes) | l'état du chantier sur tout l'univers |
| **par collection de joueur** | le chiffre que le joueur sent : ce qu'il possède, ce qu'il peut jouer |
| par famille d'effet | couverture par origine (`talent` / `attaque` / `dresseur`) |
| par extension | triée **de la moins couverte à la mieux** — là où scripter paie le plus |
| cartes qui bloquent le plus | classées par **decks bloqués** puis **joueurs concernés** (mission n°2) |
| file de demandes | ce que les joueurs réclament (voir plus bas) |

La « page d'administration » est la **CLI** `python -m pbm_api.jeu.scripts.couverture` (`--json`
pour un pilotage machine). Choix délibéré : le détail **par collection** est une donnée
d'exploitation — un joueur ne doit pas voir la collection d'un autre. L'exposer en HTTP exigerait un
rôle d'administration qui n'existe pas encore, et risquerait cette fuite ; la CLI sur le serveur est
la surface correcte. Un lot de scripts lit ce rapport pour diriger son effort.

## La file de demandes « je voudrais jouer cette carte »

Table `card_play_requests` (`models/card_play_requests.py`) : une ligne par **(joueur, carte)**,
unique — re-signaler ne crée pas de doublon, le compte de demandeurs distincts reste honnête. Statut
`en_attente` / `scriptee` / `refusee`, posé par l'exploitation quand un lot traite la carte.

La **progression** vue par le joueur se lit en deux temps : le `statut` stocké (l'intention) **et**
la `jouable_maintenant` recalculée à la lecture contre le registre `card_scripts` (le fait) — une
carte peut être devenue jouable sans qu'on ait repassé son statut à la main.

- Côté joueur (HTTP, borné à `user_id`) : `POST /me/demandes-cartes` (signaler), `GET
  /me/demandes-cartes` (suivre), `DELETE /me/demandes-cartes/{card_id}`. Jamais les demandes d'un
  autre. Service `jeu/scripts/demandes.py`.
- Côté exploitation : `demandes.file_agregee(db)` agrège par carte (demandeurs distincts), reprise
  dans le rapport de couverture — **c'est là qu'un lot de scripts lit la file** (critère n°3).

## Le branchement dans la légalité du deck (critère n°1)

`decks.legality.evaluate` reste **pur** : il reçoit désormais `unsupported={card_id: raison}` déjà
résolu par le service (`decks/service.py`, via `jeu/scripts/chargeur.refus_scripts_par_carte`) et émet
un constat `unsupported_effect` **bloquant** pour les cartes à effet non scripté — mais seulement pour
les cartes **présentes dans le deck jugé** (la carte d'un autre deck ne fuit pas). Chaque constat porte
désormais une **catégorie** (`possession` / `legalite` / `script`) : le constructeur peut ainsi dire,
pour chaque carte refusée, **ce qui** la bloque. Côté écran, la carte porte un badge « Effet non géré »
et un bouton « Je voudrais jouer cette carte » qui alimente la file.

## Où regarder dans le code

| Fichier | Rôle |
|---|---|
| `apps/api/src/pbm_api/jeu/scripts/couverture.py` | cœur pur + adaptateur base + CLI |
| `apps/api/src/pbm_api/jeu/scripts/demandes.py` | file de demandes (base) |
| `apps/api/src/pbm_api/jeu/scripts/chargeur.py` | `refus_scripts_par_carte` (card_id → raison) |
| `apps/api/src/pbm_api/decks/legality.py` | catégorie des constats + `unsupported` |
| `apps/api/src/pbm_api/routers/jeu_demandes.py` | `/me/demandes-cartes` |
| `apps/api/src/pbm_api/models/card_play_requests.py` | table `card_play_requests` |
| `apps/web/src/lib/game/legality.ts` + deck-builder-view | badge/catégorie + bouton de demande |
