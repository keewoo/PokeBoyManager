# Compte rendu — `j-cartes-outils`

**Jalon J2 — Toutes les cartes du deck sont vraiment jouées.** Piste Effets & cartes, couloir
chimera (travail sur chimera, pilotage/CI/fusion depuis devAI).

## Résumé

Les **Outils Pokémon** sont jouables : une transition **`attacher_outil`** (un Outil de la main
rejoint un Pokémon du joueur actif, Actif ou banc — R-5.5, **au plus un par Pokémon** R-3.7), une
transition **`retirer_outil`** (un effet retire l'Outil → défausse du propriétaire R-13.2, **avec
K.O. immédiat** si le retrait d'un Outil de PV fait passer les compteurs au-dessus du nouveau seuil
R-13.1), et **trois Outils réels** exprimés en producteurs d'effets continus. Le cadre d'effets
continus livré par `j-cartes-talents`/`j-cartes-stades` gérait déjà l'Outil (lecture de
`pokemon.outil`, `seuil_ko`, `modificateurs_degats`) : ce lot a ajouté les **deux coups**, le
**helper de seuil effectif** pour le K.O., et les **cartes réelles**. La **défausse au K.O.** était
déjà portée par `combat.ko.cartes_a_defausser` (R-13.2) — ce lot en dépend et le prouve par un test.

## Livrables

- **`apps/game/src/pbm_game/effets/outils.py`** (nouveau) : transitions `attacher_outil` /
  `retirer_outil` (enregistrées dans le `REGISTRE` du journal via `pbm_game/__init__.py`), et les
  producteurs des trois Outils réels + `registre_outils(meta)`.
- **`effets/continus.py`** : helper `fiches_avec_seuils_continus(etat, registre, fiches)` — le
  **seuil de K.O. effectif** (PV imprimé + deltas continus) à passer à `resoudre_kos`. Un seul point
  de câblage pour le service (attaque **et** retrait d'Outil).
- **`journal/modele.py`** : `ACTION_ATTACHER_OUTIL`, `ACTION_RETIRER_OUTIL`, `EVT_OUTIL_ATTACHE`,
  `EVT_OUTIL_RETIRE`.
- **Parité** : `EVT_OUTIL_ATTACHE` / `EVT_OUTIL_RETIRE` ajoutés aux `PROJECTEURS` (public,
  `sortie/evenements.py`) **et** aux `TRADUCTEURS` du front (`apps/web/src/lib/game/journal.ts`),
  avec leurs fixtures dans `journal.test.ts`.
- **Trois Outils réels** (le seul sous-ensemble d'Outils que le catalogue de jeu enrichit) :
  **Protective Poncho** (`B2-147` et `B2-234`, deux impressions — prévention de tous les dégâts
  tant que le porteur est au banc, modificateur de défense `fixe 0`) et **Metal Core Barrier**
  (`B2-148` — `−50` dégâts au porteur **Metal**, modificateur de défense `−50`).
- **Fiche** : `docs/jeu/OUTILS.md`. **Tests** : `apps/game/tests/test_cartes_outils.py` (16 tests).

## Preuves

- `uv run ruff check .` (apps/game) : **All checks passed**.
- `TZ=Europe/Paris uv run pytest -q` (apps/game) : **1048 passed** — dont les tests de parité
  (`test_parite_evenements_projecteurs`), de pureté du moteur (`test_rng`, `test_corpus_regles`) et
  les 16 de `test_cartes_outils.py`.
- Critères d'acceptation :
  - *le retrait d'un Outil de PV provoque le K.O. si les compteurs dépassent le nouveau seuil* →
    `test_retrait_outil_de_pv_provoque_le_ko_immediat_r131` : un Outil jouet +30 PV tient un Pokémon
    à 70 compteurs en vie (seuil 90, `resoudre_kos` ne le tue pas) ; `retirer_outil` ramène le seuil
    à 60 et émet `EVT_KO` (70 ≥ 60). Les compteurs ne bougent jamais
    (`test_pv_continus_changent_le_seuil_pas_les_compteurs_r131`).
  - *un Pokémon ne porte jamais deux Outils* → `test_deuxieme_outil_refuse_r37` (ValueError citant
    R-3.7) ; l'invariant d'état `state/invariants.py` garde déjà R-3.7 par construction.
  - *trois Outils réels scriptés et testés* → `test_protective_poncho_previent_les_degats_au_banc_r37`
    (dégâts au banc ramenés à 0 ; rien quand le porteur est Actif),
    `test_metal_core_barrier_moins_50_pokemon_metal_r37` (−50 au porteur Metal, rien à un autre
    type), `test_registre_outils_couvre_les_trois_refs_reelles`.
  - *Outil défaussé avec son porteur au K.O.* → `test_outil_defausse_avec_le_porteur_au_ko_r132`.
  - *Outil sur un Pokémon du banc* → `test_attacher_outil_sur_un_pokemon_du_banc_r37`.
- CI GitHub Actions : voir la PR (elle fait foi, front compris — type-check + vitest).

## Écarts au plan

- **Le catalogue de jeu n'enrichit que trois `ref` d'Outils** (deux cartes distinctes :
  Protective Poncho en deux impressions, Metal Core Barrier). Aucune n'est un Outil de **PV** ni de
  **coût de retraite** : le critère « retrait d'un Outil de PV → K.O. » est donc prouvé au niveau
  du **cadre** avec un producteur **jouet** +30 PV (comme `effets.continus` l'y invite
  explicitement), et les trois Outils **réels** sont des effets de **prévention/réduction de
  dégâts**. C'est le catalogue réel, pas une réduction de périmètre choisie.
- **Clause « se défausse à la fin du tour adverse » de Metal Core Barrier** : ce n'est pas un effet
  continu. Le moteur fournit le **retrait** (`retirer_outil`, testé) ; le **service** en orchestre
  l'instant (il émet un `retirer_outil` à la fin du tour adverse, comme il émet le `checkup`). La
  carte est donc complètement spécifiée, sans approximation (D9).
- **Câblage des modificateurs continus dans la résolution d'attaque** : `combat/attaque.py` ne
  consulte pas encore les modificateurs continus (même état que les Stades depuis
  `j-cartes-stades`). Les producteurs et `fiches_avec_seuils_continus` sont le livrable ; le câblage
  dans l'attaque et la construction des `fiches` effectives sont l'intégration service (ci-dessous).
- **Pas de route HTTP nouvelle** dans ce lot : il est **pur moteur**. Aucun test d'accès croisé à
  ajouter (il n'y a pas de route utilisateur `user_id` ici) ; l'isolation reste celle des routes de
  partie existantes. Aucun écran nouveau : les deux événements passent par le journal déjà rendu
  (traducteurs ajoutés + fixtures).

## Reste à faire (intégration service, hors moteur pur)

- Fusionner `registre_outils(meta)` dans `CatalogueJeu.registre_continus` (avec `meta` portant le
  `type` de chaque Pokémon porteur, pour Metal Core Barrier).
- Câbler les modificateurs continus dans `combat/attaque.py` et construire les `fiches` de
  `resoudre_kos` via `fiches_avec_seuils_continus` (attaque **et** retrait d'Outil).
- Émettre le `retirer_outil` d'auto-défausse de Metal Core Barrier à la fin du tour adverse.
- Surfacer `attacher_outil` dans les actions légales (`FamilleAttacherOutil`, sur le modèle de
  `FamilleAttacherEnergie`) — non livré ici ; le coup se joue déjà par la transition.
