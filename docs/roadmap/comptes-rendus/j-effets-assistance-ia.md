# Compte rendu — `j-effets-assistance-ia`

**Jalon J2 · piste Effets & cartes · décision DJ8.** Assistance IA : proposer le script d'une carte,
jamais le valider seule. Lot exécuté sur **chimera** (couloir J-EFF), piloté depuis **devAI**.

## Résumé

L'IA propose, pour chaque texte d'effet non scripté, **un script DSL ET ses cas de test**. Le script
n'entre en jeu (`scripte`) **que si ses tests passent ET** qu'une **seconde IA, chargée de le
contredire, l'a approuvé** — sans relecture humaine carte par carte (DJ8). Un **rapport par famille**
est produit pour JF (qui peut retirer une famille d'un mot). La clé est la **clé plateforme**, jamais
celle d'un utilisateur. Budget cumulé plafonné à **50 €**, coût journalisé par carte, reprise après
interruption. **Sans clé**, le lot livre l'outillage, ses tests et une mesure sur **fournisseur
factice**, sans dépense (livré dans cet état : aucune dépense réelle engagée par ce lot).

Le garde-fou central, conforme au risque nommé dans la fiche : ce n'est **pas** la confiance
annoncée par le modèle qui active un script, mais l'**exécution réelle** (les essais rejoués contre
le moteur) et la **cohérence maison** (l'effet ne crée ni ne détruit de carte, l'état reste valide).

## Livrables

**Moteur pur (`apps/game`, `pbm_game`)**
- `effets/dsl/essais.py` — exécute un essai de script (`construire` → `executer_programme`),
  contrôle la **cohérence maison** (conservation des cartes R-3.1, invariants R-3), et `verifier_script`
  (chargement DSL + tous les essais + cohérence). Pur, aucune E/S.
- `tests/test_dsl_essais.py` — 9 cas (R-3.1, R-3, R-5.1, R-10.6).

**Assistance (`apps/api`, `pbm_api.jeu.scripts.assistance`)**
- `familles.py` — classe un effet par famille (grain du rapport et du veto JF) — pur.
- `gabarit.py` — prompts proposeur/contradicteur ; **grammaire dérivée du vocabulaire réel du
  moteur** (ne peut pas dériver du langage) — pur.
- `fournisseur.py` — aller-retour IA : `AnthropicGenerateur` (API Messages, clé plateforme jamais
  journalisée) et `FournisseurFactice` (déterministe, sans dépense) ; parsing strict (Pydantic).
- `pricing.py` — coût d'un appel au **tarif standard** (= 2 × le tarif Batch de `insights_batch`,
  source unique) : l'assistance appelle l'API synchrone, pas la remise Batch.
- `budget.py` — grand livre JSON : dépense cumulée, coût par carte, **reprise** par empreinte.
- `verification.py` — la **porte DJ8** (pure) : `scripte` ssi tests verts ET contradicteur approuve ;
  sinon `non_supporte` (l'IA a déclaré l'effet hors langage) ou `a_revoir` (nommé).
- `runner.py` — orchestration d'un passage : sélection **priorité DJ2** (possédées d'abord, puis
  fréquentes), propose → teste → (si vert) contredit → décide → écrit, plafond, reprise, rapport par
  famille + mesures de rendement.
- `scripts/assistance_scripts_ia.py` — CLI : lit la clé (fichier chmod 600 / env / stdin), bascule
  sur le factice sans clé en le disant, refuse (fail-closed) un passage réel sans taux de change.

**Registre & base**
- `models/card_scripts.py` — colonnes de revue (`review_tests_ok`, `review_contradicteur`, `famille`,
  `confidence`, `cost_eur`) + **contrainte CHECK `ck_card_scripts_scripte_gate`** : un `scripte`
  exige programme + date de validation + tests verts.
