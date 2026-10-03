# SIMULATION.md — bots de simulation : des milliers de parties pour débusquer les blocages

> Le moteur est pur et rejouable : on peut donc le **faire jouer par des bots**, par milliers, et
> regarder ce qui casse. Les cas de règles (`cas-de-regles.yaml`) vérifient ce qu'on a *prévu* ;
> les bots trouvent ce qu'on n'a *pas* prévu — boucles, états impossibles, parties sans fin.
> Livré par le lot `j-simulation-bots` (jalon J2).

## Ce que c'est

Le paquet **`pbm_sim`** (`apps/game/src/pbm_sim/`) est de l'**outillage**, pas le moteur : il vit à
côté de `pbm_game` dans le même `src` (pour que les tests l'importent), mais il n'en fait pas
partie — il a le droit de lire des fichiers, d'ouvrir des processus et de tirer de l'aléatoire
(`random`), ce que le moteur s'interdit. Le moteur ne l'importe jamais ; c'est l'inverse. Il n'est
pas empaqueté dans le *wheel* du moteur.

| Module | Rôle |
|---|---|
| `pbm_sim.bots` | deux bots qui décident sur la **seule vue joueur** : `bot_aleatoire`, `bot_heuristique` |
| `pbm_sim.decks` | un roster de decks **synthétiques** entièrement jouables, et le `Scenario` qu'une graine détermine |
| `pbm_sim.orchestrateur` | `jouer_partie(graine)` — joue une partie, range toute défaillance dans une `Anomalie` nommée |
| `pbm_sim.campagne` | `campagne(graines)` — des milliers de parties en parallèle, et la distribution des durées |
| `pbm_sim.rapport` | la mise en forme lisible d'une campagne |
| `python -m pbm_sim` | la ligne de commande : `campagne`, `reproduire` |

## La règle d'or : les bots jouent sur la vue, pas sur l'état

Un bot reçoit exactement ce qu'un vrai client reçoit — la projection `pbm_game.state.vue` (sa main,
le plateau public, le **nombre** de cartes cachées) et la **liste des coups légaux** que le moteur a
calculés pour lui — puis il en choisit un. Il ne voit **jamais** la main de l'adversaire, l'ordre de
la pioche ni le contenu des récompenses : ces fonctions ne reçoivent pas l'`EtatPartie`, par
construction (un test le garde : `test_simulation_bots.py`). Un blocage qu'un bot rencontre est donc
un blocage qu'un vrai joueur pourrait rencontrer.

- **`bot_aleatoire`** joue n'importe quel coup légal (hors abandon), au hasard de son propre flux
  reproductible : c'est lui qui explore les combinaisons tordues.
- **`bot_heuristique`** joue proprement : promouvoir le Pokémon le moins amoché (R-8.7), attaquer
  pour le plus de dégâts (R-9/R-10), évoluer (R-7), poser ses bases, et n'attacher une énergie que
  si ça rapproche d'une attaque — *il économise ses ressources*. Ses parties ressemblent à de vraies
  parties, donc leurs durées sont parlantes.

Les deux **ignorent l'abandon** tant qu'un autre coup existe (et il en existe toujours un : avancer
la phase) — sinon un bot mettrait fin aux parties sans rien exercer.

## Les decks sont synthétiques, et c'est voulu

Au jalon J2, seules les attaques à **dégâts secs** sont jouables (D9 — une attaque à effet n'est pas
scriptée, la construction de deck la refuse). Les bots ont donc besoin de decks **entièrement
jouables** du premier coup à la victoire. Le roster (`pbm_sim.decks.ARCHETYPES`) en fournit six, 60
cartes chacun, qui exercent largement le moteur : aggro rapide, tank à coût incolore, ligne
d'**évolution** (R-7), **faiblesse** ×2 (R-10.2), **résistance** −30 (R-10.3), coût de **retraite**
élevé (R-8.2) et cible **TAG TEAM** à trois récompenses (R-15.7). Quand les lots de scripts de
cartes arriveront (`j-cartes-*`), le roster s'enrichira de cartes réelles au fur et à mesure
qu'elles deviennent jouables.

