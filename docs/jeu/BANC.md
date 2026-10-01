# Banc, retraite et promotion — `pbm_game.banc`

> Livré par le lot `j-retraite-banc` (jalon J1). Le code vit dans
> `apps/game/src/pbm_game/banc/` ; les types d'action et d'événement sont déclarés dans
> `apps/game/src/pbm_game/journal/modele.py`. Cette fiche documente **les trois façons** dont le
> Pokémon Actif change de place et **ce qu'elles n'ont pas en commun**. Tout est **pur** :
> fonctions sans E/S, état figé, transitions journalisées et rejouables.

## Pourquoi

Le déplacement de l'Actif est le geste **défensif** du jeu, et la cible des effets d'appât.
Trois mouvements y mènent, aux règles **différentes** — les confondre est le piège nommé par la
fiche du lot : un échange forcé traité comme une retraite rendrait les cartes d'appât injouables
sous Paralysie (R-16.12) ou leur ferait consommer la retraite du tour. Chacun a donc son chemin.

| Mouvement | Fonction | Déclencheur | Coût | Interdit sous Sommeil/Paralysie ? | Marque la retraite du tour ? |
|---|---|---|---|---|---|
| **Retraite** (R-8.2/3/4) | `battre_en_retraite` | volontaire, son tour | énergies **au choix** (R-8.2) | **oui** (R-8.4/R-11.10) | **oui** (R-5.6/R-8.3) |
| **Promotion** (R-8.7) | `promouvoir` | obligatoire après un K.O. | — | n/a (Actif absent) | non |
| **Échange forcé** (R-8.8) | `echange_force` | un **effet** de carte | **aucun** | **non** (R-16.12) | **non** |

## Le passage au banc (R-8.6) — ce qu'il soigne, et rien d'autre

Les trois mouvements partagent la même porte, `_nettoyer_pour_banc` : le Pokémon qui **descend
au banc** perd ses **états spéciaux** et les **effets d'attaque**, mais **conserve** énergies,
Outil, compteurs de dégâts (R-10.4) et pile d'évolutions. Depuis `j-etats-speciaux`, le retrait
des états passe par `pbm_game.etats.soigner_etats_speciaux` (R-11.9), **partagé** avec la guérison
par évolution et par effet de soin — voir [`ETATS-SPECIAUX.md`](ETATS-SPECIAUX.md). C'est là, et
nulle part ailleurs, que les effets temporaires portés par l'état se retireront quand les lots
d'effets arriveront — une seule porte, pour qu'un effet ne devienne jamais éternel en silence. En promotion, le Pokémon qui
monte vient du banc, où aucun état ne peut vivre (R-11.2) : il est propre par construction.

## Ce que le moteur reçoit, ce qu'il ne devine pas (D9)

Le moteur est **pur** et ne lit pas le catalogue. Il reçoit :

- le **coût de retraite** (`cout_retraite`, nombre de symboles) — lu sur la carte par le service,
  pas deviné ici ;
- le **choix du joueur** — quelles énergies défausser (`energies_defaussees`, des `instance_id`)
  et quel Pokémon du banc promouvoir (`banc_index`).

Il **valide** (une énergie par symbole, toutes réellement attachées, un index dans le banc) et
**applique**. Un refus lève une `ValueError` qui **cite la règle** (R-8.2, R-8.4, …) — jamais un
refus muet. La *liste* de la retraite comme coup jouable par le générateur d'actions attend le
coût imprimé : elle arrive avec `j-cartes-pokemon` (que ce lot débloque).

## Les trois transitions, en détail

### Retraite — `battre_en_retraite(etat, jid, banc_index, cout_retraite, energies_defaussees)`

