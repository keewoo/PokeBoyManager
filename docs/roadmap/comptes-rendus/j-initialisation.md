# Compte rendu — `j-initialisation`

**Lot** : Mise en place — mélange, main de sept, mulligans, actif et banc face cachée, six récompenses.
**Jalon** J1 · piste Serveur de parties · couloir **J-MOT** (moteur pur, exécuté sur **devAI**).
**Branche** `roadmap/j-initialisation` · base `origin/main`.

> **Reprise.** Le worktree et la branche existaient déjà : une session antérieure avait commité le
> cœur du moteur (`1b0c8b2`) et laissé un travail non commité à moitié câblé côté service. Cette
> session a repris cet état, l'a amené à un ensemble cohérent et vert, fusionné `origin/main`
> (12 commits de retard : `doc-api`, `j-timer`, `j-deconnexion-abandon`) et clôturé.
>
> **Emplacement du worktree.** `/Volumes/Data/DevAI` a refusé l'écriture à cette session lancée
> par launchd (TCC, cas connu du 01/10) : repli sur `~/dev/wt-j-initialisation`, comme le prévoit
> le contexte d'exécution.

## Résumé

La mise en place est la première chose qu'un joueur voit, et l'une des plus subtiles : les
mulligans et la **révélation simultanée** sont des règles que la plupart des jeux en ligne
simplifient à tort. Ce lot livre le moteur pur `pbm_game.mise_en_place` qui les applique
fidèlement (R-4), sans jamais rien laisser fuir à l'adversaire avant la révélation.

- **Mélange + pioche de sept** (R-4.1) par flux d'aléatoire nommé, reproductible.
- **Boucle de mulligan** (R-4.4/R-4.6) : main sans base **révélée** puis remélangée et repiochée ;
  double mulligan **sans** carte bonus.
- **Cartes bonus** (R-4.5) : une par mulligan pris seul par l'adversaire, **comptées** pendant la
  boucle et **piochées à la révélation**.
- **Placement Actif + banc face cachée** (R-4.2/R-3.2) : le choix vit dans
  `EtatPartie.mise_en_place`, invisible de l'adversaire jusqu'à la révélation.
- **Révélation simultanée** (R-4.2/R-4.3) : un **seul** événement porte les deux côtés, six
  récompenses posées face cachée — personne n'est révélé avant l'autre, même s'il valide bien avant.

Le moteur ne devine aucun stade (D9) : les actions portent `params["definitions"]` fourni par le
service ; une fiche absente **bloque**. Cette session a complété et **testé** le helper de
sérialisation service → action `definition_vers_dict` (round-trip exact avec
`definition_depuis_dict`), et **retiré** l'import prématuré et inutilisé qu'avait laissé la session
précédente dans `apps/api/.../games/construction.py` — le câblage service appartient à un lot
service ultérieur, pas à ce lot moteur.

## Livrables

| Fichier | Rôle |
|---|---|
| `apps/game/src/pbm_game/mise_en_place/{modele,transitions,__init__}.py` | moteur pur R-4 + deux transitions journalisées |
| `apps/game/src/pbm_game/journal/{modele,transitions,debogage}.py` | actions `mise_en_place_initiale`/`placer_mise_en_place` et six types d'événement (`EVT_MAIN_REVELEE`, `EVT_MULLIGAN`, `EVT_MISE_EN_PLACE_PRETE`, `EVT_PLACEMENT_CACHE`, `EVT_MISE_EN_PLACE_REVELEE`…) |
| `apps/game/src/pbm_game/state/{modele,projection,serialisation}.py` | `EtatPartie.mise_en_place` + projection par joueur (non-fuite) + aller-retour JSON exact |
| `apps/game/src/pbm_game/cartes/{modele,__init__}.py` | `definition_vers_dict` (inverse de `definition_depuis_dict`) |
| `apps/game/tests/test_mise_en_place.py` (19) | preuves moteur, chaque test citant son `R-x.y` |
| `apps/game/tests/test_cartes.py` (+2) | round-trip `definition_vers_dict` (fiche riche + base nue) |
| `docs/jeu/MISE-EN-PLACE.md` | fiche durable de la mécanique R-4 |
| `docs/jeu/cas-de-regles.yaml`, `couverture-exceptions.yaml` | cas de règles R-4 couverts |

## Preuves

- **Suite moteur `apps/game` verte** : `uv run pytest -q` → **857 passed** (dont les 19 de
  `test_mise_en_place.py` et les 2 round-trip ajoutés) ; `uv run ruff check .` → **All checks
  passed**. Python 3.12, `UV_PYTHON=3.12`.
- **Critère 1 — non-fuite avant révélation** : `test_placement_face_cachee_ne_fuit_pas_avant_revelation`
  vérifie qu'après que A a placé, aucun `instance_id` de son placement n'apparaît dans `repr(vue(etat, "b"))`,
  que l'Actif/banc publics de A restent vides, et que B ne voit que `a_place: true`.
- **Critère 2 — comptage des bonus exact et journalisé** :
  `test_comptage_bonus_exact_quand_les_deux_prennent_des_mulligans` et
  `test_cartes_bonus_piochees_a_la_revelation` (bonus `(0, 2)` → main de B à `7-1+2=8` après
  révélation, résumé `bonus_pioches: 2` dans l'événement) ; `test_main_revelee_est_journalisee_avec_son_contenu`.
- **Critère 3 — révélation simultanée** :
  `test_revelation_est_simultanee_meme_si_un_joueur_valide_bien_avant` : A valide en premier, rien
  ne lui est révélé de B ; quand B valide, **un seul** `EVT_MISE_EN_PLACE_REVELEE` porte `{a, b}`.
- **Tests exigés (mission §5)** : `test_trois_mulligans_de_suite`,
  `test_mulligan_des_deux_joueurs_sans_carte_bonus`, `test_main_sans_base_cinq_fois_daffilee`.
- **Pureté / rejouabilité** : `test_import_mise_en_place_ne_tire_aucune_dependance_lourde`,
  `test_rejouabilite_avec_le_vrai_rng`, `test_etat_en_mise_en_place_fait_un_aller_retour_json_exact`.
- **Un test qui mord** : les deux round-trip importent `definition_vers_dict` — sans la fonction,
  l'import échoue ; `test_deck_sans_aucune_base_refuse_plutot_que_boucler` prouve qu'un deck sans
  base est **refusé** au lieu de boucler à l'infini.
- CI GitHub : la PR porte le verdict (web, api, game, e2e). Voir dernier message.

## Écarts au plan

- **Lot moteur (couloir J-MOT), aucune route ni écran.** Les points « route utilisateur → test
  d'accès croisé » et « écran → maquette » de la grille générique ne s'appliquent pas : ce lot
  n'ajoute ni endpoint HTTP ni composant React. La non-fuite est prouvée **au niveau du moteur**
  (projection `vue`), là où l'autorité réside.
- **Câblage service non inclus, volontairement.** `apps/api` ne consomme pas encore
  `mise_en_place_initiale`/`placer_mise_en_place` : construire ces actions depuis deux decks et les
  jouer relève d'un lot service. Le helper `definition_vers_dict` est livré **prêt et testé** pour lui.
- Pas de `release_uat`/`release_prod` : rien à déployer (moteur pur, aucune surface servie).

## Reste à faire (lots suivants)

- Lot service : câbler la mise en place dans le cycle de vie d'une partie (construire l'action avec
  `definitions`, la jouer, exposer la projection par le temps réel) et son test d'accès croisé.
- Tirage au sort du premier joueur (R-4.7) : posé par `j-lancement-partie`/le câblage service, pas
  deviné par le moteur.
