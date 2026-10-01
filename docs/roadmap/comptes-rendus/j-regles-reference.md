# Compte rendu — `j-regles-reference` — Corpus de règles de référence : la version qui fait foi, écrite et citée

**Statut visé : fusionné dans `main` après CI verte.**
Piste Règles & moteur · couloir J-MOT (devAI) · jalon J1 · aucune dépendance amont · 01/10/2026.

## Résumé

Premier lot du moteur de jeu `pbm_game`, écrit **avant** la première ligne de moteur. Il pose la
vérité contre laquelle tout le reste sera jugé : un corpus de règles numérotées (`docs/jeu/REGLES.md`),
une table de cas qui nomme pour chacun la règle qu'il vérifie (`docs/jeu/cas-de-regles.yaml`), et un
test qui garantit que ce lien n'est jamais rompu. Le paquet `pbm_game` est créé ici, pur et vide de
dépendances d'exécution — les lots suivants (`j-modele-etat`, …) le remplissent.

## Décision DJ1 — déjà prise, citée et datée

`decisions_prises.DJ1` dans `docs/roadmap/etat.json` fait foi : **JF, le 01/10/2026
(2026-10-01T09:50+0200)**, a choisi le **format « maison » sans rotation avec le corpus de règles
actuel** — toute carte possédée est jouable quelle que soit son époque, mais jouée avec les règles
d'aujourd'hui (faiblesse ×2, résistance −30, 6 récompenses, banc de 5, le joueur qui commence
n'attaque pas à son premier tour). Cette décision et sa date sont inscrites en **R-1.2** du document.
Aucune question n'a eu à être posée : la décision était déjà tranchée.

## Source unique, officielle, datée — le piège évité

Le risque nommé par le lot : recopier une page d'encyclopédie amateur qui mélange les époques. Évité
par une **source unique** : le livret officiel **« Pokémon Trading Card Game Rules », série Écarlate
& Violet, ©2023 Pokémon** (PDF officiel pokemon.com), consulté le 01/10/2026, langue de référence
anglais. Les points sensibles (ordre de calcul des dégâts, ordre du Pokémon Checkup, matrice de
cumul des états spéciaux, règle du premier tour, décomptes de récompenses) ont été **extraits du PDF
lui-même**, pas de mémoire, et sont cités section par section en **R-1.1**.

Points où les règles ont changé selon les époques : listés explicitement en **§ R-17**, chacun
tranché vers le comportement actuel (faiblesse +X → ×2 ; résistance −20 → −30 ; premier joueur ne
pioche pas → pioche ; cumul d'états ; confusion 30 PV → 3 compteurs). Aucun point n'est laissé en
« selon l'époque ».

## Livrables

- `docs/jeu/REGLES.md` — corpus de **121 règles** numérotées `R-x.y`, 17 sections : source & format,
  deck, zones, mise en place & mulligan, tour, premier tour, évolution, retraite/banc, attaque,
  calcul des dégâts, états spéciaux (avec matrice de cumul paire par paire), Pokémon Checkup, K.O. &
  récompenses, victoire/abandon/égalité, cartes particulières (ex, Tera ex, GX, V, VMAX, VSTAR, TAG
  TEAM, V-UNION, Radiant, ACE SPEC), cas limites, variantes historiques tranchées.
- `docs/jeu/cas-de-regles.yaml` — **62 cas**, chacun nommant au moins une règle existante ; **11 cas
  limites** balisés par slug canonique, dont les **6 explicitement listés dans la mission**
  (pioche vide, banc vide après K.O., K.O. simultané, dernier Pokémon K.O. hors attaque, abandon,
  égalité). Les champs `entree`/`attendu` sont volontairement différés à `j-tests-regles` (le modèle
  d'état n'existe pas encore).
- `apps/game/` — paquet moteur `pbm_game` (Python 3.12, uv) : `pbm_game.regles` (chargement et
  vérification de cohérence, fonctions **pures**), tests, `pyproject.toml` **sans dépendance
  d'exécution**, `uv.lock`.
- `.github/workflows/ci.yml` — nouveau job **`game`** (ruff + pytest, **sans base/Redis/S3**) :
  une suite que la CI n'exécute pas serait une CI verte sur rien.

## Preuves

- Tests verts en local (Python 3.12, `uv run pytest -q` dans `apps/game`) : **13 passés**.
- Le test **échoue sans le changement** : il lit `docs/jeu/REGLES.md` et `docs/jeu/cas-de-regles.yaml`
  — absents, les fixtures échouent. Mieux : pendant l'écriture, `test_aucune_regle_definie_en_double`
  a **réellement mordu** sur une définition `R-15.12` dupliquée (une citation en gras), corrigée.
- Pureté du moteur prouvée par deux tests : import de `pbm_game` sans dépendance lourde, **et**
  analyse statique (AST) de chaque `.py` du paquet refusant tout import de fastapi/sqlalchemy/
  asyncpg/redis/boto3/httpx/pbm_api… — c'est l'invariant que `j-modele-etat` reprendra.
- Le vérificateur **mord** aussi sur un corpus incohérent : tests dédiés d'un cas sans règle, d'un
  identifiant mal formé, d'une citation orpheline, d'un cas limite manquant.
- `uv sync --locked` passe (lock à jour, ce que la CI exige).
- `ruff check .` : All checks passed.

## Critères d'acceptation

- [x] Chaque section du document porte un identifiant de règle citable par un test (`R-x.y`, vérifié
  par `test_cas_citent_des_regles_existantes`).
- [x] Aucun point de règle laissé en « selon l'époque » : § R-17 tranche chaque variante.
- [x] La table de cas couvre au minimum les dix cas limites de la mission (11 balisés, les 6 nommés
  présents — `test_dix_cas_limites_couverts`, `test_cas_limites_des_six_mecaniques_nommees`).
- [x] DJ1 validée par JF et datée dans le document (R-1.2 : 2026-10-01T09:50+0200).

## Écarts

- Les champs `entree`/`attendu` de chaque cas sont **différés** à `j-tests-regles` : à ce stade le
  modèle d'état (`j-modele-etat`) n'existe pas, un cas ne peut donc pas encore porter un état
  d'entrée concret. La table nomme la règle vérifiée, ce qui est exactement le périmètre de ce lot
  (« chaque cas nomme la règle qu'il vérifie »).
- La « Sudden Death » officielle (manche à 1 récompense sur égalité) est documentée comme une
  décision du **service**, hors moteur (R-14.4) : le moteur J1 renvoie `égalité`. Choix écrit, un
  seul comportement.
- Le paquet `pbm_game` vit dans `apps/game` et partage la version de Python de la flotte (3.12),
  mais **aucune** dépendance d'exécution : la pureté est garantie par test, pas seulement par
  intention.

## Reste à faire (lots débloqués)

- `j-modele-etat` — état de partie (zones, attachements, compteurs, vues par joueur) ; reprendra
  l'invariant de pureté posé ici.
- `j-tests-regles` — étoffera `cas-de-regles.yaml` avec les états d'entrée et les résultats attendus,
  une fois le modèle d'état disponible.

## Complément du 01/10/2026 (pilote, branche `roadmap/j-regles-complement`)

Relecture du corpus fusionné : il s'appuyait sur le livret Écarlate & Violet (2023) et **ignorait la
série en vigueur, Méga-Évolution (2025)**, dont la Méga-Évolution Pokémon ex donne **3 récompenses**
— or son nom finit par « ex », si bien qu'un classement par suffixe l'aurait comptée à 2, en silence.
Il ignorait aussi les marqueurs des ères anciennes, qu'un format « on joue ce qu'on possède » (DJ1)
rencontrera, et ne disait pas si la **zone perdue** existe — question que `j-modele-etat` doit trancher.

Ajouts : R-1.4 (série en vigueur, Rule Box imprimé comme source des règles propres à une carte),
R-2.7/R-2.8 (Prisme Étoile, Pokémon ★), R-3.8 (zone perdue), R-13.3 complété, R-13.7 (le suffixe du
nom ne suffit pas), R-15.13 à R-15.22 (Méga-Évolution ex, Pokémon-EX, M Pokémon-EX, Pokémon-ex de
l'ère EX, BREAK, Prisme Étoile, LÉGENDE, LV.X, Pokémon ★, Rule Box inconnu refusé), R-17.10 ; dix
cas ajoutés à la table. Source de la règle Méga-Évolution ex : annonce officielle pokemon.com du
27/02/2025 (citée en R-1.4).

**Écart connu, hors de ce corpus** : `apps/api/src/pbm_api/ingame/rules.py` (`prize_rule_of`, fiche
« En jeu » en PROD) classe par suffixe du nom : il affiche 2 récompenses pour une Méga-Évolution ex
et pour une TAG TEAM (3 en réalité). À corriger dans un lot dédié.
