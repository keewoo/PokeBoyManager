# CAS-EXECUTABLES.md — la batterie de cas de règles du moteur

> **Un moteur de règles se prouve, il ne se relit pas.** Cette batterie est ce qui permet de
> modifier le moteur `pbm_game` dans six mois sans tout casser en silence. Un cas est une **donnée**
> — un état de départ, une action (ou un appel de fonction), un résultat attendu, et la règle
> `R-x.y` qu'il vérifie — qu'un humain qui connaît les règles (`docs/jeu/REGLES.md`) lit et écrit
> **sans toucher au code du moteur**. L'exécuteur est le seul code ; les cas sont des données.

## Où ça vit

| | |
|---|---|
| Les cas | `docs/jeu/cas-executables/*.yaml` (un fichier par mécanique) |
| L'exécuteur (pur) | `apps/game/src/pbm_game/cas/` — `construire`, `executer`, couverture |
| Le test qui les exécute | `apps/game/tests/test_cas_executables.py` (≥ 200 cas, tous verts en CI) |
| La garde de couverture | `apps/game/tests/test_couverture_regles.py` |
| Les exceptions justifiées | `docs/jeu/couverture-exceptions.yaml` |
| La table **documentaire** (couverture, sans exécution) | `docs/jeu/cas-de-regles.yaml` |

Au 01/10/2026 : **210 cas exécutables**, **100 règles** du corpus couvertes par un vrai cas
exécutable ; les autres sont couvertes par la table documentaire ou par une exception écrite. La
CI (job `game`) échoue si un cas rougit **ou** si une règle n'a aucun cas ni exception.

## Anatomie d'un cas

