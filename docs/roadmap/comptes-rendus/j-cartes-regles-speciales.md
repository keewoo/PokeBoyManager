# Compte rendu — `j-cartes-regles-speciales`

**Règles de cartes particulières : ACE SPEC, Radiant, VSTAR, GX, Prisme Étoile.**
Jalon J2 — « toutes les cartes du deck sont vraiment jouées ». Couloir J-EFF, exécuté sur chimera,
piloté depuis devAI.

## Résumé

Les règles R-15 qui cassent les règles générales sont portées **au deck** (service de légalité) et
**en partie** (moteur). Chaque règle appliquée cite son `R-x.y`. Aucun effet approximé (D9), aucun
repli silencieux, aucun secret.

## Livrables

### Au deck (`apps/api`, logique pure, source unique serveur+écran)
- `pbm_api/decks/regles_speciales.py` (NOUVEAU) : classifie une carte dans sa catégorie à règle
  particulière à partir des **marqueurs structurés** du catalogue (jamais le nom, R-13.7).
- `pbm_api/decks/legality.py` : limites R-2.3 (1 ACE SPEC), R-2.4 (1 Radiant), R-2.7 (1 Prisme
  Étoile *par nom*), R-2.8 (1 ★ par deck), et R-15.22 (Rule Box inconnu → **refusé**, jamais deviné).
  Nouveaux codes : `ace_spec_limit`, `radiant_limit`, `prism_star_limit`, `star_limit`,
  `unknown_rule_box`.
- `pbm_api/decks/service.py` : `DeckCardFact` + requête portent désormais `rule_marker` et
  `prize_marker`.

### En partie (`apps/game`, moteur pur)
- `combat/pouvoirs_uniques.py` (NOUVEAU) : usage **une fois par partie** (attaque GX R-15.3, VSTAR
  Power R-15.6), suivi dans l'état du **joueur** (`Joueur.pouvoirs_uniques_utilises`), pas la carte.
- `state/modele.py` + `state/serialisation.py` : champ `pouvoirs_uniques_utilises` sérialisé
  (aller-retour JSON) → l'interdiction **survit à un F5** et au rejeu.
- `cartes/modele.py` : `AttaqueDef.pouvoir_unique` (+ validation D9, round-trip JSON).
- `combat/attaque.py` : garde dans `resoudre_attaque_declaree` — un second pouvoir lève (R-15.3/
  R-15.6), l'usage est marqué après paiement du coût.
- `actions/familles_jeu.py` : `FamilleAttaquer` ne propose plus un pouvoir dépensé, et porte
  `pouvoir_unique` dans la fiche d'attaque.
- `combat/ko.py` + `combat/fin.py` : `router_cartes_ko` — un **Prisme Étoile** K.O. envoie sa carte ◇
  en **zone perdue** (R-15.18/R-3.8), ses énergies/Outil à la défausse (R-13.2).

### Documentation
- `docs/ARCHITECTURE.md` : section « Cartes à règle particulière » (repères serveur + moteur, écart
  ACE SPEC).

## Preuves

- Moteur (`apps/game`) : **986 tests verts** (`uv run pytest -q`). Dont nouveaux
  `test_pouvoirs_uniques.py` (garde, **2e VSTAR Power refusé en partie**, survie à un F5) et
  `test_cartes_regles_speciales.py` (**Prisme Étoile K.O. → zone perdue**, zone perdue sans retour).
- Service (`apps/api`) : sur une base **fraîche** (`alembic upgrade head`) + redis —
  `test_deck_regles_speciales.py` (**2 ACE SPEC refusées**, 2 Radiant, 2 Prisme même nom, 2 ★,
  Rule Box inconnu refusé) + `test_deck_routes.py` + `test_script_coverage_db.py` = 28 verts ;
  sélection `deck/legal/matchmaking/lancement/invitation` = **201 verts**.
- `ruff check .` vert sur `apps/game` et `apps/api`.
- La CI GitHub Actions fait foi (base éphémère + migrations) ; verte sur la PR.

## Critères d'acceptation

- [x] Chaque règle particulière est vérifiée **au deck** (légalité) ET **en partie** (moteur).
- [x] L'usage unique par partie **survit à une reprise après F5** (test de sérialisation).
- [x] Une carte portant une règle particulière **inconnue** est **refusée au deck** avec sa raison
  (R-15.22 au deck ; `valider_pouvoir`/marqueur inconnu dans le moteur).

## Écarts au plan

- **ACE SPEC absent du catalogue importé.** Mesuré sur `pbm_catalogue_ref` (22 653 cartes, 04/10) :
  aucune carte ne porte `rule_marker = "ACE SPEC"` (ni le texte libre « ACE SPEC »). La règle R-2.3
  est implémentée et testée mais **ne mord sur aucune carte réelle** tant que l'import ne renseigne
  pas ce marqueur. Documenté dans le module et dans `ARCHITECTURE.md` — jamais masqué (D9).

## Reste à faire (hors périmètre, nommé)

- **Renseigner le marqueur ACE SPEC à l'import** (`catalog.import_service`), seule façon de rendre
  R-2.3 effective sur du réel.
- **Jouer réellement un VSTAR Power / une attaque GX** : la garde est branchée sur la résolution
  d'attaque et la génération des coups ; le remplissage de `AttaqueDef.pouvoir_unique` par
  l'adaptateur catalogue (quelle attaque EST un pouvoir unique) viendra avec les lots de cartes et
  `j-effets-dsl` qui scriptent ces attaques.
- **VSTAR Power en tant que talent** (et non attaque) : la garde est générique (clé `vstar`), mais
  aucune action « utiliser un talent » n'existe encore au J2 — à brancher quand elle arrivera.
