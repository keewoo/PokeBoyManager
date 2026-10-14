# `j-rendu-carte` — Ma photo ou l'image officielle : la carte telle qu'elle est jouée

**Statut : livré** (recette locale sur la flotte ; aucun déploiement — la PROD se livre à part).
Machine : devAI (pilotage, suites front) + chimera (worktree, git, suites API).
Branche `roadmap/j-rendu-carte`, depuis `github/main` à `295d322`.

## Résumé

Le plateau affichait le **nom** des cartes. Il affiche maintenant la carte : la **photo
personnelle** de son propriétaire, l'**image officielle**, ou un **dos** dessiné. Le choix est fait
**par le serveur**, carte par carte et regard par regard, selon la décision DJ5 — et c'est ce qui
rend le réglage « ne jamais montrer mes photos » réel plutôt que décoratif : la photo qu'on ne doit
pas voir n'a **aucune URL** dans la charge utile reçue.

Chaque photo est **notée** (netteté, luminosité, cadrage) et se replie sur l'officielle sous un
seuil, **en le disant** au joueur dans son constructeur de deck. Et ce n'est jamais la photo
d'origine qui est servie : une **variante de jeu** de 44 Ko remplace les 178 Ko du recadrage
(0,86 Mo au lieu de 3,5 Mo pour un plateau de vingt cartes).

La règle durable est dans **`docs/jeu/RENDU-CARTES.md`** ; les repères serveur dans
`docs/ARCHITECTURE.md`, l'écran dans `docs/UI-UX.md`. Ce compte rendu porte ce qui s'est passé.

## Livrables

| | |
|---|---|
| Décision DJ5, pure | `apps/api/src/pbm_api/jeu/rendu.py` — `decider_origine` est **le seul** ordre de verdicts |
| Note de qualité, pure | `apps/api/src/pbm_api/jeu/rendu_qualite.py` — 5 seuils nommés, raisons en français |
| Variante de jeu | `apps/api/src/pbm_api/jeu/rendu_image.py` — 420×587 WebP 80 |
| Lectures base + stockage | `apps/api/src/pbm_api/jeu/rendu_service.py` |
| Pose du rendu sur la vue | `apps/api/src/pbm_api/games/rendu_vue.py` + câblage `games/projection.py`, `games/indicateurs.py`, `games/temps_reel.py` (resync comprise) |
| Routes | `apps/api/src/pbm_api/routers/jeu_rendu.py` — réglages, aperçu de deck, photo d'une partie |
| Réglage par deck | `decks.rendu_cartes` + `PATCH /me/decks/{id}` + `DeckDetail.rendu_cartes` |
| Migration | `a1f7c3d9e5b2` — table `jeu_rendu_reglages`, 3 colonnes ajoutées, tête unique |
| Rattrapage du corpus | `apps/api/scripts/preparer_rendus_jeu.py` (flotte, reprenable, `--a-blanc`) |
| Carte et dos à l'écran | `apps/web/src/components/game/board-card.tsx` (`ImageCarte`, `CardBack`) |
| Vignettes de décision | `apps/web/src/components/game/fenetre-decision.tsx` — options imagées, dos pour un ensemble caché |
| Écran « Mes cartes en jeu » | `apps/web/src/app/jeu/rendu/` + `apps/web/src/lib/api/rendu.ts` |
| Panneau du constructeur de deck | `apps/web/src/app/jeu/decks/[id]/deck-rendu-panel.tsx` |
| Fiche | `docs/jeu/RENDU-CARTES.md` (+ entrée dans la carte des fiches de `CLAUDE.md`) |

## Les trois critères d'acceptation, et leur preuve

### 1. « Une carte sans photo exploitable se joue avec l'image officielle, sans trou ni attente »

- `test_jeu_rendu_projection.py::test_une_carte_sans_photo_se_joue_avec_l_image_officielle` — la
  carte de B (qui ne la possède pas en photo) porte `/img/cards/{id}?size=low` et `?size=high`, avec
  la raison « aucune photo de cette carte », **dans les deux vues** ;
- `…::test_une_photo_trop_sombre_replie_en_le_disant` — photo présente mais notée inexploitable :
  officielle, raison « photo trop sombre » ;
- **sans attente** : aucune image n'est fabriquée dans la projection. Une variante manquante se
  replie sur l'officielle avec `RAISON_PAS_PRETE` plutôt que de faire patienter un plateau
  (`test_jeu_rendu_choix.py::test_une_variante_pas_encore_prete_replie_sans_faire_attendre`) ;
