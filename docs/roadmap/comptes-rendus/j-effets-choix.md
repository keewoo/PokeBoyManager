# Compte rendu — `j-effets-choix`

**Lot** : Demandes de décision — quand le moteur doit attendre un joueur, y compris l'adversaire.
**Jalon** : J2 (toutes les cartes du deck vraiment jouées). **Piste** : Effets & cartes.
**Machine** : travail sur **chimera** (WSL Ubuntu-24.04), pilotage depuis **devAI**.

## Résumé

Livré le mécanisme de **demandes de décision** (`pbm_game.demandes`), pur, posé au-dessus de la pile
d'effets. Une carte peut réclamer un choix — à son joueur ou à l'**adversaire**, en plein tour de
l'autre : une carte, plusieurs, un ordre, oui/non, un type, un nombre ; de façon obligatoire ou
facultative ; parmi un ensemble visible ou caché ; avec une **réponse par défaut** et une
**horloge**. La résolution **se suspend**, la demande vit **dans l'état** (sérialisée, donc reprise
après un F5 avec le temps restant), et reprend à la réponse ou à l'expiration. Le piège de la
section 5 (bloquer un fil côté serveur) est évité par conception : **la demande est une donnée, pas
une attente de code**, et la reprise est un **re-déroulé** pur (aléatoire ramené en arrière, aucun
tirage compté deux fois). Le `choisir` du DSL est branché dessus sans changer sa sémantique (D9).

## Livrables

- **Modèle** `src/pbm_game/demandes/modele.py` — `DemandeDecision`, `Reponse`, les 6 catégories,
  `valider_reponse` (le serveur fait autorité) et `reponse_par_defaut` (premier choix valide, ou
  abandon d'un effet facultatif), sérialisation bidirectionnelle.
- **Gestionnaire** `demandes/gestionnaire.py` — `Gestionnaire.demander` (rend la réponse connue ou
  lève `SuspensionDemande`), indices de décision `d0`, `d1`… déterministes.
- **Moteur** `demandes/moteur.py` — `ResolutionEnCours` (portée par l'état), `resoudre`,
  `demarrer_resolution`, `repondre`, `expirer`, le registre `REGISTRE_EFFETS`, et les événements
  `demande_emise` / `demande_repondue` / `demande_expiree`.
- **Transitions journalisées** `demandes/transitions.py` — `repondre_demande` / `expirer_demande`,
  auto-enregistrées dans le `REGISTRE` du journal (motif `banc`/`cartes`).
- **État** — `EtatPartie.resolution` (schéma **v3**), sérialisation (`state/serialisation.py`),
  empreinte (automatique via `vers_json`), **garde** dans `journal/transitions.appliquer` (aucune
  action pendant une demande sauf réponse, expiration, abandon), **projection** par joueur
  (`state/projection.py` : la demande est publique, les options réservées au destinataire, un
  ensemble caché réduit à un nombre).
- **DSL branché** — `resolveur_dsl_demandes` + `strategie_demande` (`effets/dsl/`), enregistré dans
  `REGISTRE_EFFETS` par `pbm_game/__init__.py`.
- **Aléatoire** — `Rng.restaurer` (retour en arrière en place, brique du re-déroulé).
- **Doc** — `docs/jeu/DEMANDES.md` (fiche), renvois depuis `EFFETS.md`, `JOURNAL.md`, `ETAT.md`.
- **Tests** — 5 suites : `test_demandes_modele`, `_moteur`, `_dsl`, `_journal`, `_projection`
  (45 tests ajoutés).

## Critères d'acceptation — preuves

1. **Une partie interrompue au milieu d'une demande reprend exactement à cette demande, avec le
   temps restant** → ✅ `test_reprise_apres_f5_par_serialisation_garde_le_temps_restant`
   (sérialisation aller-retour, `temps_restant_ms` préservé) et
   `test_rejeu_d_une_partie_interrompue_au_milieu_d_une_demande` (rejeu complet du journal, empreinte
   contrôlée au coup près).
2. **Les demandes imbriquées se résolvent dans le bon ordre et se voient dans le journal** → ✅
   `test_demandes_imbriquees_se_resolvent_dans_le_bon_ordre_et_au_journal` : `d0` (parent) puis `d1`
   (enfant déclenché par le parent), événements `demande_emise` / `demande_repondue` dans l'ordre.
3. **L'expiration applique la réponse par défaut et l'écrit dans le journal** → ✅
   `test_expiration_applique_le_defaut_et_le_journalise` (obligatoire → 1re option) et
   `test_expiration_d_un_effet_facultatif_abandonne_proprement` (facultatif → abandon), événement
   `demande_expiree` portant le choix joué.

Autres points de mission : **demande à l'adversaire** →
`test_demande_peut_viser_l_adversaire_pendant_le_tour_de_l_autre` ; **garde (rien d'autre qu'une
réponse, sauf abandon)** → `test_garde_bloque_toute_action_sauf_reponse_et_abandon` ; **reprise après
reconnexion mid-demande** → test de rejeu ci-dessus ; **déterminisme du re-déroulé (piège de la
section 5)** → `test_re_deroule_ne_rejoue_pas_l_aleatoire` et, côté DSL,
`test_pile_ou_face_avant_choisir_n_est_pas_rejoue_au_re_deroule` (un seul tirage dans le journal).

Chaque suite contient au moins un test qui **échoue sans** le changement et passe avec (p. ex.
l'absence de garde laisserait passer une pioche pendant une demande ; l'absence de retour en arrière
du Rng compterait le pile ou face deux fois).

## Mesures

- Suite moteur **verte** : `uv run pytest -q` → **796 passés** (751 avant le lot + 45 ajoutés).
- `uv run ruff check .` → **All checks passed**. Python 3.12.
- Moteur resté **pur** : `test_*_purete` existants toujours verts ; aucun import HTTP/DB/réseau dans
  `pbm_game.demandes`.

## Écarts au plan / périmètre

- **DSL — destinataire par défaut = celui qui joue l'effet.** Un `choisir` qui doit faire décider
  l'**adversaire** depuis le DSL demandera une extension du vocabulaire (un champ `demandeur`), qui
  viendra avec les lots de cartes qui en ont besoin (`j-cartes-objets` : appâts ; `j-cartes-supporters`).
  Le **mécanisme**, lui, gère déjà un destinataire quelconque — prouvé par les tests du moteur. Ce
  n'est pas une approximation (D9) : le `choisir` reste exactement ce qu'il était, seule la politique
  de décision est devenue branchable.
- **L'horloge est une donnée, pas un décompte.** Le moteur étant pur, il ne décrémente aucun temps :
  `delai_ms` / `temps_restant_ms` vivent dans l'état, et c'est l'adaptateur temps réel (lot
  `j-timer`) qui fera tomber l'horloge et appellera `expirer`. Documenté dans `DEMANDES.md`.
- **Aucune carte n'est scriptée ici** (D9) : comme `j-effets-architecture`, ce lot livre le cadre et
  le prouve avec des résolveurs jouets ; les effets réels arrivent avec les lots de cartes.

## Reste à faire (hors lot)

- Débloqués par ce lot : `j-cartes-objets`, `j-cartes-supporters`, `j-cartes-talents`,
  `j-plateau-decisions`, `j-timer` (voir `docs/roadmap/jeu/BACKLOG-JEU.md`).
- Extension DSL `demandeur` (choix de l'adversaire) à prévoir dans le premier lot de cartes qui en
  a besoin.
