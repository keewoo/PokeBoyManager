# Compte rendu — `j-ko-recompenses`

**Mises K.O., récompenses et conditions de victoire (R-13, R-14).**
Lot P0, piste Règles & moteur, couloir `J-MOT`, exécuté en autonomie sur **devAI**.

## Résumé

Les lots amont avaient posé les primitives de mise K.O. (`pbm_game.combat.ko`), l'abandon
(`j-actions-legales`, R-14.3), la défaite par pioche impossible (`j-machine-tour`, R-14.2) et le
K.O. hors attaque au Checkup avec promotion/banc-vide (`j-checkup`). **Il manquait le cœur du
lot** : la **première** façon de gagner — prendre sa dernière récompense (R-14.1 cas 1) — qui
n'était vérifiée nulle part ; la table **marqueur de règle → nombre de récompenses** (R-13.3,
possédée par le moteur, marqueur inconnu = panne) ; et un résolveur de K.O. **partagé** capable
de trancher le K.O. simultané et l'égalité avec son départage (R-13.5/R-14.4/R-14.5/R-16.10).

Ce lot livre le module **pur** `pbm_game.combat.fin` et **y branche le Checkup** (qui déléguait
jusqu'ici à une copie locale de la résolution de K.O.). La victoire par récompenses est donc
honorée **partout** où un K.O. survient — pas seulement dans l'attaque à venir. Une garde centrale
R-14.6 dans `appliquer` fait qu'une partie terminée refuse **toute** action, y compris mécanique.

## Livrables

- **Table marqueur → récompenses (R-13.3/R-13.4/R-13.7)** — `MARQUEUR_RECOMPENSES` (close, keyée
  par marqueur et non par nom) + `recompenses_pour_marqueur` : 1/2/3 selon R-15, **marqueur
  inconnu = `ValueError`**, jamais « par défaut 1 ». `valider_fiches` accepte une fiche qui porte
  soit un `marqueur` (préféré), soit un `recompenses` entier ≥ 1, et refuse tout le reste à la
  validation (eager).
- **Résolveur de K.O. partagé** — `resoudre_kos(etat, fiches, ordre)` : met K.O. tous les Pokémon
  (Actif avant banc, ordre déterministe — y compris **plusieurs d'une même attaque**), défausse
  (R-13.2), récompenses prises (R-13.3), puis tranche la fin. Le Checkup l'appelle à son étape 3
  (la copie locale `_resoudre_kos`/`_fiche`/`_valider_fiches` a été **retirée**, plus de
  duplication).
- **Trois conditions de victoire + égalité** — (1) dernière récompense prise → `derniere_recompense`
  (R-14.1 cas 1, **nouveau**) ; (2) adversaire sans Pokémon → `plus_de_pokemon` (R-14.1 cas 2) ;
  (3) pioche impossible → `pioche_impossible` (R-14.2, dans `debut_tour`). K.O. simultané :
  départage par **nombre de voies** (R-14.5), à égalité → NULLE (R-14.4/R-16.10).
- **Fin normalisée** — `terminer(etat, vainqueur, raison, **donnees)` fige la partie (vainqueur +
  raison + `EVT_PARTIE_TERMINEE`) et refuse de re-terminer. Garde **centrale** R-14.6 dans
  `appliquer` : une partie terminée refuse toute action (couvre aussi `melanger_pioche`/`piocher`,
  jusque-là non gardés).
- **Invariant R-3.3 exempté pour une partie terminée** — une fin par récompenses ou un K.O.
  simultané fige le plateau **avant** la promotion : un banc non promu sans Actif est un état
  terminal légitime (`state/invariants.py`).
- **Constante** `RAISON_DERNIERE_RECOMPENSE` ajoutée à `pbm_game.journal.modele` (exportée).
- **Doc** : `docs/jeu/FIN-DE-PARTIE.md` (nouvelle fiche) ; renvoi mis à jour dans `CHECKUP.md`.
- **Tests** : `apps/game/tests/test_ko_recompenses.py` (31 tests) ; un test du Checkup corrigé
  (voir Écarts).

## Preuves

- `uv run pytest -q` (apps/game) : **259 tests verts** (228 avant le lot + 31 nouveaux).
- `uv run ruff check .` : **All checks passed**.
- Test qui **échoue sans le changement et passe avec** :
  `test_victoire_en_prenant_sa_derniere_recompense_r141` — avant ce lot, prendre sa dernière
  récompense ne terminait pas la partie (seul le banc vide le faisait).
- Pureté : `test_import_fin_ne_tire_aucune_dependance_lourde` + l'analyse statique du corpus
  (`test_source_du_moteur_n_importe_rien_d_interdit`) couvrent le nouveau module.
- Chaque test de règle cite son `R-x.y` ; `test_les_regles_citees_par_ce_lot_existent_dans_le_corpus`
  garantit qu'aucune citation ne pend dans le vide.
- CI GitHub Actions (job `game`) : fait foi, verte sur la PR (voir le dernier message).

## Écarts au plan

- **Un test du Checkup corrigé, pas un bug** : `test_promotion_apres_checkup_remplit_lactif...`
  donnait à bob **1 seule** récompense ; sous la règle désormais appliquée (R-14.1 cas 1), prendre
  cette récompense **gagne** la partie — ce que l'ancien moteur ignorait. Le test a été remonté à
  6 récompenses pour isoler la promotion du cas « dernière récompense » (et assert ajouté
  `not terminee`). C'est la correction d'un test qui encodait l'ancien comportement incomplet.
- **R-14.5 (départage « deux voies contre une »)** implémenté bien qu'il dépasse le strict minimum
  des critères : R-16.10 (égalité) est un cas limite exigé et le départage est sa règle sœur ;
  les deux sont testés.

## Reste à faire

- Le branchement de `resoudre_kos` **dans la résolution d'attaque** viendra avec le lot d'effets /
  d'architecture (`j-degats-resolution` pose les dégâts, pas encore les K.O. qui en découlent) :
  le résolveur est prêt et partagé pour ce moment.
- Le `marqueur` dans les fiches est consommé par le moteur ; son **extraction depuis le catalogue**
  (sous-types / Rule Box) est du ressort du service (`j-cartes-pokemon`), hors moteur (D9).
- La **Sudden Death** après égalité (R-14.4) reste une décision du service, explicitement différée.