- **sans trou jusque dans le cas dégradé** : une photo est servie avec `url_repli` (l'officielle,
  publique). Si l'image ne charge pas → officielle ; si elle non plus → le **nom redevient
  visible** (`board-card-rendu.test.tsx`, deux tests).

### 2. « Le réglage de confidentialité est respecté côté adversaire (test de bout en bout) »

Prouvé à deux niveaux, parce qu'un seul ne suffisait pas :

- **sur la charge utile** —
  `test_jeu_rendu_projection.py::test_le_veto_retire_l_url_de_la_charge_utile_de_l_adversaire` :
  après `jamais_montrer_mes_photos`, la vue de B porte l'officielle et
  `str(item.id) not in str(vue_b)` — l'identifiant d'exemplaire n'apparaît **nulle part**. A, lui,
  continue de voir sa photo ;
- **sur la route** —
  `test_jeu_rendu_routes.py::test_le_veto_ferme_la_photo_a_l_adversaire_mais_pas_a_son_proprietaire` :
  la **même URL** répond 200 au propriétaire et 404 à l'adversaire. Toute la décision est rejouée
  par la route : une URL devinée ou gardée d'une partie précédente ne sert rien
  (`…::test_choisir_les_images_officielles_ferme_aussi_la_photo`).

Deux propriétés structurelles, chacune avec son test :

- le veto est évalué **avant** toute consultation de la photo → aucune URL ne peut sortir par une
  erreur d'ordre (`test_aucune_url_de_photo_n_est_emise_sous_veto_meme_dans_url_repli`) ;
- la raison rendue est **identique** qu'une photo existe ou non → le refus ne révèle pas que le
  joueur a photographié cette carte (`test_le_veto_ne_revele_pas_si_une_photo_existe`).

**Accès croisé** : un intrus (404), l'exemplaire d'un tiers dans ma propre partie (404), le deck
d'un autre (404), un compte sans `game_access` (404 sur les quatre routes). Tous le **même** 404 —
un code distinct dirait à l'adversaire ce qu'il n'a pas à savoir.

### 3. « Les trois rendus sont lisibles à la taille du plateau sur téléphone »

`apps/web/e2e/plateau-rendu.spec.ts`, en navigateur réel, à 844×390 (paysage) puis 390×844 :

- l'image **remplit** la carte (écart ≤ 2 px avec la boîte de la carte), à chaque orientation ;
- le **zoom** rend l'image ≥ 150 px de large (lisible sans pincer l'écran) — c'est **là** que se joue
  la lisibilité, voir l'encadré ci-dessous ;
- les **deux rendus coexistent** (ma photo / l'officielle côte à côte) et le crédit de la photo
  adverse est annoncé ;
- un **ensemble caché** montre 6 dos ;
- et **aucun défilement** à chacune des étapes — la contrainte dure de `/jeu/parties/{id}`.

⚠️ Cet e2e n'a **pas** pu être exécuté localement : navigateur Playwright impossible sur chimera
(libnspr4, sudo requis) et non installé sur devAI. **C'est la CI qui fait foi** sur ce critère —
c'est écrit ici parce que le dire est la seule façon honnête de livrer ce point. Et elle a servi :
le premier passage a **échoué**, sur deux points qui valaient d'être sus (voir ci-dessous).

### Ce que la CI a appris, et que la machine locale ne pouvait pas dire

**Une carte de plateau fait 11 px de large en paysage 844×390.** Mesuré par la CI, pas supposé. Ma
première version du test exigeait 24 px : c'était une erreur d'intention de ma part, pas un défaut
du plateau. `board-card.tsx` l'écrit noir sur blanc depuis `j-plateau-layout` — *« minuscule sur un
téléphone en paysage, d'où le zoom »*. Le critère « lisible à la taille du plateau sur téléphone »
est donc porté par le **zoom** (≥ 150 px mesurés, soit 256 px CSS en pratique), la vignette ne
servant qu'à situer la carte. Le test contrôle maintenant que la boîte n'est pas **dégénérée** et
que l'image **remplit** exactement la carte, et dit pourquoi il n'en exige pas plus.

**Le zoom s'ouvre au focus clavier, pas au survol, dans le test.** `locator.hover()` sur une cible
de 11 px a expiré à 60 s : Playwright attend une cible pointable fiable. Le chemin **clavier**
(`onFocus`, câblé comme le survol) ne dépend pas du pointage — et c'est de toute façon celui qu'on
veut garantir. La vue simulée a par ailleurs été rapprochée d'un plateau réel (Stade posé, énergies
attachées, cinq cartes en main) : un plateau vide donnerait des tailles plus flatteuses que la
réalité.

