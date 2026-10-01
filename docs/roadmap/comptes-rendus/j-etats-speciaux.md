# Compte rendu — `j-etats-speciaux`

**Lot** : États spéciaux — Empoisonné, Brûlé, Endormi, Paralysé, Confus (jalon J1, palier 7,
couloir J-MOT, moteur Python pur). **Machine** : devAI, session autonome. **Statut** : livré,
CI verte sur la PR, fusionné dans `main`.

## Résumé

Le moteur savait déjà **résoudre** les états au Pokémon Checkup (compteurs de poison/brûlure,
pile ou face de réveil/brûlure, guérison de paralysie — livré par `j-checkup`) et bloquait déjà
la **retraite** sous Sommeil/Paralysie (livré par `j-retraite-banc`). Ce lot ajoute ce qui
restait : la **pose** des états et leur **matrice de cumul** (R-11.8), la **confusion à la
déclaration d'attaque** (R-11.5), le **blocage de l'attaque** sous Sommeil/Paralysie
(R-11.3/R-11.6), la **guérison partagée** (R-11.9) et l'**orientation** de la carte exposée au
client. Nouveau paquet pur `pbm_game.etats`.

## Livrables

- **`apps/game/src/pbm_game/etats/matrice.py`** — `appliquer_etat` (matrice de cumul R-11.8 :
  orientation qui remplace, marqueurs qui cumulent, état inconnu = `ValueError`/D9),
  `soigner_etats_speciaux` (guérison de tous les états, R-11.9, porte partagée),
  `etat_bloquant_attaque` (R-11.3/R-11.6). Pur : ne dépend que de `state`.
- **`apps/game/src/pbm_game/etats/attaque.py`** — `resoudre_etats_avant_attaque` : blocage
  Sommeil/Paralysie (refus motivé) + pile ou face de confusion (R-11.5 : face = attaque,
  pile = attaque annulée + 3 compteurs sur soi), journalisé (`EVT_CONFUSION`).
- **`apps/game/src/pbm_game/etats/__init__.py`** — exports du paquet.
- **Branchements, sans réécriture** : `journal/transitions.py::_declarer_attaque` résout les
  états avant l'attaque (import local, voir « Écarts ») ; `banc/mouvements.py::_nettoyer_pour_banc`
  route sa guérison par `soigner_etats_speciaux` (R-11.9, une seule porte) ;
  `state/projection.py` ajoute `orientation` à la vue par joueur ; `rng` ajoute `flux_confusion` ;
  `journal/modele.py` ajoute l'événement `EVT_CONFUSION`.
- **Doc** : `docs/jeu/ETATS-SPECIAUX.md` (fiche durable) ; pointeur ajouté dans `docs/jeu/BANC.md`.
- **Tests** : `apps/game/tests/test_etats_speciaux.py` (68 tests).

## Preuves

- Suite moteur complète : **327 tests passent** (`UV_PYTHON=3.12 uv run pytest -q` dans
  `apps/game`), dont 68 nouveaux. Avant le lot, 259.
- Lint : **`ruff check .` — All checks passed** dans `apps/game`.
- Matrice de cumul **testée exhaustivement** : 6 états en place × 5 posés = 30 paires, comparées
  à la table recopiée depuis `REGLES.md` (`test_matrice_de_cumul_exhaustive_r118`).
- Critères d'acceptation :
  - *Matrice exhaustive (toutes les paires)* → `test_matrice_de_cumul_exhaustive_r118` ✅
  - *Endormi/Paralysé ne peut ni attaquer ni se retirer, mais peut être échangé de force* →
    `test_declarer_attaque_refusee_sous_sommeil_ou_paralysie_r113_r116` (attaque),
    `test_guerison_par_passage_au_banc_r119` + suite `test_retraite_banc` (retraite bloquée),
    `test_retraite_banc` échange forcé autorisé sous état (déjà couvert) ✅
  - *Compteurs de poison/brûlure au bon moment + pile ou face de brûlure journalisé* →
    `test_poison_et_brulure_posent_leurs_compteurs_au_checkup_r117_r114` ✅
- Confusion : `test_confusion_face_attaque_a_lieu_r115`, `…_pile_attaque_annulee_et_3_compteurs…`,
  `…_est_deterministe_et_journalisee…`.
- Pureté : import de `pbm_game.etats` sans dépendance lourde + analyse statique `rglob` du paquet
  (déjà dans `test_corpus_regles.py`, couvre les nouveaux modules).
- Imports sans cycle vérifiés depuis 8 points d'entrée (`pbm_game`, `.etats`, `.journal`, `.banc`,
  `.checkup`, `.actions`, `.combat`, `.state`).

## Décisions appliquées

- **DJ1** (format maison, règles actuelles) : corpus `REGLES.md` §R-11 appliqué à la lettre.
- La **matrice R-11.8** suit le livret en vigueur : Endormi/Confus/Paralysé s'orientent et se
  remplacent ; Brûlé/Empoisonné cumulent (exemple officiel Brûlé+Paralysé+Empoisonné supporté).

## Écarts au plan

- **Import local dans `transitions._declarer_attaque`.** `etats.attaque` importe `journal.modele`,
  dont le paquet `journal` réimporte `transitions` : un import au chargement formait un cycle
  (constaté après que `ruff` a trié les imports de `banc` en plaçant `etats` avant `journal`).
  La résolution avant attaque est donc importée au moment de l'appel ; la matrice/guérison pures
  (`etats.matrice`), sans dépendance à `journal`, restent importées normalement. Documenté dans le
  code et la fiche.
- **Aucune modification de `ci.yml`** : le job `game` exécute déjà `ruff` + `pytest` sur tout
  `apps/game`, donc les nouveaux modules et tests sont couverts sans ajout.

## Reste à faire (hors périmètre, D9 respecté)

- **Infliger** un état via un effet de carte (attaque/Dresseur) : arrive avec
  `j-cartes-attaques-effets`, qui appellera `appliquer_etat`. Ce lot débloque ce travail.
- **Guérison par évolution** : la primitive `soigner_etats_speciaux` est prête et testée ; le
  branchement se fera dans `j-cartes-pokemon` (l'évolution n'existe pas encore). Pas de simulacre
  d'évolution ici (D9).
