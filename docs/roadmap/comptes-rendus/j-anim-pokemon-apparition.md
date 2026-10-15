# `j-anim-pokemon-apparition` — Le Pokémon apparaît au-dessus de sa carte

**Jalon J3** · piste Graphisme & animations · taille L · complexité 5/5 · difficulté 5/5
**Session autonome**, 15/10/2026. Branche `roadmap/j-anim-pokemon-apparition`.

## Résumé

Le Pokémon sort de son illustration pour se poser, évoluer et attaquer. La découpe est produite
hors ligne par une chaîne de détourage (U²-Net sur ONNX Runtime), notée sur six critères nommés,
**validée à l'œil une par une** sur une planche de contrôle, puis publiée dans un registre
versionné. À l'écran, quatre calques partagent la même image et se déplacent d'amplitudes
différentes — la parallaxe sans modèle 3D, sans canvas, en `transform`/`opacity` seulement.

Onze cartes sur dix-sept candidates ont une apparition. Les vingt-deux mille autres n'en ont pas, et
cela ne se voit pas : l'effet de type générique joue comme avant, sans trou ni message.

## Les quatre critères d'acceptation

| Critère | État | Preuve |
|---|---|---|
| DJ3 tranchée et écrite **avant** la première découpe | ✅ | `etat.json` → `decisions_prises.DJ3`, posée par JF le **15/10/2026 à 10:02**, lue avant d'écrire une ligne de `decoupe.py` |
| Une carte sans découpe joue l'effet générique, sans trou ni message | ✅ | `anim-apparition.test.ts` — 4 cas de dégradation (pas de découpe, autre carte, animations réduites, pas de signal) ; `apparition-pokemon.test.tsx` « ne rend RIEN sans apparition » |
| Le coût d'affichage reste sous le plafond de fluidité | ✅ | `COUT_LE_PLUS_LOURD` = 11 ≤ coût de `fairy` (11), le type sur lequel le plancher de 30 img/s est mesuré au navigateur. **Le test a d'abord échoué à 12** : `PARTICULES_MAX` est passé de 8 à 7 plutôt que de relever le plafond |
| Les découpes des vedettes sont validées à l'œil, une par une | ✅ | Deux planches relues ; verdicts et motifs inscrits dans `apparitions.json`. **La publication est impossible sans `verdict_oeil == accepte`** (`vedettes.ecrire_notes`, testé) |

## Livrables

### La chaîne de détourage

- `apps/api/src/pbm_api/jeu/decoupe.py` — **module pur**, segmenteur injecté : il se teste en CI
  sans `onnxruntime`. `NoteDecoupe` mesure aire, compacité, bords, morceaux, flou, allongement.
- `apps/api/src/pbm_api/jeu/segmentation.py` — adaptateur U²-Net, import paresseux, empreinte
  SHA-256 du modèle vérifiée à chaque chargement.
- `apps/api/scripts/decouper_apparitions.py` — le lot : `--a-blanc`, `--vedette`, `--planche`,
  `--ecrire-registre`, `--sans-publier`, `--telecharger-modele`. Code de sortie non nul si une
  vedette du registre n'a pas pu être produite.
- `apps/api/pyproject.toml` — extra `decoupe = ["onnxruntime>=1.20.0"]`, **hors CI et hors image de
  production**.

### Le registre et le service

- `apps/api/src/pbm_api/jeu/vedettes.py` + `apparitions.json` — 17 vedettes, **11 publiées**.
- `GET /img/apparitions/{tcgdex_id}` — garde de motif **et** d'appartenance au registre avant toute
  lecture de stockage, même 404 dans les trois cas, cache immuable + ETag + 304.
- `RenduResolu.apparition` / `VueRenduCarte.apparition` — l'URL arrive avec la vue, l'écran ne
  devine rien. Une requête SQL bornée par vue, jamais 120 interrogations du stockage.
- `budget.postes_partie()` — 1 × 40 Kio. Total **2264 Kio** pour un plafond de 2304 ; mise en place
  **inchangée** (432 Kio), parce que l'apparition ne s'y déclenche jamais.

### La mise en scène

- `apps/web/src/lib/game/anim-apparition.ts` — module pur : motifs, calques, profondeurs,
  particules, `coutVisuel`, `COUT_LE_PLUS_LOURD`.
- `apps/web/src/components/game/apparition-pokemon.tsx` — `absolute`, `pointer-events-none`,
  `aria-hidden`, une seule image partagée par quatre calques.
