# `j-echanges-emotes` — Emotes prédéfinies : se parler sans chat libre

**Lot** P2 · piste Serveur de parties · couloir J-SRV · jalon **J4** · palier 11 · taille S
**Session** autonome `claude -p`, pilotée depuis **devAI**, worktree `~/dev/wt-j-echanges-emotes`
sur **chimera**, branche `roadmap/j-echanges-emotes` depuis `github/main` (`cf9070f`), puis
fusionnée avec `main` (`88b640c`, arrivée de `j-accessibilite-jeu`) avant le push final.

**Où le travail a tourné, et pourquoi.** Le code est écrit, commité, poussé et fusionné sur
**chimera** (le couloir du lot). Les suites **front** et l'**e2e navigateur** ont été exécutées sur
**devAI** : la WSL de chimera n'a ni Node ni pnpm, et Playwright n'y démarre pas (fait connu du
dépôt). Les suites Python ont tourné **sur les deux**. Un arbre de travail jetable a vécu dans
`/tmp` sur devAI (`/Volumes/Data` refuse l'écriture depuis une session agent — TCC), supprimé à la
fin. Le refus d'écriture est signalé ici plutôt que passé sous silence : la règle de flotte veut
`/Volumes/Data` pour tout fichier en transit, et c'est un réglage de confidentialité macOS à refaire
par JF, pas un volume absent.

**Décision appliquée** : **DJ10** (JF, 14/10/2026) — *« Emotes prédéfinies seulement ("bien joué",
"oups", "ton tour"), désactivables, jamais de texte libre. »*

## Résumé

Les deux joueurs peuvent s'envoyer **dix phrases prédéfinies** pendant une partie, par le canal
temps réel déjà en place. Le serveur n'accepte qu'un **code** d'une liste fermée : il n'existe, dans
toute l'interface de plateau comme dans toute l'API, **aucun chemin par lequel une phrase saisie par
un joueur atteindrait l'autre**. Chacun peut **couper** les emotes d'un clic — effet immédiat et
choix mémorisé côté compte. Le débit est limité (1 s minimum entre deux, 5 par 20 s) et le refus
annonce le délai. **Rien d'une emote n'est conservé au-delà de la partie** : pas de journal, pas de
table, pas de compteur ; le seul octet persisté est le réglage du joueur.

Le moteur (`pbm_game`) n'a **pas été touché** : une emote n'est pas un coup, aucune règle `R-x.y` du
corpus ne s'y applique, et un test interdit désormais le mot « emote » dans le paquet moteur.

## Livrables

| Quoi | Où |
|---|---|
| Règles pures : catalogue fermé, débit, défauts, codes d'erreur | `apps/api/src/pbm_api/games/emotes.py` |
| Mécanique : réglage en base, limiteur en mémoire, diffusion | `apps/api/src/pbm_api/games/emotes_service.py` |
| Transport : `Hub.publier_emote`, `Hub.user_ids`, message client `emote` | `apps/api/src/pbm_api/games/temps_reel.py` |
| Purge du limiteur au départ du dernier abonné | `apps/api/src/pbm_api/routers/games_ws.py` |
| Table du réglage + migration (`b8d3f0c47a51`) | `apps/api/src/pbm_api/models/jeu_emotes.py`, `apps/api/migrations/versions/b8d3f0c47a51_emotes_reglages.py` |
| Routes `GET /jeu/emotes/catalogue`, `GET\|PATCH /jeu/emotes/reglages` | `apps/api/src/pbm_api/routers/jeu_emotes.py` (monté dans `main.py`) |
| Catalogue et types côté écran | `apps/web/src/lib/game/emotes.ts` |
| `CanalPartie.envoyerEmote` / `onEmote` / `onEmoteRefusee` | `apps/web/src/lib/game/realtime.ts` |
| Client HTTP du réglage | `apps/web/src/lib/api/emotes.ts` |
| Palette d'emotes (hors flux, flanc droit) | `apps/web/src/components/game/emote-bar.tsx` |
| Branchement sur le plateau | `apps/web/src/app/jeu/parties/[id]/partie-view.tsx` |
| **Fiche durable** | `docs/jeu/EMOTES.md` (+ ligne dans la carte des fiches de `CLAUDE.md`) |
| Renvois | `docs/ARCHITECTURE.md`, `docs/UI-UX.md`, `docs/jeu/TEMPS-REEL.md` (tables du protocole) |

### Le catalogue, et la règle qui l'a choisi

La mission demandait de « définir la liste avec JF ». La session est autonome : **personne ne pouvait
répondre**. La liste a donc été dérivée de DJ10 et du plan du lot (qui nomme « bien joué », « oups »,
« ton tour », « belle carte »), complétée selon une **règle écrite** qui répond au point 1 de la
mission (« aucune ne peut servir à narguer ») :

> **Une emote parle de son auteur, ou félicite l'autre. Jamais l'inverse.**

« Oups… » dit *je me suis trompé*, pas *tu t'es trompé* ; aucune emote ne commente le coup de
l'adversaire autrement que pour le saluer. Les dix : `bonjour`, `bonne_partie`, `bonne_chance`,
`bien_joue`, `belle_carte`, `merci`, `oups`, `je_reflechis`, `un_instant`, `ton_tour`.

La liste est **figée par un test** des deux côtés : en ajouter une oblige à repasser par cette
règle. **JF peut en retirer une d'un mot** (une ligne du tuple `CATALOGUE` + le test qui la nomme).

## Preuves

### Critères d'acceptation du lot

| Critère | Preuve |
|---|---|
| **Aucune saisie de texte libre n'existe dans l'interface de jeu** | `e2e/emotes.spec.ts` compte `input, textarea, [contenteditable]` dans le DOM réel, **palette ouverte** → `0`. Côté serveur, `test_aucun_texte_ne_traverse` rejette six charges (phrase, vide, entier, `None`, liste, objet) ; `test_aucune_route_http_nenvoie_une_emote` vérifie sur le schéma OpenAPI qu'il n'existe aucune route d'envoi ni aucun chemin « chat »/« message » |
| **Couper les emotes est immédiat et mémorisé** | `test_coupure_immediate_sans_reconnexion` : une 1re emote atteint B, B coupe **sans rien rouvrir**, la 2e ne l'atteint plus (la diffusion relit le réglage à chaque emote). `e2e/emotes.spec.ts` : la palette disparaît au clic, et le réglage **survit à un `page.reload()`** |
| **Le débit est limité et testé** | 6 tests purs sur `debit_autorise` (intervalle minimal, quota de fenêtre, reconstitution du quota, délai annoncé) + `test_debit_depasse_refuse_avec_le_delai` de bout en bout. Les deux limites sont publiées par `GET /jeu/emotes/catalogue` pour que l'écran grise la palette **avant** le refus |

### Mission, point 3 : « ne rien persister au-delà de la partie »

- `test_emote_nentre_pas_dans_le_journal` — on pilote un **vrai canal**, on envoie une emote comme
  le ferait le navigateur, l'écho revient, et `games.current_numero` **n'a pas bougé** : l'emote
  n'est pas entrée dans le journal, donc ni rejeu, ni replay, ni resynchronisation ne la portent.
- `test_limiteur_oublie_la_partie` + purge dans `games_ws.py` quand le dernier abonné s'en va.
- `test_le_moteur_ne_connait_pas_les_emotes` — aucune mention d'« emote » dans `pbm_game`.
- `test_le_module_de_regles_des_emotes_est_pur` — relevé **statique** des imports de `emotes.py` :
  `{__future__, collections, dataclasses}` et rien d'autre (ni base, ni réseau, ni horloge).

### Un test qui échoue sans le changement — vérifié, pas supposé

| Garde | Expérience | Résultat |
|---|---|---|
| le canal porte l'emote | suppression du `case "emote"` de `realtime.ts` | **2 tests rouges** sur 9, puis verts après restauration |
| inventaire des champs de saisie | ajout d'un `<textarea placeholder="Dis quelque chose" />` dans `emote-bar.tsx` | rouge, en **nommant l'offender** : `Champ(s) de saisie non déclaré(s) … [('emote-bar.tsx', 'textarea')]` |

### Suites exécutées (sur la flotte, jamais sur le Mac de JF)

Toutes les mesures ci-dessous sont celles de l'arbre **après fusion de `main`** (voir « La fusion »).

| Suite | Résultat |
|---|---|
| `apps/api` — `uv run pytest -q` | **1 385 passés**, 2 échecs d'environnement + 1 erreur transitoire (voir « Écarts ») — dont **40 nouveaux** tests d'emotes |
| `apps/game` — `uv run pytest -q` | **1 138 passés** (moteur intact) |
| `apps/api` + `apps/game` — `ruff check .` | **All checks passed** |
| `apps/web` — `tsc --noEmit` | propre |
| `apps/web` — `eslint .` | 0 erreur (1 avertissement **préexistant** dans `game-realtime.test.ts`) |
| `apps/web` — `vitest run` | **541 passés, 0 échec** — dont **25** nouveaux/étendus sur les emotes |
| `apps/web` — `next build` | réussi |
| e2e Playwright — `emotes`, `a11y-jeu`, `plateau-responsive`, `plateau-rendu` | **16 passés** |
| e2e Playwright — `anim-fluidite` | 1 passé, **1 échec de machine** (voir « Écarts ») |

L'audit d'accessibilité du plateau (`a11y-jeu.spec.ts`, arrivé sur `main` pendant ce lot) passe
**avec la palette montée** : contraste, taille de cible minimale, parcours au clavier et texte
agrandi sans défilement.

Migrations : `alembic upgrade head` rejoué **de zéro** sur deux bases neuves (devAI et chimera) et sur
la base e2e. `alembic heads` après fusion de `main` : **une seule tête**, `a7e4c2b9d518`.

Les 40 tests d'emotes de l'API ont aussi été exécutés **sur chimera** (la machine du couloir), base
`pbm_emotes_test` créée et migrée pour l'occasion : **40 passés**, `ruff` propre sur `apps/api` et
`apps/game`.

## La fusion — `main` avait bougé, et ça n'était pas sans conséquence

`main` est passé de `cf9070f` à `88b640c` pendant le lot : **`j-accessibilite-jeu`** y a été intégré,
et il touche le plateau (`partie-view.tsx`, `game-board.tsx`, `journal-panel.tsx`, `globals.css`) et
ajoute un audit e2e. Trois choses à signaler :

1. **Deux conflits**, tous deux « les deux lots ajoutent une ligne » : `main.py` (un routeur de plus
   chacun) et `models/__init__.py` (un modèle de réglages de plus chacun). Résolus en gardant les
   deux côtés, dans l'ordre du dépôt. Commit `b7b28d3`.
2. **Deux têtes Alembic** — le piège exact que ce dépôt connaît : chaque lot avait ajouté sa
   révision, et `alembic upgrade head` refuse alors d'avancer… **mais seulement sur `main`**, donc la
   CI de chaque branche restait verte. Détecté en lançant `alembic heads` **dans la branche après la
   fusion, avant de pousser**. Migration de fusion **vide** `a7e4c2b9d518`, et `upgrade head` rejoué
   depuis une base vierge pour le prouver. Commit `c803f74`.
3. **Toutes les suites ont été relancées** sur l'arbre fusionné, pas seulement celles du lot — c'est
   ce qui permet d'affirmer que l'audit d'accessibilité passe avec la palette, et que les
   15 échecs `app-shell*` constatés avant la fusion ont **disparu** (le lot d'accessibilité a corrigé
   `vitest.setup.ts`, qui était la cause).

## Écarts, et ce qu'ils ne sont pas

1. **`apps/api` : 2 échecs, `tests/test_catalogue_seed.py`.** Cause lue, pas devinée :
   `pg_dump: command not found` — le client PostgreSQL n'est pas installé sur devAI. Sans rapport
   avec ce lot (le script de seed du catalogue n'y est pas touché) ; la CI a `postgresql-client`.
2. **`apps/api` : 1 erreur transitoire, sur un test *différent à chaque passage*.**
   `ConnectionError: PostgreSQL server at "localhost:55432" rejected SSL upgrade`, au **setup** d'un
   test — `test_adversaire_ia.py` au premier passage, `test_jeu_confort.py` au second. Les deux
   passent **isolément** (11 passés pour `test_adversaire_ia.py`). C'est le Postgres local de devAI
   qui refuse une connexion sous la charge de la suite complète, pas un défaut du code ; la CI
   utilise un conteneur de service dédié.
3. **`anim-fluidite.spec.ts`, plancher de 30 images/s : échec.** Mesuré **avec** la palette :
   14,5 img/s. Mesuré **sans** (la `partie-view.tsx` de `cf9070f` remise en place, serveurs e2e
   relancés) : **10,2 img/s**. L'échec est donc celui de la machine, pas du lot — et la palette
   mesure *plus haut* que la base de référence (bruit). Le plancher est calibré pour l'appareil de
   référence sur runner dédié ; la CI fait foi.
4. **Point 1 de la mission (« définir la liste avec JF ») : fait sans JF**, règle écrite à la place
   (voir plus haut). **Attendu de JF** : un simple oui, ou le retrait d'une emote.
5. **Pas de livraison en PROD.** Hors périmètre de ce lot (la PROD se livre à part, par devAI).
   Les migrations `b8d3f0c47a51` (table du réglage) et `a7e4c2b9d518` (fusion de têtes, vide) seront
   à jouer à cette occasion.

## Décisions prises dans le lot (et pourquoi)

- **Un seul interrupteur pour les deux sens** (coupé : ni reçu, ni envoyé) plutôt que deux
  réglages. Un demi-réglage — « je ne te lis pas mais je te parle » — est précisément la position
  qui sert à narguer, et un interrupteur unique se comprend d'un coup d'œil.
- **Aucune route HTTP d'envoi, aucun repli dégradé.** Une route voudrait dire une file d'attente,
  donc un stockage — ce que le lot interdit. En connexion dégradée la palette est désactivée **et le
  dit** (« Les emotes demandent la connexion directe ») plutôt que de faire semblant.
- **Une emote n'est pas rattrapable**, par construction. Une file d'abonné saturée la perd, et
  l'écrit dans le journal technique (jamais en silence) : l'alternative serait d'afficher « Bien
  joué ! » dix secondes trop tard, sur un coup qui n'est plus le bon. C'est pourquoi
  `publier_emote` ne marque **pas** l'abonné « saturé » — cela déclencherait une resynchronisation
  complète pour un message que la resync ne contient même pas.
- **On ne dit pas à l'émetteur que l'adversaire l'a coupé.** L'emote part, elle n'est délivrée à
  personne, l'écho revient normalement. L'annoncer transformerait un réglage de confort en
  information sociale, donc en reproche.
- **Le réglage est relu à chaque emote**, pas une fois à l'abonnement : c'est la seule façon que
  « couper » soit *immédiat* sans F5. Le coût est une requête par emote, bornée par un débit de 5
  emotes / 20 s.
- **Palette sur le flanc droit, à mi-hauteur, `fixed`.** Les cinq autres emplacements du plateau
  sont pris, et deux portent des boutons que l'e2e clique vraiment (`anim-sauter` notamment — la
  fiche de `aide-panel.tsx` raconte ce que coûte de l'avoir oublié).

## Limite connue, nommée

**Le limiteur de débit est en mémoire du process**, exactement comme le `Hub` dont il partage la
portée (documentée depuis `j-temps-reel`). Les emotes d'un joueur passent toutes par le process qui
tient *sa* WebSocket, donc son débit est bien compté pour la connexion qui l'émet ; mais une
reconnexion sur un **autre** process repartirait sur un budget neuf. Borne assumée pour un jeu privé
entre comptes invités (D11), à revoir le jour où l'API tournera en plusieurs réplicas — c'est écrit
dans `docs/jeu/EMOTES.md` et dans la docstring du module.

## Reste à faire

- **Validation de JF sur le catalogue** (ou retrait d'une emote).
- **Livraison PROD** par devAI, migration `b8d3f0c47a51` comprise.
- Rien d'autre : aucun lot aval ne dépend de celui-ci.

## Reproduire les mesures

```bash
# API (base de test dédiée, migrée depuis zéro)
cd apps/api && TEST_DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_emotes_test \
  TZ=Europe/Paris LANG=fr_FR.UTF-8 uv run pytest -q tests/test_jeu_emotes*.py
# Moteur (doit rester intact et sans emotes)
cd apps/game && uv run pytest -q
# Écran
pnpm --filter @pbm/web exec vitest run src/lib/game/emotes.test.ts \
  src/__tests__/emote-bar.test.tsx src/__tests__/game-realtime.test.ts
# Navigateur réel (devAI : Postgres :55432, Redis :56379, MinIO :59000)
cd apps/web && pnpm exec playwright test e2e/emotes.spec.ts e2e/plateau-responsive.spec.ts
```
