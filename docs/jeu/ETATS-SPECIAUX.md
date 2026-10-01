# États spéciaux — `pbm_game.etats`

> Livré par le lot `j-etats-speciaux` (jalon J1, palier 7). Le code vit dans
> `apps/game/src/pbm_game/etats/`. Cette fiche documente la **pose** des cinq états, leur
> **matrice de cumul**, la **confusion à la déclaration d'attaque** et la **guérison**. La
> *résolution au Checkup* (compteurs de poison/brûlure, pile ou face de réveil/brûlure dans
> l'ordre R-12.2) vit dans [`CHECKUP.md`](CHECKUP.md) ; la *forme* des états (constantes,
> orientation dérivée) dans [`ETAT.md`](ETAT.md). Règles de référence : [`REGLES.md`](REGLES.md)
> §R-11.

## Les cinq états (R-11.1)

**Endormi**, **Brûlé**, **Confus**, **Paralysé**, **Empoisonné**. Un état ne frappe que le
Pokémon **Actif** (R-11.2). Deux familles, qui déterminent tout le cumul :

- **États d'orientation** — Endormi, Confus, Paralysé : ils **tournent la carte** sur la table,
  donc **un seul des trois à la fois** (`orientation()` le dérive dans `pbm_game.state`).
- **États à marqueur** — Brûlé, Empoisonné : un **jeton** posé à côté, **cumulable** avec
  l'orientation en cours *et* avec l'autre marqueur.

## La matrice de cumul (R-11.8) — le piège du lot

Le cumul est ce qui est le plus souvent joué de travers. `appliquer_etat(pokemon, etat)` encode
la matrice **une fois** :

- poser un état **d'orientation** → il **remplace** l'orientation en place (le dernier posé
  gagne) et **laisse** les marqueurs ;
- poser un **marqueur** → il **s'ajoute**, en laissant l'orientation et l'autre marqueur ; un
  marqueur déjà présent reste un seul marqueur (« un nouveau remplace l'ancien », R-11.4/R-11.7).

L'exemple officiel du livret — **Brûlé + Paralysé + Empoisonné** simultanés — est donc légal.
La matrice complète (6 états en place × 5 posés = 30 paires) est **testée exhaustivement** dans
`tests/test_etats_speciaux.py`, comparée à la table recopiée depuis `REGLES.md` (jamais
recalculée avec la logique du code). Un état inconnu **échoue bruyamment** (`ValueError`, D9) :
jamais posé « au mieux ».

Un invariant d'état garde la cohérence : au plus un état d'orientation par Pokémon
(`state.invariants`, R-11.8). `appliquer_etat` ne peut donc pas produire d'état incohérent.

## La confusion à la déclaration d'attaque (R-11.5)

`resoudre_etats_avant_attaque(etat, jid, rng)` est appelé par `declarer_attaque`
(`pbm_game.journal.transitions`) **avant** que l'attaque ne produise ses effets :

| État de l'Actif | Ce qui se passe |
|---|---|
| **Endormi** / **Paralysé** | `ValueError` — il ne peut pas attaquer (R-11.3/R-11.6) |
| **Confus** | pile ou face : **face** = l'attaque a lieu normalement ; **pile** = l'attaque **n'a pas lieu** et **3 compteurs** (30 dégâts) sont posés sur le Pokémon confus |
| aucun (ou marqueurs seuls) | l'attaque a lieu |

Dans **tous** les cas où le coup est accepté, **le tour se termine** (R-5.8 : déclarer une
attaque termine le tour, qu'elle ait eu lieu ou non) — `declarer_attaque` entre ensuite en phase
`checkup`. Si l'auto-blessure de confusion met l'Actif K.O., le K.O. est traité **au Checkup**
(R-12.4/R-16.4), pas pendant la déclaration.

Le pile ou face de confusion tire dans **`flux_confusion(jid)`** (`pbm_game.rng`), un flux par
joueur distinct de ceux du Checkup : il est journalisé (`EVT_CONFUSION`) et revérifiable par
`verifier_journal`, comme tout tirage. La résolution est donc **déterministe** et rejouable.

> **Import local, par nécessité.** `transitions.py` importe `resoudre_etats_avant_attaque` *dans*
> `_declarer_attaque`, pas au chargement : `etats.attaque` importe `journal.modele`, dont le
> paquet `journal` réimporte `transitions` — un import au chargement formerait un cycle. La
> matrice/guérison pures (`etats.matrice`), elles, ne dépendent que de `state` et s'importent
> normalement (c'est ce que fait `banc`).

## La guérison de tous les états (R-11.9) — une seule porte

`soigner_etats_speciaux(pokemon)` retire **tous** les états et ne touche qu'à eux (énergies,
Outil, compteurs, pile d'évolutions conservés). C'est la porte **partagée** par :

- le **passage au banc** (retraite, promotion, échange forcé) — `pbm_game.banc.mouvements`, qui
  route désormais son `_nettoyer_pour_banc` par cette fonction (voir [`BANC.md`](BANC.md)) ;
- l'**évolution** (lot `j-cartes-pokemon`, à venir) et les **effets de soin** passeront par ici.

Une seule porte, pour que « que garde / que perd un Pokémon qui guérit » ne diverge pas entre ces
chemins. Rappel : seuls **Endormi** et **Paralysé** empêchent la *retraite* (R-11.10) — déjà
appliqué par `battre_en_retraite` ; la **Confusion n'empêche pas** de se retirer.

## L'orientation est exposée au client (R-11.8)

La projection par joueur (`vue`, `pbm_game.state.projection`) ajoute un champ **`orientation`**
à chaque Pokémon (`normale` / `endormi` / `confus` / `paralyse`), dérivé par le moteur qui fait
autorité. L'interface montre la carte « comme sur une vraie table » sans redériver la règle
côté écran (*L'interface ne décide de rien*).

## Ce que ce lot ne fait pas

- Les effets de carte qui **infligent** un état (attaques, Dresseurs) ne sont pas scriptés ici :
  ils arrivent avec `j-cartes-attaques-effets` et appelleront `appliquer_etat` (D9 — rien n'est
  approximé en attendant).
- La résolution au Checkup (compteurs, réveil, guérison de brûlure, guérison de paralysie après
  le tour du propriétaire) était déjà livrée par `j-checkup` — ce lot ne la réécrit pas.
