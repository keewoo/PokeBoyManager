# Compte rendu — `j-actions-legales`

**Lot** : Générateur d'actions légales — ce qui est jouable, et pourquoi le reste ne l'est pas.
**Piste** : Règles & moteur (couloir J-MOT, devAI) · **Jalon** J1 · P0 · palier 4.
**Branche** : `roadmap/j-actions-legales` · **Machine** : devAI (worktree `../wt-j-actions-legales`).

## Résumé

Livré le **générateur d'actions légales** du moteur `pbm_game`, en Python pur (aucune E/S,
ni HTTP, ni base, ni React). Deux fonctions portent désormais, à elles seules, la légalité
du jeu — l'interface n'a plus à connaître les règles, elle affiche ce qu'on lui donne :

- `actions_legales(etat, joueur)` → la liste **exhaustive** des coups jouables, chacun avec
  son **étiquette lisible** et ses **cibles valides** (calculées depuis l'état, jamais depuis
  l'écran) ;
- `valider(etat, action)` → l'accord, ou un **refus motivé** par une règle citée du corpus
  (`R-14.6 : la partie est terminée`). Toute action y passe, y compris celles du serveur.

**Une seule source de vérité : la liste.** `valider` recalcule `actions_legales` depuis
l'état qui fait autorité et vérifie l'**appartenance** de l'action — il ne redérive jamais la
légalité par un second chemin (c'est le piège nommé par la mission). Un test de cohérence
garde l'équivalence `valider(a).accepte ⇔ a ∈ actions_legales` pour toujours.

Conformément à **D9** (« un effet non implémenté n'est jamais approximé »), ce lot livre le
**cadre complet** (liste, validation, cibles, registre de familles extensible) et les seules
familles qui ne demandent **aucune** donnée de carte : **avancer la phase / terminer le
tour** (R-5.1, joueur actif) et **abandonner** (R-14.3, tout joueur). Les familles
dépendantes du catalogue (poser, évoluer, attacher, jouer un Dresseur, retraite, attaque) ne
sont **pas** générées : chaque lot de résolution enregistrera la sienne dans
`FAMILLES_DEFAUT`, comme les transitions s'enregistrent dans `journal.transitions.REGISTRE`.

## Livrables

- **Paquet `pbm_game.actions`** (`apps/game/src/pbm_game/actions/`) :
  - `modele.py` — `Cible`, `ActionLegale`, `Verdict` + `refus()` (qui exige une règle et un
    message : pas de refus muet) ; genres de cible.
  - `generateur.py` — `actions_legales()`, `valider()`, la classe abstraite `Famille`, les
    deux familles livrées (`FamilleAvancerPhase`, `FamilleAbandonner`) et la source unique
    `FAMILLES_DEFAUT`.
  - `__init__.py` — API publique du paquet.
- **Action mécanique `abandonner`** ajoutée au journal (`ACTION_ABANDONNER`,
  `EVT_PARTIE_TERMINEE`, `RAISON_ABANDON`, transition `_abandonner` dans
  `journal/transitions.py`, description lisible dans `journal/debogage.py`) : elle ne demande
  aucune donnée de carte, donc elle vit dans le même registre que la pioche et l'avancée de
  phase. Le générateur décide *quand* elle est jouable.
- **Tests** : `apps/game/tests/test_actions_legales.py` (18 tests, dont la propriété sur
  **10 000 états** et la mesure de coût).
- **Docs** : `docs/jeu/ACTIONS.md` (contrat, périmètre, point d'extension) ; table des
  transitions de `docs/jeu/JOURNAL.md` complétée (`abandonner`) ; docstrings de
  `pbm_game/__init__.py` et des `__init__` de paquet mises à jour.

## Preuves

- **Suite `game` verte** sur devAI (`UV_PYTHON=3.12`) : `uv run ruff check .` → *All checks
  passed!* ; `uv run pytest -q` → **110 passed in 2.02s** (dont 18 nouveaux + les anciens
  toujours verts). La CI GitHub `game` (ruff + pytest sur `apps/game`) exécute ces tests —
  elle fait foi.
- **Critère 1 — toute action listée s'applique, aucune hors liste n'est acceptée** :
  `test_propriete_toute_action_legale_s_applique_sans_erreur` tire **10 000** états de
  `fabrique_etat(seed)` ; pour chaque joueur, chaque coup listé (a) s'applique via
  `appliquer()` **sans lever** et laisse l'état **sain** (`assert_invariants`), (b) est
  **accepté** par `valider` ; et un coup hors liste est **refusé** avec une règle qui existe.
  `test_aucune_action_hors_liste_n_est_acceptee` ajoute une batterie négative sur 500 états.
- **Critère 2 — chaque refus cite une règle du corpus** :
  `test_chaque_refus_cite_une_regle_du_corpus` vérifie que tout `R-x.y` de refus
  (R-14.6, R-5.1, R-14.3, R-5.2, R-4.1, R-15.12) existe dans `docs/jeu/REGLES.md`
  (`identifiants_definis`). Le constructeur `refus()` lève si la règle ou le message manque.
- **Critère 3 — coût sous 5 ms** : `test_actions_legales_sous_5ms_sur_un_etat_complet` mesure
  le meilleur de 50 essais sur un état complet (banc plein, mains garnies, états, stade) ;
  largement sous le seuil.
- **Cibles calculées depuis l'état** : `test_cadre_porte_des_cibles_calculees_depuis_l_etat`
  exerce le mécanisme bout en bout via une famille-jouet **de test** (une cible par Pokémon
  en jeu) — sans inventer aucune règle de carte en production.
- **Pureté** : `test_import_actions_ne_tire_aucune_dependance_lourde` + le grep statique AST
  de `test_corpus_regles.py` (scanne tout `src/pbm_game`, donc le nouveau paquet).
- **Test qui échoue sans le changement** : tout `test_actions_legales.py` importe
  `pbm_game.actions`, inexistant avant ce lot → ImportError sans le changement, 18 passed avec.

## Écarts au plan

- **Périmètre des familles volontairement restreint aux coups sans donnée de carte** (D9).
  Au palier 4, le moteur n'a pas de catalogue : il ne connaît ni le type d'une carte, ni les
  coûts, ni les attaques, ni les évolutions. Générer « poser un Pokémon », « attacher une
  énergie » ou « déclarer une attaque » exigerait d'inventer ces données — interdit (« le jeu
  préfère dire *je ne sais pas encore proposer ce coup* que de le proposer de travers »). Ce
  n'est **pas** une réduction subie : c'est la ligne D9, et le **cadre** qui les accueillera
  (registre de familles, cibles, validation) est livré et testé. Documenté dans
  `docs/jeu/ACTIONS.md` § « Périmètre au palier 4 » et § « Le point d'extension ».
- **`avancer_phase` est offert à chaque phase** d'une partie vivante. Les contraintes fines de
  phase (pioche obligatoire, attaque qui termine le tour, premier tour du joueur qui commence)
  relèvent du lot suivant `j-machine-tour` ; elles affineront cette famille, sans la remplacer.
- **`abandonner` ajouté au registre du journal** : c'est une transition mécanique (aucune
  donnée de carte), à sa place aux côtés de `piocher`/`avancer_phase`, et le registre a été
  explicitement conçu par `j-journal-actions` pour être étendu.
- Aucune modification du workflow CI : le job `game` existant couvre déjà `apps/game`
  (ruff + pytest) et exécute les nouveaux tests. Aucune dépendance ajoutée → `uv.lock` inchangé.

## Reste à faire (hors lot)

- `j-machine-tour` : phases, contraintes du tour, fin de tour — affinera `FamilleAvancerPhase`.
- `j-retraite-banc`, `j-degats-resolution`, `j-cartes-pokemon` : enregistreront leurs familles
  (retraite, attaque, poser/évoluer) dans `FAMILLES_DEFAUT` quand elles auront le catalogue.
- `j-plateau-interactions` : l'interface qui affiche la liste, les cibles, l'annulation, la
  confirmation, et montre la raison d'un refus.
- `j-effets-choix` : la famille « répondre à une demande de décision » (aucun mécanisme de
  décision n'existe encore dans l'état).
