# Compte rendu — `j-retraite-banc`

**Lot** : Banc, retraite et promotion : le Pokémon actif change de place
**Couloir** : J-MOT (moteur Python pur) · **Jalon** : J1 · **Machine** : devAI
**Statut** : livré (moteur pur ; aucune UAT/PROD — ce lot ne touche ni serveur, ni base, ni front)

## Résumé

Le geste défensif du jeu est en place : l'Actif change de place par **trois chemins distincts**,
chacun avec ses propres règles (R-8), dans un nouveau paquet pur `pbm_game.banc`.

- **Retraite** (R-8.2/3/4) — volontaire, pendant son tour : défausse d'**une énergie par symbole**
  du coût de retraite **au choix du joueur** (coût nul = gratuit), **une seule par tour**
  (R-5.6/R-8.3), **interdite** sous Sommeil ou Paralysie (R-8.4/R-11.10), le nouvel Actif peut
  attaquer le même tour (R-8.5).
- **Promotion** (R-8.7) — obligatoire après un K.O. (Actif absent) : un Pokémon du banc monte ;
  **banc vide = défaite** (R-8.9/R-14.1 cas 2), raison `plus_de_pokemon`, condition de fin
  vérifiée au bon moment (jamais une exception), sur le modèle de la pioche impossible.
- **Échange forcé** (R-8.8) — provoqué par un effet : **ni** retraite du tour consommée **ni**
  énergie, **autorisé** même sous Sommeil/Paralysie (R-16.12) — c'est ce qui le distingue de la
  retraite et garde les cartes d'appât jouables (le piège nommé par la fiche).

Les trois partagent le **passage au banc** (R-8.6, une seule porte `_nettoyer_pour_banc`) : le
Pokémon qui descend perd ses états spéciaux et les effets d'attaque, mais **conserve** énergies,
Outil, compteurs de dégâts (R-10.4) et pile d'évolutions. Ce sont des **transitions journalisées**
et donc rejouables.

## Livrables

- `apps/game/src/pbm_game/banc/mouvements.py` — `battre_en_retraite`, `promouvoir`,
  `echange_force` (+ gestionnaires `appliquer_*`), le passage au banc partagé, et l'auto-
  enregistrement des trois transitions dans le `REGISTRE`.
- `apps/game/src/pbm_game/banc/__init__.py` — façade du paquet.
- `apps/game/src/pbm_game/journal/modele.py` — 3 types d'action (`retraite`, `promouvoir`,
  `echange_force`), 3 types d'événement, et `RAISON_PLUS_DE_POKEMON` (R-8.9/R-14.1).
- `apps/game/src/pbm_game/journal/debogage.py` — rendu lisible des trois nouveaux événements.
- `apps/game/src/pbm_game/__init__.py` — importe `banc` au chargement pour garantir
  l'enregistrement des transitions (le noyau des transitions ne peut pas le faire : cycle).
- `apps/game/tests/test_retraite_banc.py` — 30 tests.
- `docs/jeu/BANC.md` — la fiche durable du lot.

## Preuves

- **CI GitHub Actions verte sur la PR** (elle fait foi — à confirmer avant fusion).
- Localement sur devAI (`UV_PYTHON=3.12 uv run`) : `ruff check .` **OK**, `pytest -q` →
  **201 passed** (171 avant → 30 nouveaux).
- **Test qui échoue sans le changement et passe avec** : toute la suite importe `pbm_game.banc`
  en tête — sans le paquet, la collecte échoue.
- **Les trois mouvements ont des chemins distincts et testés** : sections dédiées
  (retraite / promotion / échange forcé), plus les quatre cas exigés par la mission — retraite
  sans énergie suffisante (R-8.2), banc plein (R-8.1, pas de 6e), échange forcé sous paralysie
  (R-8.8/R-16.12), promotion banc vide (R-8.9).
- **Le passage au banc soigne ce qu'il doit, et rien d'autre** :
  `test_passage_au_banc_retire_les_etats_mais_conserve_tout_le_reste_r86` (états retirés ;
  énergies, Outil, compteurs, pile conservés).
- **Banc vide après K.O. = fin avec la bonne raison** :
  `test_promotion_banc_vide_termine_la_partie_avec_la_bonne_raison_r89` (vainqueur = adversaire,
  `raison_fin = plus_de_pokemon`, `assert_invariants` OK).
- **Pureté / rejouabilité** : état d'entrée figé inchangé après `appliquer` ; rejeu d'une partie
  avec retraite redonne l'état exact ; round-trip JSON de l'action et de l'événement ; reprise
  après sérialisation. Chaque test de règle cite son `R-x.y`, et deux tests vérifient que tous
  ces identifiants existent dans `docs/jeu/REGLES.md`.

## Écarts au plan / décisions

- **Pas de câblage dans le générateur d'actions.** Lister la retraite comme coup jouable exige le
  **coût de retraite imprimé** (catalogue), absent du moteur pur. Conforme à la frontière déjà
  documentée (`generateur.py`, `DEGATS.md`) : la `Famille` retraite arrive avec `j-cartes-pokemon`
  (que ce lot débloque). Les transitions, elles, sont bien livrées et journalisées.
- **La mise K.O. (défausse, récompenses, R-13) reste à `j-ko-recompenses`.** Ce lot fournit la
  **promotion** et la **défaite au banc vide** ; `j-ko-recompenses` laissera l'Actif à `None` puis
  empruntera `promouvoir`. `RAISON_PLUS_DE_POKEMON` est posée ici et réutilisable par ce lot.
- **Enregistrement des transitions** : fait **depuis `banc/mouvements.py`** (et non depuis
  `journal.transitions`) pour éviter un cycle d'import (`banc` dépend du journal). `pbm_game`
  importe `banc` à son chargement pour garantir que `appliquer` connaît toujours ces actions.
  Vérifié sans cycle dans les trois ordres d'import (banc d'abord, journal d'abord, regles seul).

## Reste à faire (hors périmètre de ce lot)

- `j-cartes-pokemon` : coût de retraite depuis le catalogue + `Famille` retraite dans le
  générateur + la carte d'appât qui déclenche l'échange forcé.
- `j-ko-recompenses` : détection et défausse du K.O., récompenses, conditions de victoire — qui
  branchera la promotion livrée ici.
- `j-etats-speciaux` : les cinq états (ce lot consomme déjà `ENDORMI`/`PARALYSE` pour la garde de
  retraite R-8.4).

## Sécurité / secrets

Aucun secret. Moteur pur : aucune route, aucune base, aucun `user_id` — le contrôle d'accès
croisé ne s'applique pas à ce lot (il s'appliquera au service de parties, piste J-SRV).