Tout cas porte : `id` (kebab-case, unique), `regles` (≥ 1 identifiant `R-x.y` défini dans
`REGLES.md`), `description` (une phrase), et `op` (l'opération). Puis les champs propres à `op`.
Un cas attend **soit** un résultat (`attendu`), **soit** une erreur (`erreur` : une sous-chaîne,
en général le `R-x.y`, qui doit apparaître dans le message `ValueError` — c'est ce qui prouve
qu'une règle **mord**).

### `op: appliquer` — une ou des actions journalisées contre le moteur

```yaml
- id: abandon-defaite-immediate
  regles: [R-14.3, R-16.5]
  op: appliquer
  description: "Abandonner fait perdre immédiatement ; l'adversaire gagne."
  etat:                              # construit par pbm_game.cas.construire (voir plus bas)
    alice: {actif: {}}
    bob: {actif: {}}
    tour: {joueur: alice, phase: principale, numero: 3}
  tirages:                           # (facultatif) fixe les pile ou face voulus
    - {flux: "confusion:alice", resultat: pile}
  action: {type: abandonner, auteur: alice}   # ou `actions: [...]` pour une séquence
  attendu:
    etat: {terminee: true, vainqueur: bob, raison_fin: abandon}
    evenements: [{type: partie_terminee, donnees: {vainqueur: bob}}]
```

- `action` (un coup) **ou** `actions` (une liste jouée à la suite, sur le même état/Rng).
- `attendu.etat` — assertions **partielles** (on ne vérifie que ce qu'on nomme) : `terminee`,
  `vainqueur`, `raison_fin`, `tour` (`phase`/`numero`/`joueur_actif`/les trois drapeaux/`entres`),
  et, par **joueur** : `actif` (`degats`/`etats`/`energies`/`cartes`/`outil`/`present`),
  `actif_present`, `banc` (un nombre, **ou** une liste d'assertions par Pokémon de banc),
  `main`/`pioche`/`defausse`/`recompenses`/`zone_perdue` (des nombres).
- `attendu.evenements` — chaque événement attendu doit exister dans l'ordre (sous-séquence) ; son
  `donnees` est une correspondance partielle. On ne contraint pas les événements produits en trop.
- `erreur` — à la place de `attendu` : l'action doit lever une `ValueError` citant cette chaîne.
- Pour l'action système `checkup`, les **fiches** (PV/récompenses) sont injectées automatiquement
  depuis l'état (on ne les réécrit pas à la main).

### Les autres opérations (appels de fonction purs)

| `op` | Ce qu'elle rejoue | Champs |
|---|---|---|
| `degats` | `resoudre_degats` (ordre strict R-10) | `args` (`base`, `type_attaque`, `faiblesse`, `resistance`, `modificateurs_*`, `au_banc`) → `attendu` (`degats`/`compteurs`/`detail`/`arrete_avant_degats`) ou `erreur` |
| `compteurs` | `poser_compteurs` / `poser_degats` (R-10.4/R-10.6) | `pokemon`, `poser_compteurs`/`poser_degats` → `attendu.degats` ou `erreur` |
| `etat` | matrice de cumul, orientation, guérison (R-11) | `pokemon`, `poser` (liste), `soigner` → `attendu` (`etats`/`orientation`/`bloquant`) ou `erreur` |
| `recompenses` | `recompenses_pour_marqueur` (R-13.3) | `marqueur` → `attendu` (entier) ou `erreur` |
| `cout` | `cout_satisfait` (R-9.2) | `cout` (`types`/`incolore`), `fournitures` → `attendu` (`accepte`/`regle`) ou `erreur` |
| `legalite` | `valider` / `actions_legales` | `etat` + (`action` → `attendu.accepte`/`regle`) ou (`joueur` → `attendu.types`) |
| `invariants` | `verifier` (R-3) | `etat` → `attendu.saines` ou `attendu.violation_contient` |
| `rng` | reproductibilité + vérifiabilité d'un tirage (R-4.7) | `tirages` (liste de `{flux, resultat}`) |

## Décrire un état concis (`construire`)

Le constructeur fabrique un `EtatPartie` réel depuis une description lisible. Un **Pokémon** :
`{cartes: N (pile, défaut 1), degats: N, etats: [...], energies: N, outil: true, pv: N, recompenses: N | marqueur: "ex"}`.
`pv` + (`recompenses` | `marqueur`) alimentent la table **fiches** (catalogue, D9) indexée sur la
carte au sommet. Un **joueur** : `{actif: <pokemon> | null, banc: N | [<pokemon>...], pioche/main/defausse/recompenses/zone_perdue: N}`.
Le **tour** : `{joueur, numero, phase, energie_posee, supporter_joue, retraite_faite, entres: [...]}`.
Au plus haut niveau : les deux clés qui ne sont pas `tour`/`stade`/`stade_proprietaire`/`terminee`/`vainqueur`/`raison_fin`
nomment les deux joueurs (défaut `alice`, `bob`).

**Identifiants déterministes** (pour citer une carte, ex. une énergie à défausser) : l'énergie `i`
de l'Actif de `alice` est `alice.actif.ei` ; du banc `k`, `alice.bancK.ei`. La carte de base d'un
Pokémon : `alice.actif` (banc : `alice.bancK`).

## Les tirages d'aléatoire (déterminisme)

Un cas qui dépend d'un pile ou face (confusion, réveil, guérison de brûlure) liste ses `tirages`
`[{flux, resultat}]`. L'exécuteur **cherche une graine** qui produit exactement ces résultats
(`trouver_graine`) : le cas reste donc parfaitement déterministe et reproductible. Les flux :
`partie:qui-commence`, `confusion:<joueur>`, `checkup:brule:<joueur>`, `checkup:endormi:<joueur>`,
`melange:deck:<joueur>`.

## Ajouter un cas

1. Choisir le fichier de la mécanique (`degats.yaml`, `etats.yaml`, …) ou en créer un.
2. Écrire le cas en données, en citant la ou les règles `R-x.y` de `REGLES.md` qu'il vérifie.
3. `cd apps/game && UV_PYTHON=3.12 uv run pytest -q tests/test_cas_executables.py` — il doit être vert.
4. **Tout lot de moteur doit ajouter ses cas** : une mécanique nouvelle sans cas de règle est un
   lot inachevé. Quand une mécanique jusqu'ici non implémentée arrive (évolution, Supporter,
   effets de cartes…), retirer sa ligne de `couverture-exceptions.yaml` et ajouter ses cas — la
   garde `test_couverture_regles.py` refuse une exception périmée.
