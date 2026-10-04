# Compte rendu — `j-cartes-talents`

**Lot** : Talents — passifs, activés une fois par tour, déclenchés — et annulables
**Jalon** : J2 (Toutes les cartes du deck sont vraiment jouées) · piste Effets & cartes · couloir chimera
**Machine** : chimera (WSL Ubuntu-24.04), piloté depuis devAI · Python 3.12 · base `github/main` `36afc0a`

## Résumé

Les talents étaient « le vrai examen de passage de l'architecture d'effets » : trois natures
(continu, activé, déclenché), une annulation mutuelle à trancher, et un suivi « une fois par tour »
qui doit être **par Pokémon** et non par joueur. Le lot livre le **cadre** des talents, le branche
sur l'architecture d'effets déjà en place (producteurs continus, bus, pile) **sans la réécrire**,
et prouve le tout avec **cinq talents réels** de natures différentes.

Rien n'a été ajouté au socle : les talents continus passent par les producteurs de
`pbm_game.effets.continus`, les déclenchés par le bus de `pbm_game.effets.bus`, les activés par une
nouvelle action journalisée `activer_talent`. **Un seul portillon**, `talent_actif`, gouverne les
trois : en jeu, non neutralisé, non désactivé par un état — chaque refus **nommé**, jamais muet.

## Livrables

- `apps/game/src/pbm_game/effets/talents.py` — le cadre **pur** : natures, fiche `Talent`,
  `RegistreTalents`, le portillon `talent_actif`, la décision d'annulation `identites_neutralisees`,
  et les *builders gardés* `construire_registre_continus` / `construire_bus` qui branchent les
  talents continus et déclenchés sur l'architecture existante, chacun gardé par le portillon.
- `apps/game/src/pbm_game/effets/talents_actives.py` — la transition journalisée `activer_talent`
  (jumelle de `effets.objets`) : talent activé **une fois par tour, par Pokémon**, désactivé par un
  état spécial, éteint sous un verrou `talents_sans_effet` — chaque refus cite sa règle.
- `Tour.talents_actives_ce_tour` (state + sérialisation + drapeaux `talent_active_ce_tour` /
  `marquer_talent_active`) : le suivi « une fois par tour, par Pokémon », porté par l'état (donc
  sérialisé, donc survit à un F5), remis à vide à chaque tour neuf. **Rétro-compatible** : un état
  d'avant ce lot se relit sans migration (clé absente = aucun talent activé).
- `ACTION_ACTIVER_TALENT` / `EVT_TALENT_ACTIVE` + projecteur public + traducteur front
  (`apps/web/src/lib/game/journal.ts`) : les deux tests de parité (émetteurs↔projecteurs,
  journal↔front) restent verts.
- `docs/jeu/TALENTS.md` — la fiche du jeu : les trois natures, le « une fois par tour par Pokémon »,
  et **la décision d'annulation mutuelle tranchée par écrit**.
- `apps/game/tests/test_cartes_talents.py` — 18 tests, dont les cinq talents réels et les trois cas
  exigés par la fiche.

## Preuves

- **CI / recette locale chimera** : `uv run ruff check .` → *All checks passed* ;
  `uv run pytest -q` (suite complète du moteur) → **1015 passed in 39.55s**, dont les **18** du
  lot et les deux tests de parité.
- **Critère n°1 — annulation mutuelle tranchée et testée** :
  `test_deux_verrous_ne_s_annulent_pas` (deux Garbotoxine coexistent, chacun actif, seuls les
  talents ordinaires sont éteints), `test_talent_continu_annule_par_un_talent_adverse` (un Garbodor
  adverse fait disparaître la réduction −30 du Bouclier du calcul de dégâts). Décision écrite :
  `docs/jeu/TALENTS.md` (clause « sauf lui-même », R-12.3).
- **Critère n°2 — un talent cesse d'agir à l'instant où son Pokémon quitte le jeu** :
  `test_talent_cesse_a_l_instant_ou_son_pokemon_quitte_le_jeu` — même registre, même appel, l'effet
  disparaît dès que la source quitte l'état, **sans aucune opération de retrait** (dérivé, pas
  défait).
- **Critère n°3 — cinq talents réels de natures différentes** : Bouclier Indéfectible (continu),
  Garbotoxine (continu, verrou), Incisives Travailleuses (activé), Soin de Camp (déclenché), Forge
  Ardente (activé, depuis l'Actif, désactivé par un état). Tous scriptés et testés.
- **Les trois tests exigés** : `test_talent_banc_soigne_entre_les_tours` (talent de banc qui soigne
  au Checkup), `test_talent_continu_annule_par_un_talent_adverse` (talent annulé par un talent
  adverse), `test_talent_active_deux_fois_refuse` (talent activé deux fois refusé — et un **autre**
  Pokémon portant le même talent reste libre).

## Grille

| Tâche | État | Preuve |
|---|---|---|
| dev | fait | `talents.py`, `talents_actives.py`, state/drapeaux/sérialisation, action+événement |
| tests | fait | 18 tests ; suite complète 1015 passed ; chaque règle cite son R-x.y |
| securite | fait | moteur pur, aucun secret ; routes inchangées (pas d'E/S dans ce lot) |
| maquette | s.o. | aucun écran ajouté ; le journal front ne gagne qu'un traducteur (phrase FR) |
| doc_tech | fait | `docs/jeu/TALENTS.md` + docstrings françaises (le *pourquoi*) |
| release_uat | fait | recette locale chimera : ruff vert + 1015 tests verts |
| release_prod | s.o. | aucun déploiement (la PROD se livre à part, par devAI) |
| backlog | s.o. | tenu par la file (etat.json non touché, conformément au couloir) |
| compte_rendu | fait | ce fichier |

## Écarts au plan

- **Les cinq talents réels sont scriptés dans la suite de tests**, pas dans un catalogue interne du
  moteur — choix cohérent avec `effets.objets` / `effets.supporters`, où les scripts de cartes
  viennent du service (DSL en paramètres), le moteur ne portant que le **cadre** (D9 : registre vide
  par défaut). Le cadre accepte et garde correctement ces talents, c'est ce que les tests prouvent.
- **Suppression dérivée vs matérialisée.** La neutralisation est **dérivée de l'état** pour les
  natures continue et déclenchée (correcte *par construction*, ce qui répond au piège de la fiche :
  un talent continu consulté au mauvais moment). Côté transition `activer_talent` — pure, elle
  ignore le registre des talents — le garde-fou serveur reste le verrou `talents_sans_effet`
  (déjà prévu par `effets.verrous`). Les deux chemins sont testés.

## Reste à faire (hors périmètre de ce lot)

- Câbler les registres de talents d'une partie réelle dans l'orchestrateur côté `apps/api`
  (publier `EJ_*` au bon moment, proposer les talents activés légaux, matérialiser le verrou
  `talents_sans_effet` à l'entrée/sortie d'un Garbodor). Le cadre est prêt ; aucun lot du jeu n'en
  dépend (le lot ne débloque rien).