## Chiffres mesurés

Sur une **carte réelle** (Dracaufeu `base1-4`, image officielle haute définition redressée par
`warp_card`) :

| | Taille | Poids | Un plateau (20) | Un deck (60) |
|---|---|---|---|---|
| photo stockée | 630×880 JPEG 92 | 178 Ko | 3,5 Mo | 10,5 Mo |
| **variante de jeu** | 420×587 WebP 80 | **44 Ko** | **0,86 Mo** | 2,6 Mo |

Facteur **/4,1**. 420 px de large parce que le pire cas n'est pas le plateau (≈ 60 px) mais le zoom
(`min(70vw,16rem)` = 256 px, soit 512 px à densité double).

**Calibrage des seuils de qualité** sur cette même carte réelle : netteté **677** (seuil 60),
luminosité **130** (fenêtre 55–225), **0 %** de pixels brûlés (seuil 22 %) → exploitable, très loin
des seuils. Les seuils ont d'abord été posés sur des images synthétiques (nette, floue, sombre,
brûlée, délavée, coupée), puis vérifiés contre cette carte.

Le défaut le plus intéressant est le **reflet du flash** : il est mesuré **à part** (part de pixels
≥ 250), parce qu'un flash peut brûler un quart de l'image en laissant une luminance moyenne tout à
fait normale. `test_le_reflet_du_flash_est_detecte_meme_avec_une_moyenne_normale` construit exactement
ce cas (28 % brûlés, moyenne dans la fenêtre acceptable) : sur la seule moyenne, cette photo passait.

## Tests

| Suite | Résultat |
|---|---|
| `test_jeu_rendu_qualite.py` + `test_jeu_rendu_choix.py` (purs) | **31 passés** |
| `test_jeu_rendu_routes.py` + `test_jeu_rendu_projection.py` | **25 passés** |
| Suite API complète (chimera) | **1314 passés**, 2 échecs d'environnement (voir ci-dessous) |
| Non-régression ciblée (projection, indicateurs, routes de partie, decks, schéma, temps réel) | 47 passés |
| `ruff check .` (ce que fait la CI) | **All checks passed** |
| `alembic heads` | **une seule tête** (`a1f7c3d9e5b2`) ; `upgrade head` joué sur la base de test |
| Front : lint, `tsc --noEmit`, `next build` | **verts** (page `/jeu/rendu` dans le build) |
| Front : vitest | **431 passés**, 15 échecs préexistants (voir ci-dessous) |
| Nouveaux tests front | `board-card-rendu.test.tsx` (13), `rendu-view.test.tsx` (7), `deck-rendu-panel.test.tsx` (5), `fenetre-decision.test.tsx` (+2) |
| e2e | `plateau-rendu.spec.ts` (4 tests) — **non exécuté localement**, CI souveraine |

**Le test qui échoue sans le changement** : vérifié en remettant `board-card.tsx` dans sa version
`HEAD` → **10 des 13** tests de `board-card-rendu.test.tsx` échouent (avant ce lot, `BoardCard`
n'émettait aucun `<img>` ; les 3 qui passent sont ceux du cas « aucune image »).

### Les deux échecs API ne viennent pas du lot

`test_catalogue_seed.py::{test_seed_export_then_restore_into_empty_database,test_seed_import_is_idempotent}`
→ `pg_dump: command not found`. Le client PostgreSQL n'est pas installé dans la WSL de chimera ; la
CI l'installe. Aucun rapport avec ce lot (ces tests lancent `scripts/catalogue_seed.sh`).

### Les 15 échecs front ne viennent pas du lot

`app-shell.test.tsx`, `app-shell-jeu.test.tsx`, `app-shell-decks.test.tsx` — trois fichiers que ce
lot ne touche pas, pile dans `src/lib/theme-provider.tsx:12` (`readStoredTheme`). Écart déjà
documenté sur devAI (Node 26 local contre Node 24 en CI).

## Décisions prises dans le lot, et pourquoi

- **La décision vit à un seul endroit** (`decider_origine`). Le constructeur de deck et la vue de
  partie passent tous deux par elle : sinon l'avertissement « ta photo est trop sombre » et ce que
  le joueur voit en jeu pourraient diverger, sans qu'aucun test de l'un ou de l'autre ne l'attrape.
  Un test fixe cette équivalence sur quatre cas.
- **Les rendus sont résolus pour les deux regards d'un coup** (`RendusPartie`, clé
  `(regard, propriétaire, ref)`). Ce n'est pas du zèle : `HUB.publier` projette **un** résultat vers
  **tous** les abonnés avec un seul `CatalogueAffichage` — une résolution par regard au moment de
  l'enrichissement demanderait une lecture de base par abonné.