## Les anomalies qu'on cherche

Après **chaque** coup, l'orchestrateur contrôle les invariants de l'état (`pbm_game.state.invariants`) ;
à la fin, il rejoue le journal et compare l'empreinte. Tout ce qui cloche devient une `Anomalie`
nommée — jamais un `continue` muet :

| Type | Ce qu'il attrape |
|---|---|
| `etat_invalide` | un invariant violé après un coup (carte en double, banc > 5, compteurs négatifs, total qui bouge) |
| `exception` | un coup — légal ou système — qui lève en s'appliquant |
| `blocage` | un point de décision sans aucun coup jouable, partie non finie |
| `partie_sans_fin` | plus de `max_pas` coups sans fin — **la forme d'une boucle d'effets** (le risque nommé par la fiche) |
| `rejeu_divergent` | le rejeu du journal ne redonne pas l'état final |
| `demande_inattendue` | une demande de décision en attente que le harnais J2 ne pilote pas (les decks synthétiques n'en produisent pas) |

**Le transitoire de promotion est exempté, lui seul.** Après un K.O., le moteur laisse
volontairement l'état « Actif absent, banc non vide, partie non finie » (R-3.3/R-8.7) jusqu'à la
promotion du tour suivant — ses propres tests ne vérifient d'ailleurs pas les invariants sur cet
état précis. L'orchestrateur l'exempte donc, mais **étroitement** (ce joueur, dans cet état) : toute
autre violation passe (`test_simulation_orchestrateur.py` le prouve dans les deux sens).

## Reproduire une anomalie — en une commande

Une partie est **entièrement déterminée par sa graine** : le choix des deux decks, des deux bots, du
siège qui commence et la graine d'aléatoire du moteur en découlent. La même graine redonne donc
exactement la même partie. Chaque anomalie porte sa graine ; pour la revoir en détail :

```bash
cd apps/game
uv run python -m pbm_sim reproduire <graine>            # issue, durée, anomalies, fin de journal
uv run python -m pbm_sim reproduire <graine> --derniers 0   # tout le journal
```

Code de sortie **1** si la partie rejouée porte une anomalie — utilisable comme garde.

## Lancer une campagne

```bash
cd apps/game
uv run python -m pbm_sim campagne --prefixe nuit --nombre 10000      # des milliers de parties
uv run python -m pbm_sim campagne --prefixe x --nombre 500 --serie   # en série (sans parallélisme)
```

Sort en **1** s'il reste la moindre anomalie. Le parallélisme (un processus par cœur) est le défaut ;
la campagne ne s'arrête **jamais** au premier pépin — elle les collecte tous, pour donner une mesure
(« X anomalies sur N »), pas juste un premier échec.

## Où ça tourne, et quand

- **En CI, à chaque poussée** : une campagne **réduite** (250 parties) tourne dans le job `game` de
  GitHub Actions (`test_simulation_campagne_ci.py`). Une régression du moteur fait rougir ce test,
  avec la graine fautive. C'est la garde « une campagne à chaque lot de scripts de cartes ».
- **Chaque nuit** : une campagne **longue** (`.github/workflows/simulation-nuit.yml`, cron) ; en cas
  d'anomalie, le job échoue et les graines sont dans son journal.
- **Sur chimera**, à la demande : les campagnes de masse (10 000+) — c'est la machine qui construit,
  16 fils, pas celle qui sert.

## Le chiffre du lot

Campagne de **10 000 parties** sur chimera (préfixe `jalon-j2`) : **10 000 saines, 0 anomalie**.
Distribution des durées et détail : `docs/roadmap/comptes-rendus/j-simulation-bots.md`.
