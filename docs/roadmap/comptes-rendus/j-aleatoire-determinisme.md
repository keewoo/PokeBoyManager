# Compte rendu — `j-aleatoire-determinisme`

**Aléatoire reproductible : mélange, pile ou face, et graine vérifiable.**
Couloir J-MOT (moteur pur), jalon J1. Session autonome sur devAI.

## Résumé

Le moteur dispose d'une source d'aléatoire **reproductible, vérifiable et journalisée**,
`pbm_game.rng`, en Python pur (aucune E/S dans le cœur). Trois propriétés, chacune testée :

1. **Encapsulation** — le hasard passe uniquement par un objet `Rng` reçu explicitement ;
   aucun appel à `random` nulle part dans le moteur, gardé par un test de grep AST sur
   tout le paquet `pbm_game`.
2. **Flux nommés indépendants** — chaque usage (mélange de chaque joueur R-4.1, pile ou
   face de début R-4.7, états spéciaux R-11.3/4/5, effets divers) tire dans son propre
   flux à compteur indépendant : ajouter un tirage dans un flux ne décale jamais la suite
   d'un autre — le piège explicite de la mission est écarté par construction.
3. **Engagement-révélation (commit-reveal)** — on publie `engagement(graine)` avant la
   partie, on révèle la graine à la fin ; `verifier_journal` recalcule chaque tirage et
   confirme qu'il est exactement le i-ème de son flux sous la graine, dans l'ordre, sans
   trou. Impossible de changer de graine ni de « rejouer jusqu'à un bon résultat ».

Mécanique : flux d'octets déterministe `HMAC-SHA256(graine, flux ‖ 0x00 ‖ indice ‖ sous_bloc)`,
entiers tirés sans biais par rejet, mélange Fisher–Yates. Un tirage = un incrément de
compteur, quel que soit le nombre d'octets consommés. Documentée pour réimplémentation
indépendante dans `docs/jeu/ALEATOIRE.md`.

## Livrables

- `apps/game/src/pbm_game/rng/__init__.py` — cœur pur : `Rng` (`pile_ou_face`, `entier`,
  `melanger`), flux nommés, journal (`Tirage`), `engagement`/`verifier_engagement`,
  `verifier_journal`/`rejouer_tirage`/`Anomalie`, sérialisation (`etat`/`depuis_etat`,
  `tirage_vers_json`/`tirage_depuis_json`).
- `apps/game/src/pbm_game/rng/__main__.py` — vérificateur commit-reveal en une commande
  (`python -m pbm_game.rng verifier <fichier.json>`), seul endroit du paquet à faire de
  l'E/S, volontairement isolé du cœur.
- `apps/game/tests/test_rng.py` — 27 tests couvrant les trois critères.
- `docs/jeu/ALEATOIRE.md` — fiche de mécanique (réimplémentation indépendante).
- `apps/game/README.md` et `pbm_game/__init__.py` — état à jour.

## Preuves

- **Critère : aucun aléatoire global** — `test_aucun_import_ni_appel_a_random_dans_le_moteur`
  (grep AST sur `src/pbm_game/**.py`). Vert.
- **Critère : rejouabilité ~100 parties** — `test_cent_parties_rejouees_a_graine_identique_donnent_un_etat_identique`
  : 100 graines `os.urandom(32)`, chaque partie simulée (mélange des 2 decks, qui commence,
  20 pile ou face d'états spéciaux, 5 entiers) rejouée deux fois → état final **et** journal
  JSON identiques. Vert.
- **Critère : vérification a posteriori outillée en une commande** — CLI testée de bout en
  bout :
  - honnête → `✅ Mélange vérifié`, sortie 0 ;
  - pile ou face retourné → `❌ ... résultat 'face' ne correspond pas à la graine (recalculé 'pile')`, sortie 1.
  - Le vérificateur mord aussi sur un mélange réordonné, un tirage effacé (indice hors
    séquence) et une graine changée (`test_verificateur_mord_sur_*`).
- **Suite complète** : `uv run pytest -q` dans `apps/game` → **74 passed** (27 nouveaux +
  47 préexistants). `uv run ruff check .` → All checks passed. Python 3.12, sur devAI.
- **CI** : job `game` du workflow exécute déjà `uv sync --locked`, `ruff check .`,
  `pytest -q` dans `apps/game` — les nouveaux tests y tournent sans modifier le workflow.
  Verdict de la CI GitHub sur la PR : **fait foi**.

## Sécurité / isolation

- Moteur pur : pas de route utilisateur, pas de base, pas de secret. Test d'import prouve
  qu'aucune dépendance lourde n'est tirée.
- La graine n'est jamais affichée ailleurs que par `graine_hex` (révélation volontaire de
  fin de partie) ; l'engagement est une empreinte SHA-256 à séparation de domaine.
  `verifier_engagement` compare en temps constant (`hmac.compare_digest`).

## Écarts au plan

Aucun. Les trois critères d'acceptation sont remplis avec preuve.

## Reste à faire (lots suivants, hors périmètre)

- Câbler le `Rng` au journal d'actions (`j-journal-actions`) et au lancement de partie
  (`j-lancement-partie`).
- Exposer engagement/révélation via l'API (`apps/api`) — le moteur fournit la brique
  (`engagement`, `graine_hex`, `etat()`), l'API la publie.
