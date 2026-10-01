# ETAT.md — Le modèle d'état d'une partie (`pbm_game.state`)

> Fiche durable du lot `j-modele-etat`. Décrit la **forme** de l'état d'une partie et les
> choix qui la structurent. Les règles qu'elle respecte font foi dans
> [`REGLES.md`](REGLES.md) (`R-x.y`) ; le code vit dans `apps/game/src/pbm_game/state/`.

## Principe

L'état d'une partie est un objet **pur et sérialisable** : des dataclasses **figées**
(`frozen=True`), sans aucune méthode de mutation. Le moteur ne connaît ni HTTP, ni base,
ni React. Toute transformation de l'état passera par une **action journalisée** (lots
suivants) — jamais par une méthode pratique posée sur l'état, sinon la rejouabilité est
perdue au premier raccourci.

## Les structures (`modele.py`)

| Dataclass | Porte |
|---|---|
| `Carte` | un exemplaire : `instance_id` (l'exemplaire, unique dans la partie) + `ref` (ce que la carte **est**, référence catalogue) |
| `PokemonEnJeu` | pile d'évolutions (`cartes`, bas→haut), `energies`, `outil` (≤ 1, R-3.7), `compteurs_degats` (en **compteurs**, jamais en PV — R-10.4), `etats_speciaux` (R-11) |
| `Joueur` | `id`, `pioche`, `main`, `actif`, `banc` (≤ 5), `defausse`, `recompenses` (6, face cachée), `zone_perdue` |
| `Tour` | `joueur_actif`, `numero`, `phase`, drapeaux `energie_posee` / `supporter_joue` / `retraite_faite` (R-5.4/5/6) |
| `EtatPartie` | `joueurs` (2), `tour`, `schema_version`, `stade` (unique, partagé — R-3.5) + `stade_proprietaire`, `terminee` / `vainqueur` / `raison_fin` (R-14.6) |

**L'orientation n'est pas stockée** : elle **dérive** de l'état d'orientation présent
(`orientation(pokemon)` → endormi / confus / paralysé / normale), pour qu'elle ne puisse
jamais désynchroniser. Un seul état d'orientation à la fois (R-11.8) ; les marqueurs
(brûlé, empoisonné) se cumulent entre eux et avec l'orientation.

## Information publique vs cachée — la frontière anti-triche

**Le serveur fait autorité.** `vue(etat, joueur)` (`projection.py`) produit ce qu'un
joueur a le **droit** de savoir — l'information cachée est **retirée**, pas masquée après
coup :

| Zone | Pour soi | Pour l'adversaire |
|---|---|---|
| main | identités | **nombre seulement** |
| pioche | **nombre seulement** (jamais l'ordre) | **nombre seulement** |
| récompenses | **nombre seulement** (face cachée) | **nombre seulement** |
| défausse, zone perdue | publiques | publiques |
| Actif, banc, Stade | publics | publics |

L'ordre de la pioche n'est exposé à **personne**, pas même à son propriétaire. Une zone
cachée devient un simple entier : aucun `instance_id` ni `ref` caché ne survit dans la
structure produite — garanti par un test qui parcourt la vue à la recherche de ces
identifiants sur des centaines d'états aléatoires.

## Sérialisation (`serialisation.py`)

`vers_json` / `depuis_json` : round-trip **exact** (`depuis_json(vers_json(e)) == e`) et
sortie **déterministe** (les ensembles d'états sont triés) — deux états égaux produisent
le même JSON, socle du replay et de la comparaison. `depuis_json` **refuse bruyamment**
une structure malformée ou une `schema_version` inconnue (jamais de repli silencieux).

## Invariants (`invariants.py`)

`verifier(etat) -> list[str]` renvoie les violations (vide = sain) ; `assert_invariants`
lève `InvariantViole`. Contrôlés : deux joueurs distincts ; banc ≤ 5 (R-3.2) ; 1 Actif
tant qu'un Pokémon est en jeu (R-3.3) ; ≤ 6 récompenses (R-3.4) ; **aucune carte dans deux
zones** (chaque `instance_id` une seule fois) ; total par joueur constant si l'attendu est
fourni (R-2.1) ; un seul état d'orientation (R-11.8) ; états ∈ les cinq connus (R-11.1) ;
compteurs ≥ 0 (R-10.4) ; tour cohérent (R-5). La suite de tests du moteur appelle
`assert_invariants` après chaque action.

## Ce qui est volontairement absent

Pas de logique de jeu ici (piocher, attaquer, résoudre) : ce lot ne livre que la **forme**.
L'aléatoire reproductible (`j-aleatoire-determinisme`), le journal d'actions
(`j-journal-actions`) et la résolution viennent ensuite et consomment cet objet.
