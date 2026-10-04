# Compte rendu — `j-effets-catalogue-compilation`

**Lot** : Du catalogue aux cartes jouables — compilation, versions et errata.
**Jalon** : J2 (toutes les cartes du deck vraiment jouées). **Piste** : Effets & cartes.
**Machine** : travail sur **chimera** (WSL Ubuntu-24.04), pilotage depuis **devAI**.
**Statut** : livré (recette locale chimera verte, CI GitHub faisant foi sur la PR).

## Résumé

Livré le **pont entre le catalogue et le moteur** : une table `card_scripts` qui relie un **texte
d'effet** (et non une carte) à un **script DSL**, plus le chargeur qui résout un deck en scripts
validés et **refuse** une carte non scriptée avant la mise en place (D9), la détection d'errata qui
fait repasser « à revoir » un script dont le texte a changé, et le regroupement par texte identique
qui divise par plus de deux le nombre de scripts à écrire. Aucun script de carte réel n'est écrit
ici (c'est `j-effets-assistance-ia` et les lots de cartes, priorisés par DJ2) : ce lot livre la
**mécanique** dans laquelle ils se rangeront, et son outillage.

Le moteur `pbm_game` reste **pur** : tout ce qui lit la base vit dans `pbm_api.jeu.scripts`.

## Livrables

- **Table & migration** : `apps/api/src/pbm_api/models/card_scripts.py` (`CardScript` + les statuts
  `scripte`/`non_supporte`/`a_revoir`), migration `c3a7f1e9d2b4_card_scripts` (additive, une seule
  tête alembic conservée, `down_revision = b2c3d4e5f6a7`). Clé : `text_fingerprint` unique
  (empreinte du texte source) ; colonnes `source_text`, `lang`, `dsl_version`, `script` (JSONB),
  `statut`, `author`, `validated_at`, `tests` (JSONB), `notes`.
- **Empreinte & extraction** (`jeu/scripts/empreinte.py`, pur) : normalisation (NFC, espaces, casse),
  empreinte SHA-256, et `effets_scriptables(card)` qui extrait les effets d'une carte au grain de
  l'effet (talent, attaque à effet, texte de Dresseur), dé-dupliqués dans la carte.
- **Regroupement** (`jeu/scripts/groupement.py`, pur) : `mesurer_groupement` — voie naïve vs voie
  groupée, part économisée (critère n°2).
- **Dépôt** (`jeu/scripts/depot.py`) : lire/enregistrer/valider un script (idempotent par empreinte).
- **Chargeur** (`jeu/scripts/chargeur.py`) : `refus_scripts_deck` / `refus_scripts_cartes` — résout
  un deck, recharge chaque script `scripte` par l'interprète (`charger_programme`), refuse et nomme.
- **Errata** (`jeu/scripts/errata.py`) : `detecter_errata` — un script `scripte` dont le texte source
  a disparu du catalogue repasse « à revoir » (mode `--a-blanc` disponible).
- **Branchement** : `pbm_api.games.entry.verifier_deck` ajoute le contrôle des scripts (D9, J2) après
  la compilation ; il mord donc à l'entrée de la file **et** au lancement (`verifier_lancable`),
  avant la mise en place.
- **Commande de maintenance** : `apps/api/scripts/scripts_effets.py` — `lister`, `importer`,
  `valider`, `diffuser`, `errata`, `mesurer`.
- **Tests** : `tests/test_card_scripts_empreinte.py` (8 tests purs) et
  `tests/test_card_scripts_chargeur.py` (10 tests sur base).
- **Doc** : `docs/jeu/COMPILATION.md` (fiche durable), entrée dans la carte des fiches de `CLAUDE.md`.

## Critères d'acceptation — preuves

1. **Une carte dont le texte a changé ne se joue plus avec l'ancien script : elle passe « à revoir »
   et le deck le dit.** → ✅ `test_errata_texte_change_refuse_le_deck_et_bascule_le_script` : un
   script `scripte` pour « Piochez 2 cartes. », puis le texte de l'attaque devient « Piochez 3
   cartes. » → `refus_scripts_deck` refuse la carte (nouvelle empreinte sans script) ET
   `detecter_errata` fait repasser l'ancien script `a_revoir` (`validated_at` remis à nul).
2. **Le regroupement réduit mesurablement le nombre de scripts à écrire (chiffre publié).** → ✅
   `test_regroupement_reduit_le_nombre_de_scripts` (pur) + **mesure sur le catalogue de référence
   `pbm_catalogue_ref` (22 653 cartes, 04/10/2026)** : 19 723 cartes porteuses d'effet ;
   **28 407** couples (carte, effet) → **12 153** textes distincts → **16 254 scripts économisés,
   57,22 %** (`uv run python scripts/scripts_effets.py mesurer`).
3. **Le lancement d'une partie avec une carte non scriptée est refusé avant la mise en place, jamais
   en plein milieu.** → ✅ `test_lancement_refuse_carte_non_scriptee_avant_mise_en_place` :
   `verifier_lancable` (appelé par le lancement *avant* `creer_partie`/`demarrer_partie`) lève
   `DeckInjouable` ; le compteur de parties `games` est inchangé — aucune partie fantôme.

Garde du risque nommé (« script manquant → effet neutre ») : il n'existe **aucun** repli neutre.
Un effet absent, `a_revoir`, `non_supporte` ou de version illisible bloque la carte et le dit
(`test_carte_a_effet_sans_script_refusee`, `test_script_a_revoir_ou_non_supporte_refuse`,
`test_script_version_illisible_refuse`). Une carte sans effet reste jouable sans aucun script
(`test_deck_sans_effet_jouable_sans_script`). Accès croisé préservé : le deck d'autrui reste 404
avant tout contrôle de script (`test_verifier_deck_autrui_404_avant_tout`).

## Preuves d'exécution (chimera, base de test isolée `pbm_jeff_cat_test`)

- `uv run ruff check .` (apps/api) → **All checks passed!**
- `uv run alembic heads` → **une seule tête** `c3a7f1e9d2b4` ; `alembic upgrade head` applique la
  migration proprement sur une base neuve.
- `uv run pytest tests/test_card_scripts_empreinte.py tests/test_card_scripts_chargeur.py` →
  **18 passed**.
- Régression (chemins touchés par `verifier_deck`) : `test_games_service`, `test_lancement_service`,
  `test_lancement_routes`, `test_jeu_catalogue`, `test_game_access`, `test_games_routes` →
  **46 passed** (les decks de cartes vanille restent jouables sans aucun script).
- `scripts/scripts_effets.py mesurer` contre `pbm_catalogue_ref` (lecture seule) → chiffres
  du critère n°2 ci-dessus.

## Écarts / limites assumées (D9, jamais masquées)

- **Aucun script de carte réel n'est écrit.** Priorité DJ2 (cartes possédées, puis les plus
  fréquentes) : c'est le travail de `j-effets-assistance-ia` et des lots de cartes. Ce lot livre le
  registre, le chargeur, l'errata, le regroupement et l'outillage — pas le contenu.
- **« Par langue »** (mission point 1) : le catalogue range le texte d'effet **brut** (fr, repli en)
  sans étiquette de langue fiable par champ. L'empreinte porte donc sur le texte normalisé seul
  (deux langues = deux octets = deux empreintes, elles ne se confondent jamais) ; `lang` est une
  **métadonnée** de traçabilité posée par celui qui enregistre le script, pas une clé d'appariement.
- **Dégâts variables sans texte** (« 20× » avec `effect` vide) : le grain de ce lot est le **texte**
  d'effet. Une attaque à dégâts variables mais sans texte relève de `j-cartes-attaques-effets`,
  nommé ; elle n'est pas avalée en silence (l'adaptateur `jeu/catalogue` la marque déjà).
- **`non_supporte`** : prévu dans le modèle et le chargeur (refus nommé), mais aucune carte n'y est
  encore classée (aucun script écrit).

## Reste à faire (hors lot)

Lots débloqués : `j-effets-assistance-ia` (écrire les scripts sous contrôle IA), et
`j-effets-couverture-outil` (le tableau de ce qui manque pour rendre un deck jouable, et pour qui).
Le savoir durable est dans `docs/jeu/COMPILATION.md`.
