# Compte rendu — `j-degats-resolution`

**Lot** : Attaque et dégâts — coût, faiblesse, résistance, modificateurs.
**Piste** : Règles & moteur (couloir J-MOT, devAI) · **Jalon** J1 · P0 · palier 6.
**Branche** : `roadmap/j-degats-resolution` · **Machine** : devAI (worktree `../wt-j-degats-resolution`).

## Résumé

Livré le **paquet `pbm_game.combat`**, en Python pur (aucune E/S, ni HTTP, ni base, ni React) :
la vérification du **coût d'une attaque** (R-9.2) et le **calcul des dégâts** dans l'ordre strict
du corpus (R-10.1). C'est le geste central du jeu et le plus souvent faux — l'ordre des
opérations entre faiblesse, résistance et modificateurs change le résultat. Chaque étape est
tracée et nommée, un **détail de calcul** lisible est produit (« 60 base, ×2 faiblesse, −30
résistance = 90 », R-10.9), et les dégâts se posent en **compteurs**, jamais en PV soustraits
(R-10.4).

Conformément à **D9**, le lot livre **le calcul et ses crochets**, pas les données de carte : le
moteur reçoit des **descripteurs** (`CoutAttaque`, `Faiblesse`, `Resistance`, `Modificateur`)
déjà extraits du catalogue — leur câblage depuis le catalogue est la couche suivante
(`j-cartes-pokemon`, que ce lot débloque). Les listes de modificateurs des étapes 2 et 5 sont
donc **vides au jalon J1** : ce sont des points d'accroche nommés pour les effets à venir, aucun
n'est approximé.

## Livrables

- **Paquet `pbm_game.combat`** (`apps/game/src/pbm_game/combat/`) :
  - `modele.py` — descripteurs figés et sérialisables : `CoutAttaque` (colorés + incolores),
    `Faiblesse` (×2 par défaut, R-10.2), `Resistance` (−30 par défaut, R-10.3), `Modificateur`
    (opérations d'un ensemble fermé `ajout`/`multiplie`/`fixe`, chacun citant sa règle),
    `EtapeCalcul`, `ResultatDegats` (dégâts, compteurs, trace, détail, `arrete_avant_degats`).
  - `cout.py` — `cout_satisfait(cout, fournitures)` → `Verdict` : colorés payés par le type
    exact, incolores par n'importe quelle unité restante, énergies **multi-unités** comptées
    (R-9.2) ; refus toujours motivé citant **R-9.2**.
  - `resolution.py` — `resoudre_degats(...)` (l'ordre strict R-10.1), `poser_degats` /
    `poser_compteurs` (en compteurs, R-10.4/R-10.6), `evenement_degats` (le détail porté par
    le journal).
  - `__init__.py` — API publique.
- **Journal** : constante `EVT_DEGATS` (`journal/modele.py`), exportée par `pbm_game.journal`.
- **Tests** : `apps/game/tests/test_degats.py` — **35 cas** (voir « Preuves »).
- **Docs** : `docs/jeu/DEGATS.md` (nouvelle fiche) ; docstring du lot dans `pbm_game/__init__.py`.

## Preuves

- **Suite moteur verte** : `uv run pytest -q` dans `apps/game` → **171 passed** (35 nouveaux du
  lot + l'existant), `UV_PYTHON=3.12`. `uv run ruff check .` → **All checks passed!**
- **Les huit cas `degats-*` du corpus passent** (critère d'acceptation) : exécutés par la table
  `CAS_DEGATS` de `test_degats.py`, chacun citant son `R-x.y` et contrôlé contre les règles que
  le corpus lui attache. Un test de **couverture**
  (`test_tous_les_cas_de_degats_du_corpus_sont_couverts`) échoue si un cas `degats-*` du corpus
  n'a pas d'entrée exécutable — pas d'oubli silencieux.
  - `degats-faiblesse-x2` (R-10.2) : 60 → ×2 = 120.
  - `degats-resistance-moins-30` (R-10.3) : 50 → −30 = 20.
  - `degats-ordre-faiblesse-puis-resistance` (R-10.1/R-10.8) : 60 → ×2 = 120 → −30 = **90**
    (jamais (60−30)×2).
  - `degats-compteurs-pas-pv` (R-10.4) : pose vérifiée par `test_poser_degats_*`.
  - `degats-banc-sans-faiblesse-resistance` (R-10.5) : au banc, faiblesse **et** résistance
    présentes → 60 inchangé.
  - `degats-plancher-zero` (R-10.7) : 20 − 30 → plancher 0, aucun compteur.
  - `degats-faiblesse-sur-zero` (R-16.8) : base 0 → arrêt à l'étape 2, faiblesse **jamais**
    appliquée (`arrete_avant_degats`).
  - `degats-detail-journalise` (R-10.9) : détail exact de l'exemple du corpus.
- **Détail affiché dans le journal** (critère d'acceptation) : `evenement_degats` produit un
  `EVT_DEGATS` dont `donnees["detail"]` vaut « 60 base, ×2 faiblesse, −30 résistance = 90 », en
  valeurs JSON natives (test `test_evenement_degats_porte_le_detail_pour_le_journal`).
- **Dégâts au banc sans faiblesse ni résistance** (critère d'acceptation) :
  `test_degats_au_banc_ignorent_faiblesse_et_resistance` (60 au banc vs 120 à l'Actif).
- **Coût (R-9.2)** : 10 tests — gratuit, coloré exact/insuffisant, incolore payé par tout type,
  énergie multi-unités (Double Incolore = 2), énergie bi-type, unité incolore qui **ne paie
  pas** un symbole coloré, incolore insuffisant, surplus toléré, fourniture malformée qui
  **échoue bruyamment**.
- **Pureté** : `pbm_game.combat` n'importe ni HTTP, ni base, ni réseau — garanti par l'analyse
  statique existante (`test_source_du_moteur_n_importe_rien_d_interdit`), verte.
- **Le test échoue sans le changement** : `test_degats.py` importe `pbm_game.combat`, inexistant
  avant ce lot — la suite ne collecte pas sans lui.

## Écarts au plan

- Aucun sur le périmètre. Le coup d'attaque **listé** par le générateur d'actions et le câblage
  des descripteurs depuis le **catalogue** restent hors lot (D9) : ils appartiennent à
  `j-cartes-pokemon` (débloqué par ce lot). `declarer_attaque` reste donc tel que livré par
  `j-machine-tour` (il ne mécanise que « termine le tour ») ; sa résolution complète branchera
  `pbm_game.combat` quand le catalogue sera là.
- La table `docs/jeu/cas-de-regles.yaml` **n'a pas été modifiée** : les champs `entree`/`attendu`
  restent au lot `j-tests-regles` (son en-tête le réserve). Les cas de dégâts sont rendus
  exécutables par la table `CAS_DEGATS` du test, qui cite les mêmes `R-x.y` et se contrôle
  contre le corpus.

## Reste à faire (lots suivants)

- `j-cartes-pokemon` — extraire du catalogue les descripteurs (type d'énergie, coût, faiblesse,
  résistance, attaques) et brancher `pbm_game.combat` dans la résolution d'attaque + le
  générateur.
- `j-ko-recompenses` — lire `compteurs_degats ≥ PV` (R-13.1) pour les mises K.O., récompenses et
  conditions de victoire.
- Lots d'effets — remplir les modificateurs des étapes 2 et 5, chacun scripté et testé (D9).
