# Résolution d'attaque — `pbm_game.combat`

> Livré par le lot `j-degats-resolution` (jalon J1). Le code vit dans
> `apps/game/src/pbm_game/combat/` ; l'événement de journal `EVT_DEGATS` est déclaré dans
> `apps/game/src/pbm_game/journal/modele.py`. Cette fiche documente **le paiement du coût** et
> **le calcul des dégâts** dans l'ordre officiel. Tout est **pur** : fonctions sans E/S,
> descripteurs sérialisables, testables par milliers de cas.

## Pourquoi

C'est le geste central du jeu, et celui dont le calcul est le plus souvent faux : l'ordre des
opérations entre faiblesse, résistance et modificateurs change le résultat. Appliquer la
faiblesse après les réductions, ou soustraire des PV, sont deux erreurs **invisibles** jusqu'au
jour où un joueur compte et découvre qu'il a perdu à tort. On suit donc **à la lettre** l'ordre
strict du corpus (`docs/jeu/REGLES.md` §R-10) et chaque étape est tracée.

## Ce que le moteur reçoit, ce qu'il ne devine pas

Le moteur ne connaît **pas encore** les données de carte (type d'une énergie, coût imprimé,
faiblesse d'un Pokémon, attaques) : elles arrivent avec `j-cartes-pokemon` (que ce lot
débloque). La résolution travaille donc sur des **descripteurs** déjà extraits du catalogue —
`CoutAttaque`, `Faiblesse`, `Resistance`, `Modificateur` — et ne les approxime jamais (D9). Ce
lot livre **le calcul et ses crochets** ; le câblage des descripteurs depuis le catalogue est
la couche suivante.

## Paiement du coût (R-9.2) — `cout.cout_satisfait`

Un `CoutAttaque` porte les symboles **colorés** par type (`types={"feu": 1, "eau": 1}`) et le
nombre de symboles **incolores** (`incolore`, le ★). Pour chaque énergie attachée, l'appelant
fournit ce qu'elle **fournit** — un mapping `{type: unités}` :

| Énergie | Fournit | Pourquoi |
|---|---|---|
| Énergie Feu de base | `{"feu": 1}` | 1 unité d'un type |
| Double Énergie Incolore | `{"incolore": 2}` | une énergie **fournit plusieurs unités** (R-9.2) |
| Énergie spéciale bi-type | `{"feu": 1, "eau": 1}` | plusieurs types |

Règle de paiement : le coût demande « **au moins** » l'énergie requise (le surplus ne gêne
pas). Un symbole **coloré** se paie par une unité de **ce type exact** ; un symbole
**incolore** par **n'importe quelle** unité restante (y compris `incolore`). On paie donc
d'abord les colorés (ils n'acceptent que leur type), puis les incolores avec le reste — c'est
optimal. Une unité `incolore` **ne paie jamais** un symbole coloré. Un refus cite **R-9.2** et
nomme ce qui manque, jamais un refus muet.

## Calcul des dégâts (R-10.1) — `resolution.resoudre_degats`

L'ordre est **strict** et chaque étape est un `EtapeCalcul` (fragment lisible + règle + avant/après) :

1. **base** imprimée ;
2. **modificateurs côté attaquant** (`modificateurs_attaquant`) — puis **arrêt si le résultat
   est ≤ 0** : la faiblesse n'est alors **jamais** appliquée (R-16.8), et `arrete_avant_degats`
   vaut vrai ;
3. **faiblesse** `×facteur` (×2 par défaut, R-10.2) ;
4. **résistance** `−réduction` (−30 par défaut, R-10.3) ;
5. **modificateurs côté défenseur** (`modificateurs_defenseur`, réductions) ;
6. **plancher à 0** (R-10.7) puis **1 compteur par 10 dégâts** (R-10.1 étape 6).

Au banc (`au_banc=True`), les étapes 3 et 4 sont **sautées** — ni faiblesse ni résistance
(R-10.5). Les auto-dégâts (recul) empruntent le même chemin « sans faiblesse/résistance ».

**Applicabilité du type.** `faiblesse`/`resistance` ne jouent que si l'attaque est de leur type
(`type_attaque`). `type_attaque=None` signifie « applicabilité déjà décidée par l'appelant »
(le catalogue a fait l'appariement, ou un test isole l'arithmétique).

**Les modificateurs** (`Modificateur`) sont les **points d'accroche nommés** des étapes 2 et 5.
Au jalon J1 les listes sont **vides** : aucun effet de carte n'est encore scripté (D9). Chaque
modificateur porte un `libelle`, la `regle` qui le motive et une opération d'un ensemble fermé
(`ajout` / `multiplie` / `fixe`) ; les lots d'effets à venir les rempliront, scriptés et testés.

## Pose des dégâts : en COMPTEURS, jamais en PV (R-10.4)

`resoudre_degats` **calcule**, elle ne pose rien. La pose se fait par :

- `poser_degats(pokemon, degats)` — augmente `compteurs_degats` du montant calculé (cumulatif,
  renvoie un nouveau `PokemonEnJeu` figé) ;
- `poser_compteurs(pokemon, n)` — pose `n` compteurs **directs** = `n × 10` dégâts, pour les
  effets « placez N compteurs » qui ne sont affectés par **aucune** faiblesse, résistance ni
  modificateur (R-10.6).

On n'écrit **jamais** de PV : les soins et les effets « PV restants » se calculent depuis les
compteurs et les PV de la carte (K.O. quand `compteurs_degats ≥ PV`, R-13.1 — lot
`j-ko-recompenses`).

## Détail de calcul et journal (R-10.9)

`ResultatDegats.detail` reproduit l'exemple du corpus : **« 60 base, ×2 faiblesse, −30
résistance = 90 »** (signes `×` U+00D7 et `−` U+2212). `evenement_degats(resultat, cible)`
construit l'événement `EVT_DEGATS` qui porte ce détail en valeurs **JSON natives** — c'est lui
qu'affichent le journal de partie et l'aide en jeu.

## Table de cas

Les huit cas `degats-*` de `docs/jeu/cas-de-regles.yaml` sont **exécutés** par
`apps/game/tests/test_degats.py` (table `CAS_DEGATS`), chacun citant son `R-x.y`. Un test de
couverture échoue si un cas `degats-*` du corpus n'a pas d'entrée exécutable — pas d'oubli
silencieux. S'y ajoutent les tests de coût (R-9.2), de pose en compteurs (R-10.4/R-10.6), du
plancher (R-10.7), de l'arrêt sur dégât nul (R-16.8) et des crochets de modificateurs.

## Ce qui n'est PAS dans ce lot

- le câblage des descripteurs depuis le **catalogue** (`j-cartes-pokemon`) et le coup d'attaque
  **listé** par le générateur d'actions ;
- la **mise K.O.**, les **récompenses** et les conditions de victoire (`j-ko-recompenses`,
  qui lit `compteurs_degats ≥ PV`) ;
- les **effets** d'attaques (modificateurs concrets), talents et Dresseurs — chacun scripté et
  testé dans son lot (D9).
