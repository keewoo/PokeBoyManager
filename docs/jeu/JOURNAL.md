# Journal d'actions — `pbm_game.journal`

> Livré par le lot `j-journal-actions` (jalon J1). Le code vit dans
> `apps/game/src/pbm_game/journal/`. Cette fiche **documente le format et la mécanique**
> pour qu'une réimplémentation indépendante (replay côté client, outil de support,
> vérificateur) les reconstruise sans lire le code Python.

## Pourquoi

Principe du jalon J1 : **une partie est un état initial, une graine d'aléatoire et un
journal d'actions numéroté.** Ce n'est pas une photo du plateau — c'est la suite des
coups. Rejouer le journal redonne *exactement* le même état. Cette seule propriété rend
possibles quatre choses d'un coup :

- la **reprise après un F5** (on rejoue le journal) ;
- le **replay** d'une partie coup par coup ;
- le **support** (« montre-moi la partie ») ;
- l'**anti-triche** (le journal, recalculé, ne peut pas mentir).

Le piège que ce lot évite : **journaliser l'état plutôt que les actions**. Le fichier
gonfle, la divergence ne se voit plus, et le replay ment. On enregistre ce qui a été
**DEMANDÉ** (l'action) et ce que le moteur en a **FAIT** (les événements), jamais une
photo du plateau. L'état n'est qu'un **cache** reconstructible.

## Ce qui est enregistré

Une **partie** (`Partie`) persistée, c'est trois choses :

| Champ | Quoi |
|---|---|
| `etat_initial` | l'état au coup 0 (voir `docs/jeu/ETAT.md`) |
| `graine` | la graine d'aléatoire en hexadécimal (voir `docs/jeu/ALEATOIRE.md`) |
| `entrees` | le journal, liste numérotée d'`Entree` |

Le moteur est **pur** : il ne tire pas la graine (l'appelant le fait, `os.urandom(32)`
côté serveur) et n'appelle **aucune horloge** (l'horodatage est fourni par l'appelant).

Une **entrée** (`Entree`) est numérotée (0-based, suite sans trou) et autosuffisante :

| Champ | Quoi |
|---|---|
| `numero` | rang dans le journal (0, 1, 2, …) |
| `auteur` | l'identifiant du joueur, ou `systeme` (`AUTEUR_SYSTEME`) |
| `action` | ce qui a été demandé : `{type, auteur, params}` |
| `evenements` | ce que le moteur en a fait : liste de `{type, donnees}` |
| `horodatage` | chaîne ISO fournie par l'appelant (donnée d'entrée, pas recalculée au rejeu) |
| `empreinte` | l'empreinte de l'état **après** ce coup (voir plus bas) |

## L'empreinte — la divergence au coup près

`empreinte(etat)` = `SHA-256` hexadécimal d'une forme JSON **canonique** de l'état :
`json.dumps(vers_json(etat), sort_keys=True, ensure_ascii=False, separators=(",", ":"))`.
La sérialisation de l'état est déjà déterministe (ensembles triés) ; les clés triées et
les séparateurs compacts achèvent la canonicalisation. Deux états égaux ⇒ même empreinte ;
deux états différents ⇒ empreintes différentes.

Chaque entrée porte l'empreinte de l'état résultant. Au rejeu, on recalcule l'état coup
par coup et on compare : une divergence lève `RejeuDivergent` **sur le coup fautif**, pas
à la fin de la partie. L'empreinte porte sur l'**état de jeu** seul ; une divergence
d'aléatoire se voit, elle, dans le journal de tirages du `Rng` et son vérificateur
commit-reveal. Les deux contrôles sont complémentaires.

## Appliquer une action