- **`decks.rendu_cartes` est nullable *sans* `server_default`.** Nul veut dire « suit le réglage du
  compte », pas « photo » : un défaut posé sur la colonne figerait les decks existants et rendrait le
  réglage global sans effet sur eux. Côté API, `rendu_cartes: ""` **efface** la préférence — dans un
  PATCH partiel, `null` serait indistinguable d'un champ absent.
- **Le cadrage n'est pas remesuré.** Une fois la carte redressée en 630×880, l'image remplit le cadre
  par construction : ce qui a été coupé l'a été avant. Il est donc **reçu** depuis
  `detections.bbox["crop_quality"]` (lot `v3-detection`), et vaut `None` pour un exemplaire sans
  détection — on ne suppose pas qu'il est parfait, ce serait faire passer une carte coupée.
- **La variante n'est jamais fabriquée dans la projection** : un plateau se lit plusieurs fois par
  seconde. Elle l'est à l'ouverture du deck (le moment « à l'avance », borné, et c'est là qu'on le
  dit au joueur), à la première demande de la photo, ou par le script sur la flotte.
- **Le crédit « photo de Aymeric » n'est écrit qu'au zoom**, et annoncé par l'`aria-label` sur le
  plateau : à 60 px de large, un bandeau de texte serait illisible **et** recouvrirait les énergies.
  Discret ne veut pas dire absent.
- **`object-contain`, pas `cover`** : une carte a des proportions connues, la rogner couperait son
  nom ou ses PV.
- **Le dos est dessiné, pas chargé** — identité propre (aucun logo officiel Pokémon), et une image de
  plus à télécharger pour une carte qu'on ne voit pas serait du poids pour rien.

## Écarts au plan, et ce qui reste

- **Le redressement n'a pas été « réutilisé », il était déjà là** (mission point 1). La photo de
  `collection_items.photo_s3_key` **est** le recadrage redressé de `v3-detection` : le lot n'avait
  pas à redresser, mais à **réduire**. C'est ce qui est fait. Rien ne manque, la formulation du plan
  anticipait simplement un travail déjà acquis.
- **Pas de crochet à la validation.** La préparation aurait pu être déclenchée quand un exemplaire
  reçoit sa photo (`validation/service.py`), mais cela imposait un `storage` à la signature de
  `confirm_detection`/`confirm_all` et à leurs appelants, pour un gain marginal : l'ouverture du deck
  prépare déjà, avant toute partie. Choix assumé, pas un oubli.
- **Le corpus existant n'a pas de variante.** Rien n'est cassé — ces cartes se replient sur
  l'officielle en le disant — mais pour que les joueurs voient leurs photos dès la première partie,
  il faut un passage de `scripts/preparer_rendus_jeu.py` sur la flotte, contre la base de PROD. Ce
  n'est **pas** fait ici (aucun déploiement dans ce lot). À inscrire dans la prochaine livraison PROD,
  **après** la migration.
- **La désignation à l'aveugle d'un ensemble caché reste non implémentée** (D9). Le lot y ajoute les
  dos de carte et le nombre — le joueur voit enfin qu'il s'agit de cartes — mais la phrase « pas
  encore disponible » est conservée : on ne l'approxime pas.
- **Qualité WebP à 80**, soit 44 Ko. Descendre à 70 gagnerait ~25 % de poids ; à vérifier sur de
  vraies photos de téléphone (pas sur une image officielle) avant de toucher au chiffre.
- **Les seuils de qualité méritent une seconde passe sur de vraies photos.** Ils sont calibrés sur
  des images synthétiques et une carte officielle, pas sur des photos prises au téléphone par un
  enfant — qui sont précisément le cas d'usage. Le script `--a-blanc` donne la distribution des
  verdicts sur le corpus réel : c'est la mesure à faire avant d'ajuster.

## Ce qui attend JF

Rien à décider : DJ5 était prise (14/10/2026) et elle est appliquée à la lettre. Deux choses à
savoir pour la prochaine livraison PROD :

1. la migration `a1f7c3d9e5b2` est à jouer (trois colonnes + une table, aucune donnée réécrite, le
   retour arrière rend exactement l'état d'avant) ;
2. puis `uv run python scripts/preparer_rendus_jeu.py` **sur la flotte** (jamais sur le serveur qui
   sert) pour que les photos déjà prises deviennent jouables.