Gardes (le serveur tient les règles) : partie vivante (R-14.6), **joueur actif** seulement et
**corps du tour** (phase principale ou d'attaque, R-5.1), **une seule par tour** (R-5.6/R-8.3,
via `tour.retraite_faite`), Actif présent, **ni Endormi ni Paralysé** (R-8.4/R-11.10), un
Pokémon de banc pour prendre la place (R-8.2). Puis : défausse des énergies choisies — une **par
symbole**, au choix, coût nul = gratuit (R-8.2) —, l'ancien Actif descend **nettoyé** (R-8.6) et
le banc monte Actif (il **peut attaquer** le même tour, R-8.5). Marque `retraite_faite` (R-8.3).

### Promotion — `promouvoir(etat, jid, banc_index)`

Précondition : l'Actif de `jid` est **absent** (`None`) — le vide laissé par un K.O. Si le banc
est **vide**, `jid` n'a plus de Pokémon à promouvoir : c'est une **défaite** (R-8.9/R-14.1 cas 2),
pas une exception — la partie se fige, l'adversaire gagne, raison `plus_de_pokemon`
(`RAISON_PLUS_DE_POKEMON`). Exactement le motif de la pioche impossible (R-14.2) : une condition
de fin vérifiée au bon moment. Sinon, `banc[banc_index]` devient Actif. Refuse un Actif **présent**
(aucune promotion requise, R-8.7). La **mise K.O.** elle-même (défausse, récompenses, R-13) est le
lot `j-ko-recompenses`, qui laisse l'Actif à `None` puis appelle ce chemin.

### Échange forcé — `echange_force(etat, jid, banc_index)`

Provoqué par un effet. **Ne consomme ni** la retraite du tour **ni** d'énergie, et reste
**autorisé** même sous Sommeil ou Paralysie (R-16.12) — c'est ce qui le distingue de la retraite.
L'ancien Actif descend **nettoyé** (R-8.6). Refuse un Actif absent (ce serait une promotion,
R-8.7) et un banc vide (aucune cible, R-8.8). La **cible** (le joueur dont l'Actif change) est
nommée dans `params["joueur"]`, jamais devinée ; l'effet qui le déclenche viendra plus tard (D9).

## Actions et événements journalisés

Trois `Action.type` — `retraite`, `promouvoir`, `echange_force` — et trois `Evenement` —
`retraite_effectuee`, `promotion_effectuee`, `echange_force_effectue` (plus `partie_terminee`
pour la défaite au banc vide). Leurs gestionnaires (`appliquer_*`) **s'enregistrent eux-mêmes**
dans le `REGISTRE` du journal en bas de `banc/mouvements.py` : `pbm_game` importe `banc` à son
chargement pour le garantir. Faire l'inverse (le noyau des transitions tirant `banc`) créerait un
cycle d'import, puisque `banc` dépend du journal. Comme toutes les transitions, les trois sont
**rejouables** : rejouer le journal d'une partie qui contient une retraite redonne l'état exact.

## Tests — `apps/game/tests/test_retraite_banc.py`

Les trois chemins sont testés séparément, et les quatre cas exigés par la mission : **retraite
sans énergie suffisante** (R-8.2), **banc plein** (R-8.1, l'échange ne déborde pas les 5),
**échange forcé sous Paralysie** (R-8.8/R-16.12, là où la retraite refuse) et **promotion banc
vide** (R-8.9, défaite). S'y ajoutent : le passage au banc soigne les états mais conserve
énergies/Outil/compteurs/pile (R-8.6), l'échange forcé **ne consomme pas** la retraite du tour
(R-8.8), la rejouabilité, la sérialisation round-trip et la lisibilité du journal. Chaque test
cite un `R-x.y`, et deux tests vérifient que tous ces identifiants **existent** dans
`docs/jeu/REGLES.md`.

## Ce qui n'est PAS dans ce lot

- la **mise K.O.** (défausse du Pokémon K.O., récompenses, R-13) et les **conditions de victoire**
  autres que le banc vide → `j-ko-recompenses` ;
- la **retraite listée** comme coup jouable par le générateur, qui a besoin du **coût imprimé** du
  catalogue → `j-cartes-pokemon` ;
- l'**effet** concret qui déclenche un échange forcé (cartes d'appât) → lots d'effets (D9).
