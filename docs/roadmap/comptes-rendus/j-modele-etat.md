# Compte rendu — `j-modele-etat` — État d'une partie : zones, attachements, compteurs, vues par joueur

**Statut visé : fusionné dans `main` après CI verte.**
Piste Règles & moteur · couloir J-MOT (devAI) · jalon J1 · palier 1 · amont `j-regles-reference` (intégré) · 01/10/2026.

## Résumé

Deuxième lot du moteur `pbm_game` : l'**objet d'état** que toute la suite manipule. Des
dataclasses **figées et pures** (aucune E/S, aucune méthode de mutation), leur
**sérialisation JSON bidirectionnelle** exacte et déterministe, la **projection par
joueur** `vue(etat, joueur)` qui ne laisse fuir aucune information cachée, et des
**invariants vérifiables**. Tout respecte la séparation information publique / information
cachée dès la structure — pour que l'anti-triche soit une propriété de l'objet, pas une
rustine posée plus tard (le gain nommé par la mission).

## Livrables

- **`apps/game/src/pbm_game/state/`** — nouveau sous-paquet pur :
  - `modele.py` — `Carte`, `PokemonEnJeu`, `Joueur`, `Tour`, `EtatPartie` (toutes `frozen`),
    constantes de règle (5 états spéciaux, orientation/marqueur R-11.8, phases R-5,
    `SCHEMA_VERSION`), helpers purs `orientation()` (dérivée, jamais stockée) et
    `carte_active()`.
  - `serialisation.py` — `vers_json` / `depuis_json`, round-trip exact, sortie
    déterministe (états triés), refus bruyant d'une structure ou d'une `schema_version`
    invalide.
  - `projection.py` — `vue(etat, joueur)` : zones cachées réduites à un **nombre**.
  - `invariants.py` — `verifier` / `assert_invariants` / `toutes_les_cartes` /
    `total_cartes_joueur`, exception `InvariantViole`.
- **Tests** (`apps/game/tests/`) : `test_state_serialisation.py`,
  `test_state_projection.py`, `test_state_invariants.py`, `test_state_purete.py`, et la
  fabrique d'états aléatoires `fabrique_etats.py` (non collectée par pytest).
- **`docs/jeu/ETAT.md`** — fiche durable du modèle d'état.
- `pbm_game/__init__.py` mis à jour (mention du lot).

## Preuves

- `uv run ruff check .` → **All checks passed** (Python 3.12, `apps/game`).
- `uv run pytest -q` → **47 passed in 0.33s**.
- **Non-fuite anti-triche** : `test_vue_ne_laisse_fuir_aucune_carte_cachee` parcourt la vue
  JSON de chaque joueur sur **300 états aléatoires** et vérifie qu'aucun `instance_id`/`ref`
  des pioches (ordre inclus), des récompenses et de la main adverse n'y apparaît.
- **Round-trip** : `test_round_trip_identique_sur_etats_aleatoires` — `depuis_json(vers_json(e)) == e`
  sur 300 états.
- **Invariants** : `test_etats_aleatoires_sont_sains` (300 états), + un test ciblé par
  invariant citant sa règle (R-3.2, R-3.3, R-3.4, R-2.1, R-11.8, R-11.1, R-10.4, R-5,
  carte en double).
- **Pureté** : `test_import_state_ne_tire_aucune_dependance_lourde` (aucun fastapi /
  sqlalchemy / httpx / boto3 / redis dans `sys.modules` après import) ; l'analyse statique
  de `test_corpus_regles.py` couvre déjà `state/` via `rglob`.
- « Test qui échoue sans le changement » : toute la suite `test_state_*` échoue à l'import
  sans le sous-paquet `pbm_game.state` qui n'existait pas.

## Critères d'acceptation

- [x] `vue(etat, joueur)` ne laisse fuir aucune carte cachée (test de parcours, 300 états).
- [x] Invariants vérifiables après chaque action (`assert_invariants`, utilisé par la suite).
- [x] Un état complet se sérialise, se relit et se compare à l'identique.
- [x] Aucune dépendance à FastAPI / SQLAlchemy / réseau (test d'import + analyse statique).

## CI

La CI fait foi. Le job `game` de `.github/workflows/ci.yml` exécute déjà
`uv sync --locked` + `uv run ruff check .` + `uv run pytest -q` dans `apps/game` : les
nouveaux modules et tests y sont ramassés sans retouche du workflow (`testpaths=["tests"]`).
Aucune modification du workflow n'était donc nécessaire — rien n'est « vert sur rien ».

## Écarts au plan

Aucun écart de périmètre. Deux choix d'implémentation à signaler :

- **Tests de propriété sans `hypothesis`** : un générateur déterministe `random.Random(seed)`
  balaie des centaines d'états plutôt que d'ajouter une dépendance dev et de reverrouiller
  `uv.lock`. L'esprit (état arbitraire → propriété tenue) est respecté.
- **`schema_version` figée à 1** ; `depuis_json` refuse toute autre valeur. L'évolution du
  schéma (migrations) viendra quand un second format existera.

## Reste à faire

Rien pour ce lot. Il débloque `j-aleatoire-determinisme` (mélange/pile ou face/graine) et,
plus loin, le journal d'actions et la résolution, qui consommeront cet objet.