- `globals.css` — quatre images-clés `pbm-anim-fx-a-*`, `transform`/`opacity` uniquement.
- Branchement : `board-card.tsx` (avant les indicateurs, comme l'effet typé) et `game-board.tsx`
  (le signal dérivé **une fois** puis distribué).

## Preuves

| Mesure | Chiffre |
|---|---|
| Tests API neufs | **49** (`tests/test_jeu_apparition.py`), verts sans `onnxruntime` |
| Suites API voisines | **122 passed** (rendu, projection, assets, images, routes) |
| Tests web neufs | **40** (24 module pur + 8 composant + 8 garde CSS) |
| Suite web complète | **888 passed / 97 fichiers**, aucune régression |
| `tsc --noEmit` | **0** |
| `ruff check .` | **All checks passed** |
| Découpes produites / publiées | 14 / **11** sur 17 candidates |
| Poids d'une découpe | médiane **20,9 Ko**, max **23,3 Ko**, plafond 40 Kio |
| Budget d'une partie | **2264 Kio** / 2304 Kio |
| Nœuds animés simultanés | **11** / 11 admis |

### Les trois découpes refusées par la note, et les trois refusées à l'œil

`base1-9` Magnéton (éclaté en 2 morceaux) · `base1-10` Mewtwo (sujet trop petit, éclaté) ·
`base1-16` Électhor (bord vaporeux, 0,32 > 0,22) — refusées par la mesure.
`base1-5` Mélofée (fond sombre accroché à l'oreille) · `base1-8` Mackogneur (fond holographique
gardé tout autour) · `base1-58` Pikachu (fond violet autour de la tête) — refusées à l'œil, motifs
inscrits au registre.

### Le raté que la planche a attrapé

Première passe, fenêtre d'illustration à 57,5 % de la hauteur : la découpe de **Raichu** était la
ligne de texte « Pokémon Souris. Taille : 0,8 m, poids : 30 kg ». Bien détourée, compacte, d'un seul
tenant — acceptée par tous les critères existants. Deux corrections : la fenêtre est remontée à
52 %, et un critère d'**allongement** (4×) a été ajouté. Raichu est maintenant correct et publié.

C'est la justification concrète de la planche de contrôle : aucune mesure n'aurait trouvé ça seule.

## Écarts au plan

1. **« Segmentation GPU » → segmentation CPU.** Le plan annonçait du GPU sur chimera. La mesure a
   montré qu'un modèle de **4,6 Mo** suffit, en quelques secondes par carte sur CPU : installer
   CUDA et plusieurs gigaoctets de dépendances pour dix-sept images aurait été un coût sans gain.
   La chaîne tourne sur la flotte, hors de la machine qui sert, ce qui était le vrai enjeu.
2. **GrabCut écarté, et pas gardé en repli.** Mesuré et documenté : sur fond holographique il garde
   le fond entier (compacité 0,76-0,79 = un rectangle). Un repli qu'on sait mauvais est un repli
   silencieux ; sans modèle, la chaîne s'arrête (code 3).
3. **Travail conduit sur devAI, pas dans la WSL de chimera.** Le couloir annoncé était chimera, mais
   sa WSL n'a **ni node ni pnpm** et ce lot est majoritairement front. Worktree sur devAI (`/tmp`,
   transit léger), suites front et API lancées là. `/Volumes/Data` est **refusé en écriture**
   (`Operation not permitted`, TCC) — réglage *Confidentialité et sécurité* à faire par JF.
4. **La liste des vedettes n'a pas été établie avec Aymeric.** Session autonome, personne à qui
   demander. Les 17 candidates sont les holos du Base Set plus Pikachu : emblématiques, variées en
   types, reconnaissables par un enfant de onze ans. **Ses préférés restent à intégrer**, et c'est
   une ligne à ajouter au registre, pas un développement.
5. **Les découpes ne sont pas déposées en PROD.** Le lot ne déploie pas (règle du couloir). Le
   passage `--ecrire-registre` sans `--sans-publier` reste à lancer sur l'environnement cible.

## Reste à faire

- Lancer la chaîne sur l'environnement de production pour déposer les 11 découpes dans le stockage
  objet (`uv run python scripts/decouper_apparitions.py` depuis la flotte). **Tant que ce n'est pas
  fait, le registre annonce des URL qui rendront 404** — l'écran dégrade proprement, mais la
  fonctionnalité n'est pas visible.
- Demander ses préférés à Aymeric et les ajouter au registre, par lots.
- Reprendre les six refus : Mélofée, Mackogneur et Pikachu demandent un seuil d'alpha plus strict ou
  un modèle plus gros (`isnet-general-use`) ; Mewtwo et Magnéton sont éclatés par un fond très
  contrasté.
- Ajouter une vignette d'apparition à la galerie `/jeu/effets` — non fait parce qu'elle a besoin
  d'une découpe réellement déposée dans le stockage de l'environnement.
- Un e2e dédié à l'apparition : il demande une partie dont une carte est vedette dans la base e2e.
  Le coût est aujourd'hui borné par un test statique, pas par une mesure au navigateur.

## Points d'attention pour la suite

- **Le `.venv` d'`apps/api` est un lien** vers celui du dépôt principal et son install éditable
  pointe `~/dev/pokeboy`, pas le worktree : toute commande doit passer
  `PYTHONPATH=<worktree>/apps/api/src`, sinon c'est le code de `main` qui est testé.
- La **base de test partagée** `pbm_v2_catalogue_complet_test` (port 55432) était périmée
  (`users.coach_actif` absente) : un `alembic upgrade head` a été lancé dessus. C'est un état
  partagé avec d'autres worktrees, et il a été modifié — dit plutôt que tu.
- `onnxruntime` a été installé dans le `.venv` partagé de devAI pour mesurer. C'est exactement ce
  que fait `uv sync --extra decoupe` ; rien d'autre n'a été touché.
