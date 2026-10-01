# Compte rendu — `j-journal-actions`

**Lot** : Journal d'actions — la partie est sa suite de coups, pas son état.
**Piste** : Règles & moteur (couloir J-MOT, devAI) · **Jalon** J1 · P0.
**Branche** : `roadmap/j-journal-actions` · **Machine** : devAI (worktree `../wt-j-journal-actions`).

## Résumé

Livré l'**ossature du journal d'actions** du moteur `pbm_game`, en Python pur (aucune E/S,
ni HTTP, ni base, ni React) : une partie est désormais un **état initial + une graine + un
journal numéroté**, et rejouer le journal redonne *exactement* le même état, contrôlé par
une **empreinte au coup près**. Compaction par instantané + queue pour ne pas rejouer 400
coups à chaque reconnexion. Format sérialisé **versionné** (`JOURNAL_VERSION = 1`), refus
d'une version inconnue. Les trois critères d'acceptation sont prouvés par tests (dont la
simulation de **1 000 parties**).

Conformément à D9 (« un effet non implémenté n'est jamais approximé »), ce lot ne livre que
des transitions **entièrement mécaniques** — mélange (R-4.1), pioche (R-5.2), avancée de
phase/tour (R-5.1/R-12.1) — qui ne demandent aucune donnée de carte. Les actions riches
(énergie, évolution, attaque, Dresseurs) arriveront avec les lots de résolution qui ont le
catalogue, et s'enregistreront dans le **même** registre d'actions. Un `action.type`
inconnu est refusé, jamais deviné.

## Livrables

- **Paquet `pbm_game.journal`** (`apps/game/src/pbm_game/journal/`) :
  - `modele.py` — `Action`, `Evenement`, `Entree`, `Partie`, `Instantane`, `JOURNAL_VERSION`.
  - `empreinte.py` — `empreinte(etat)` : SHA-256 d'une forme JSON canonique de l'état.
  - `transitions.py` — `appliquer(etat, action, rng) -> (etat, evenements)` (pur côté état),
    `jouer()`, `partie_neuve()`, le `REGISTRE` et les trois transitions mécaniques.
  - `rejeu.py` — `rejouer()`, `compacter()`, `reprendre()`/`reprendre_partie()`, `RejeuDivergent`.
  - `serialisation.py` — `*_vers_json` / `*_depuis_json` versionnés (round-trip exact).
  - `debogage.py` — `decrire_entree()` : entrée lisible, identifiants résolus en noms.
- **Tests** : `apps/game/tests/test_journal.py` (22 tests, dont la simulation de 1 000 parties).
- **Doc** : `docs/jeu/JOURNAL.md` — format et mécanique pour une réimplémentation indépendante.
- Docstring de `pbm_game/__init__.py` mise à jour (mention du lot).

## Preuves

- **Suite `game` verte** sur devAI (`UV_PYTHON=3.12`) : `uv run ruff check .` → *All checks
  passed!* ; `uv run pytest -q` → **92 passed** (dont 22 nouveaux). La CI GitHub `game`
  (ruff + pytest sur `apps/game`) exécute ces tests — elle fait foi.
- **Critère 1 — rejouabilité sur 1 000 parties** : `test_mille_parties_rejouees_a_l_identique`
  simule 1 000 parties (1 à 12 coups), compare `vers_json(rejouer(partie)) == vers_json(etat_final)`
  et vérifie que les empreintes enregistrées égalent celles observées en avant de jeu.
  `test_rejeu_mord_sur_une_empreinte_truquee` / `_un_evenement_truque` prouvent la détection
  **au coup près** (`RejeuDivergent.numero == coup fautif`).
- **Critère 2 — lisibilité** : `test_entree_lisible_resout_les_noms_de_cartes` (noms affichés),
  `..._signale_un_nom_inconnu_sans_le_masquer` (id manquant rendu explicite, pas de repli).
- **Critère 3 — compaction** : `test_reprise_depuis_instantane_egale_le_rejeu_complet` compare,
  pour chaque point de coupe `k ∈ [0, n]`, `reprendre_partie(partie, compacter(partie, k))` au
  rejeu complet, état et empreinte ; `test_instantane_incoherent_est_refuse` (cache non cru).
- **Pureté** : `test_import_journal_ne_tire_aucune_dependance_lourde` + le grep statique AST de
  `test_corpus_regles.py` (scanne tout `src/pbm_game`) — aucun `random`, aucun module interdit.
- **Test qui échoue sans le changement** : tout `test_journal.py` importe `pbm_game.journal`,
  inexistant avant ce lot → ImportError sans le changement, 22 passed avec.

## Écarts au plan

- **Périmètre volontairement restreint aux transitions mécaniques** (D9). Le lot est
  l'infrastructure du journal ; il ne génère pas les actions légales (`j-actions-legales`),
  ne persiste pas (`j-partie-service`) et ne résout pas les effets de cartes. Ce n'est pas
  une réduction subie : c'est la ligne de D9 (« le jeu préfère dire *je ne sais pas jouer
  cette carte* que de la jouer de travers »). Documenté dans `docs/jeu/JOURNAL.md` § « Ce que
  le lot ne fait pas ».
- **Horodatage fourni par l'appelant** (le moteur est pur, sans horloge) : c'est une donnée
  d'entrée de l'entrée, relue au rejeu, jamais recalculée.
- Aucune modification du workflow CI : le job `game` existant couvre déjà `apps/game`
  (ruff + pytest) et exécute les nouveaux tests. Aucune dépendance ajoutée → `uv.lock` inchangé.

## Reste à faire (hors lot)

- `j-actions-legales` : générateur d'actions légales (ce qui est jouable et pourquoi le reste
  ne l'est pas) — s'appuiera sur `REGISTRE` et les invariants d'état.
- `j-partie-service` : créer/persister/reprendre/expirer une partie (la compaction est prête).
- `j-replay` : rejouer coup par coup et partager (le journal + `decrire_entree` sont prêts).
- Les lots de résolution ajouteront leurs transitions (énergie, évolution, attaque, Dresseurs).