`appliquer(etat, action, rng) -> (nouvel_etat, evenements)` est **pur côté état** :
`etat` est figé, un nouvel état est renvoyé. Le seul collaborateur mutable est le `Rng`
(ses compteurs avancent, son journal de tirages s'allonge) — mutation **rejouable** par
conception, donc sans danger pour la reproductibilité.

**D9 — un effet non implémenté n'est jamais approximé.** Un `action.type` absent du
registre est **refusé** (`ValueError`), jamais deviné. Une transition refuse aussi une
demande mécaniquement impossible (piocher plus que la pioche n'a) plutôt que de la replier
en silence.

### Transitions livrées par ce lot

Ce lot livre l'**ossature** du journal et un noyau de transitions **entièrement
mécaniques** — elles ne demandent aucune donnée de carte (type, coût, effet) et sont donc
pleinement implémentables et testables ici. Les actions riches (attacher une énergie,
poser un Pokémon, faire évoluer, attaquer, jouer un Dresseur) arrivent avec les lots de
résolution qui disposent du catalogue ; elles s'enregistrent dans le **même** registre.

| `action.type` | Règle | Effet | Événements |
|---|---|---|---|
| `melanger_pioche` | R-4.1 | mélange la pioche du joueur cible via son flux d'aléatoire dédié | `pioche_melangee` |
| `piocher` | R-5.2, R-4.1 | déplace `params.nombre` (défaut 1) cartes du **sommet** (`pioche[0]`) vers la main | `cartes_piochees` |
| `avancer_phase` | R-5.1, R-12.1 | `pioche → principale → attaque → checkup` ; depuis `checkup`, ouvre le tour suivant (numéro + 1, joueur adverse, drapeaux remis, phase `pioche`) | `phase_avancee` (+ `tour_commence` au changement de tour) |

Le joueur cible d'une action est `params.joueur` s'il est donné, sinon `action.auteur` ;
une action système sans joueur cible est refusée (jamais de joueur deviné).

## Rejeu et compaction

- `rejouer(partie) -> (etat_final, rng_final)` : repart de l'état initial sous la graine,
  applique chaque action, vérifie l'empreinte **et** les événements de chaque coup. Lève
  `RejeuDivergent(numero, quoi, attendu, obtenu)` au premier écart.
- `compacter(partie, jusqu_a) -> Instantane` : rejoue les `jusqu_a` premiers coups et fige
  un **instantané** `{numero_entrees, etat, rng_etat, empreinte}`. Reprendre une partie de
  400 coups ne doit pas coûter 400 applications.
- `reprendre_partie(partie, instantane) -> (etat, rng)` : repart de l'instantané et ne
  rejoue que la **queue** (`entrees[numero_entrees:]`). Le résultat est, par construction,
  identique au rejeu complet. L'instantané est un **cache** : on ne le croit pas sur
  parole — sa cohérence (empreinte contre état) est revérifiée d'abord.

## Format sérialisé — versionné

`JOURNAL_VERSION = 1`. Toute évolution incompatible de la forme (champ d'une entrée, forme
d'une action/événement/instantané) l'incrémente. `partie_depuis_json` / `instantane_depuis_json`
**refusent** une `journal_version` inconnue (`ValueError`) : un journal d'une version
future ne se relit pas « au mieux », il se refuse. Round-trip garanti :
`partie_depuis_json(partie_vers_json(p)) == p`.

```json
{
  "journal_version": 1,
  "etat_initial": { "...": "voir docs/jeu/ETAT.md" },
  "graine": "00112233…",
  "entrees": [
    {
      "numero": 0,
      "auteur": "alice",
      "action": {"type": "piocher", "auteur": "alice", "params": {"nombre": 7}},
      "evenements": [
        {"type": "cartes_piochees",
         "donnees": {"joueur": "alice", "nombre": 7, "instance_ids": ["c-1", "c-2", "…"]}}
      ],
      "horodatage": "2026-10-01T12:00:00Z",
      "empreinte": "9f86d081…"
    }
  ]
}
```

## Vue de débogage — lisible sans outil

`decrire_entree(entree, noms)` rend une entrée lisible par un humain, les identifiants de
cartes résolus en **noms**. Le moteur ne connaît pas le catalogue (il est pur) : la table
`noms` (`instance_id -> nom`) est fournie par l'appelant. Un identifiant **absent** de la
table n'est pas masqué (pas de repli silencieux) : il est rendu `«id» (nom inconnu)`, pour
qu'un trou se voie au lieu de se confondre avec une carte nommée.

```
#0 [2026-10-01T12:00:00Z] alice · piocher({'nombre': 1}) → alice pioche 1 : Dracaufeu [c-7]
```

## Ce que le lot ne fait pas

- Il ne **génère pas** les actions légales ni ne valide la légalité d'un coup au sens des
  règles (c'est `j-actions-legales`) : une transition n'enforce que ses préconditions
  mécaniques.
- Il ne **persiste pas** (ni HTTP, ni base) : c'est `j-partie-service`.
- Il ne **résout pas** les effets de cartes (attaques, Dresseurs, talents) : chaque lot de
  résolution ajoute ses transitions au registre, scriptées et testées.