- `jeu/scripts/depot.py` — `enregistrer_script` étendu (champs de revue ; `review_tests_ok=True` par
  défaut pour un `scripte`, préservant les imports/validations d'avant DJ8).
- `migrations/versions/c9d4e7a1b3f8_card_scripts_assistance.py` — colonnes + backfill + CHECK.
- `config.py` — `assistance_budget_eur=50.0`, `assistance_model="claude-haiku-4-5"`.

**Doc** : `docs/jeu/ASSISTANCE-IA.md`.

## Preuves

- **Moteur** : `uv run pytest` sur `apps/game` → **952 passés** (dont les 9 de `test_dsl_essais.py`).
  `ruff check .` propre.
- **API** : `ruff check .` propre. Suite ciblée (assistance + card_scripts) sur une base migrée à
  neuf → **65 passés** :
  - `test_assistance_{familles,gabarit,fournisseur,budget,verification}.py` (purs) ;
  - `test_assistance_runner.py` — un effet exprimable → `scripte` (`review_tests_ok=True`,
    `review_contradicteur="approuve"`, `famille="pioche"`, `validated_at` posé), un effet hors langage
    → `non_supporte` (script NULL), **plafond** qui arrête le passage, **reprise** (scripte non
    re-sélectionné ; `a_revoir` sauté par le grand livre) ;
  - `test_card_scripts_gate_constraint.py` — un INSERT direct d'un `scripte` sans preuve est
    **refusé par la base** (IntegrityError) ; `enregistrer_script` remplit la preuve et passe ;
    `non_supporte` sans preuve reste permis ;
  - `test_card_scripts_chargeur.py` / `test_script_coverage.py` / `test_card_scripts_empreinte.py` —
    **non-régression** des lots précédents, verts avec la nouvelle contrainte.
- **Migration** : `alembic upgrade head` applique la chaîne jusqu'à `c9d4e7a1b3f8` ; `\d card_scripts`
  montre les colonnes et la contrainte `ck_card_scripts_scripte_gate`.
- **La CI GitHub fait foi** : elle lance les trois jobs (web/api/game) sur un schéma migré à neuf.

## Critères d'acceptation

- [x] **Aucun script n'entre en jeu sans tests verts ET validation — vérifié par une contrainte en
  base** : `ck_card_scripts_scripte_gate` (prouvé par `test_card_scripts_gate_constraint.py`). DJ8
  remplace la relecture humaine carte par carte par la 2ᵉ IA contradictrice + le rapport/veto par
  famille.
- [x] **Budget plafonné respecté et coût par carte publié** : grand livre + mesures (`budget.py`,
  `rapport_texte`), plafond prouvé par `test_plafond_arrete_le_passage`.
- [x] **Interruption sans perte ni retraitement** : grand livre sauvé après chaque effet, reprise au
  grain de l'empreinte (prouvé par les deux tests de reprise).

## Écarts au plan

- **Section 3 du prompt (file de relecture humaine) remplacée par DJ8** : la décision prise par JF le
  04/10 supprime la relecture humaine carte par carte au profit d'une 2ᵉ IA contradictrice + rapport
  par famille (droit de veto de JF). Appliqué à la lettre.
- **Aucune dépense réelle dans ce lot** : la clé plateforme vit sur devAI
  (`~/.pokeboy-secrets/platform-anthropic-key`) ; conformément à DJ8, le lot livre l'outillage + tests
  + mesure sur fournisseur factice. Le passage réel (50 €) est une **opération à lancer depuis devAI**.
- **Texte EN par effet** non alimenté (le registre range un texte par empreinte) : le prompt accepte
  un texte EN quand on en a un ; l'alimenter est une amélioration future.

## Reste à faire (hors périmètre de ce lot)

- Lancer le **passage réel** depuis devAI avec la clé plateforme (plafond 50 €, priorité DJ2), puis
  remettre le **rapport par famille** à JF pour arbitrage (retrait éventuel d'une famille).
- Suivre l'errata : un texte modifié repasse déjà `a_revoir` (lot précédent) et redevient candidat.

## Note d'exploitation

La base de test partagée de chimera (`pbm_v2_catalogue_complet_test`) était **périmée** (schéma
d'avant `coach_ia`, colonne `users.coach_actif` absente) — sans rapport avec ce lot. La vérification a
été faite sur une base migrée à neuf (`pbm_jeff_test`, `alembic upgrade head`). Rafraîchir la base de
test partagée de chimera serait utile aux prochains lots.
