# Compte rendu — `j-checkup`

**Phase entre les deux tours : l'ordre exact de résolution (Pokémon Checkup, R-12).**
Lot P0, piste Règles & moteur, couloir `J-MOT`, exécuté en autonomie sur **devAI**.

## Résumé

Le moteur avait une machine à tour (`j-machine-tour`) qui entrait en phase `checkup` mais n'y
résolvait **rien** : les états spéciaux, les K.O. hors attaque et l'expiration des effets
temporaires n'avaient pas d'endroit où se résoudre dans un ordre fixé. Ce lot livre cette phase,
de bout en bout, dans l'ordre strict du corpus (R-12), et la mécanique de K.O. **partagée** qui
évite que le code de victoire ne vive que dans la résolution d'attaque.

Nouveau paquet **pur** `pbm_game.checkup` (`resoudre_checkup` + la transition système `checkup`,
journalisée et rejouable) et nouvelles primitives **partagées** de mise K.O. dans
`pbm_game.combat.ko`. Aucun I/O, aucune donnée de carte en dur : PV et récompenses sont fournis
par le service depuis le catalogue (D9).

## Livrables

- **Phase intermédiaire ordonnée** — `apps/game/src/pbm_game/checkup/resolution.py` :
  `resoudre_checkup` résout, dans l'ordre, les états de chaque Actif (R-12.2 : poison → brûlure →
  sommeil → paralysie), l'expiration des effets temporaires (R-12.5), puis les K.O. (R-12.4).
  Le joueur **dont le tour s'achève** est résolu en premier (déterminisme + R-11.6 paralysie).
- **Effets des états au Checkup** — poison 1 compteur (R-11.7), brûlure 2 compteurs + pile ou
  face (R-11.4), réveil au pile ou face (R-11.3), paralysie guérie au Checkup après le tour de
  son propriétaire (R-11.6). Pile ou face journalisé dans un flux dédié (`flux_checkup`).
- **Expiration journalisée des effets** — fenêtre `FENETRE_EXPIRATION_EFFETS` (R-12.5) : chaque
  expiration émet `EVT_EFFET_EXPIRE`. Vide au jalon J1 (aucun effet temporaire n'existe encore),
  mais câblée, franchie et prouvée par un déclencheur jouet injecté en test.
- **K.O. hors attaque + récompenses + promotion** — primitives partagées `pbm_game.combat.ko`
  (`est_ko`, `cartes_a_defausser`, `prendre_recompenses`) ; au Checkup : défausse (R-13.2),
  l'adversaire prend ses récompenses (R-13.3), promotion demandée au bon joueur (`EVT_KO` +
  `EVT_PROMOTION_REQUISE`, R-8.7), banc vide = défaite (R-8.9/R-14.1), double K.O. des deux
  derniers Actifs = égalité (R-14.4).
- **Action système `checkup`** journalisée et rejouable (fiches catalogue dans `params`, donc le
  rejeu n'a pas besoin du catalogue) ; non listée par le générateur d'actions.
- **Doc** : `docs/jeu/CHECKUP.md`. Événements et action ajoutés à `pbm_game.journal.modele`.
- **Tests** : `apps/game/tests/test_checkup.py` (29 tests).

## Preuves

- **Suite moteur verte** : `apps/game` → `uv run pytest -q` = **228 passed** (dont 29 nouveaux),
  `ruff check .` = **All checks passed!** (Python 3.12, `TZ=Europe/Paris`).
- **Échec sans le changement** : le paquet `pbm_game.checkup` et `test_checkup.py` sont des
  fichiers neufs (absents d'`origin/main`) → l'import en tête de la suite échoue sans ce lot.
- **Critères d'acceptation** :
  - *Ordre poison + brûlure + réveil sur les deux joueurs* →
    `test_ordre_poison_brulure_reveil_sur_les_deux_joueurs_r122` (séquence d'événements contrôlée,
    joueur du tour d'abord).
  - *Un K.O. donne ses récompenses et déclenche la promotion* →
    `test_un_empoisonne_meurt_entre_les_tours_ladversaire_prend_sa_recompense_et_promotion_r124`
    (alice empoisonnée meurt, bob prend 1 récompense, promotion demandée à alice) ;
    `test_ko_dun_pokemon_ex_donne_deux_recompenses_r133` (compte lu sur la fiche, pas en dur).
  - *Aucun effet temporaire ne survit sans journal* →
    `test_expiration_dun_effet_temporaire_est_journalisee_r125` +
    `test_aucun_effet_temporaire_au_jalon_j1_mais_la_fenetre_existe_r125`.
- **D9** : fiche manquante / malformée → `ValueError` bruyante
  (`test_fiche_manquante_...`, `test_fiche_malformee_refusee_jamais_par_defaut_1_r134`).
- **Pureté** : `test_import_checkup_ne_tire_aucune_dependance_lourde`,
  `test_resoudre_checkup_ne_mute_pas_l_etat_d_entree`.
- **Rejouabilité** : `test_checkup_passe_par_le_registre_et_est_rejouable` (empreinte contrôlée),
  `test_checkup_action_fiches_survivent_a_la_serialisation`.
- **Chaque test de règle cite son `R-x.y`** et `test_chaque_etat_resolu_cite_une_regle_du_corpus`
  vérifie que les règles citées par les événements existent dans `docs/jeu/REGLES.md`.

## Écarts au plan / décisions prises (session autonome)

- **Frontière avec `j-etats-speciaux` et `j-ko-recompenses`.** Les critères d'acceptation de
  `j-checkup` exigent un cas *poison → mort → récompense → promotion* qui fonctionne. J'ai donc
  implémenté **ici** les effets des états *au Checkup* (R-11.3/4/6/7 — pleinement spécifiés par
  le corpus, donc jamais approximés) et la mécanique de K.O. hors attaque. Restent explicitement
  aux lots qui me suivent (et qui me dépendent) : la **pose** des états, la matrice de cumul, la
  confusion à l'attaque et l'orientation (`j-etats-speciaux`) ; les **conditions de victoire**
  complètes et le détail du K.O. simultané (`j-ko-recompenses`). Les primitives de K.O. sont
  volontairement dans `pbm_game.combat.ko`, **partagées**, pour qu'ils s'y branchent sans
  réécriture. L'égalité sur double K.O. est gérée a minima ici pour ne jamais désigner un
  mauvais vainqueur ; `j-ko-recompenses` en portera la version détaillée.
- **Pas de modification de `.github/workflows/ci.yml`** : le job `game` lance déjà
  `uv run pytest -q` dans `apps/game`, qui collecte automatiquement `test_checkup.py`. La CI
  exécute donc bien ce lot.
- **`graphify update .`** se fait sur le checkout `main` (`~/dev/pokeboy`), que la file de lots
  utilise — je n'y touche pas en session autonome ; l'étape revient à l'ordonnanceur après la
  fusion.

## Reste à faire

- `j-etats-speciaux` : pose, matrice de cumul, confusion, orientation — se branchent sur cette
  phase sans la réécrire.
- `j-ko-recompenses` : conditions de victoire complètes (plus de récompenses, pioche vide, etc.)
  et K.O. simultané détaillé, au-dessus de `pbm_game.combat.ko`.
- `j-effets-architecture` : remplira `FENETRE_EXPIRATION_EFFETS` et les effets « au Checkup ».
