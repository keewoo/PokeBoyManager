# Compte rendu — `v4-jeu`

Session autonome (`claude -p`) sur chimera, worktree `~/dev/wt-pbm-v4-jeu`, branche
`roadmap/v4-jeu`. Exécuté sous le régime décrit dans le CONTEXTE D'EXÉCUTION du prompt
(sections A/P/0/7 du prompt de lot remplacées) : pas de `suivi.py`, pas d'écriture dans
`etat.json`/`ROADMAP.html`/`BACKLOG.md`/`prompts/`, fusion directe vers `origin/main` (dépôt
relais local, pas GitHub). `v4-anecdotes` (dépendance déclarée) est bien fusionné dans
`origin/main` (`7d7a766`) au démarrage — le garde-fou `suivi.py verifier v4-jeu` renvoie
pourtant code 2 (`etat.json` pas à jour côté ordonnanceur) : ignoré conformément au contexte
d'exécution, qui prime sur la section 0.

**Rebase à la fusion** : `origin/main` a avancé **deux fois** pendant la clôture (v5-rgpd,
v3-detection, v3-identification, puis v1-identite) — la séquence de fusion a donc été rejouée
deux fois (« si `origin/main` a bougé pendant les tests, recommence la séquence »). Conflits
dans `main.py`/`worker.py` (deux routeurs/deux tâches arq à enregistrer côte à côte, pas un
remplacement), `tests/conftest.py` (valeur de repli `TEST_DATABASE_URL`, cosmétique) et
`packages/api-client/src/schema.d.ts` (régénéré plutôt que fusionné à la main, fichier
généré) — résolus en combinant les deux côtés. **Tête de migration à rechaîner deux fois** : ma
migration partageait son `down_revision` avec celle d'un autre lot fusionné entre-temps
(`2e56ba32d5ed` data_exports, puis `328aef94ea58` v1-identite) — rebasée à chaque fois sur la
tête réelle (finalement `328aef94ea58`) pour garder une seule chaîne, sinon `alembic upgrade
head` sur une base neuve aurait créé `card_tournament_presence` sans jamais créer les tables des
lots parallèles. Bases de test **recréées de zéro** après ce correctif : un `alembic_version`
pointant déjà sur ma révision (posée avant la fusion) masquait l'absence réelle des tables des
lots parallèles — `alembic upgrade head` ne rejoue que les révisions manquantes par rapport à ce
pointeur, jamais un contrôle du schéma réel. `/auth/register` a aussi changé de contrat entre
temps (v1-identite : `last_name`/`birth_date`/`accept_terms` désormais requis) —
`tests/test_in_game_study.py` avait copié l'ancien payload d'inscription depuis
`test_card_insights.py` avant ce changement ; corrigé pour reprendre exactement le nouveau
payload déjà utilisé par les autres suites du dépôt.

## Résumé

`GET /cards/{card_id}/in-game-study` combine trois sources indépendantes sur la fiche carte,
onglet « En jeu » :

1. **Légalités et règle des Prix** — déterministe, depuis le catalogue (`Card.legal_standard`/
   `legal_expanded`, suffixe du nom de la carte pour ex/V/VSTAR/GX = 2 Prix, VMAX = 3 Prix).
   Jamais d'IA, jamais de cache (calcul gratuit, doit refléter le catalogue immédiatement).
2. **Présence en tournoi** — source publique Limitless TCG (`robots.txt` vérifié sans
   restriction), rapprochée par date de sortie d'extension (aucun identifiant partagé avec notre
   catalogue), vérifiée une seconde fois par le nom affiché avant d'accepter un résultat.
   Relevé **hebdomadaire** (job arq, jamais à la demande), jamais une carte « probable ».
3. **Synthèse IA** — même patron que les anecdotes (cache partagé par carte, clé de
   l'utilisateur qui ouvre la fiche en premier), mais régénérée si le relevé de tournoi a été
   rafraîchi depuis la dernière synthèse, et visible même sans clé IA pour les points 1 et 2
   (contrairement aux anecdotes, D4 ne masque ici que le point 3).

## Livrables

- `apps/api/src/pbm_api/ingame/rules.py` — `legalities_of`/`prize_rule_of`, purement
  déterministe (`tests/test_ingame_rules.py`, 16 tests dont les suffixes ex/V/VSTAR/VMAX/GX/EX,
  hors-Pokémon, et le piège "Complex" ne doit pas matcher "ex" comme simple terminaison).
- `apps/api/src/pbm_api/ingame/tournaments.py` — `LimitlessTcgClient` (pages HTML publiques,
  aucune clé), parsing par expressions régulières ciblées (stdlib uniquement, pas de nouvelle
  dépendance HTML — la structure des deux pages exploitées est stable et étroite),
  `match_set_code` (rapprochement par date de sortie, départagé par nom si ambiguïté),
  `find_card_page` (rapprochement + vérification du titre affiché, ne renvoie qu'un résultat
  vérifié ou `None`). `LimitlessBlockedError` sur HTTP 403/429.
- `apps/api/src/pbm_api/ingame/tournaments_job.py` — `refresh_tournament_presence`, patron
  identique à `pbm_api.pricing.service` (reprise à la carte près, upsert idempotent, bridé aux
  cartes légales dans au moins un format, concurrence 1 — site tiers à ménager).
- `apps/api/src/pbm_api/ingame/generation.py`/`service.py` — synthèse IA (`AIProvider.extract`
  sur prompt texte, comme `v4-anecdotes`), cache partagé (`card_insights`, verrou consultatif
  Postgres sur un espace de nom dédié), régénération si `tournament.checked_at` postérieur à
  `game_study_generated_at`.
- `apps/api/src/pbm_api/routers/in_game_study.py` — la route, câblée dans `main.py`.
- `apps/api/src/pbm_api/models/catalog.py` — `CardTournamentPresence` (nouvelle table) ;
  `CardInsight` gagne `game_study_source_model`/`game_study_generated_at`/
  `game_study_cached_until`, un triplet **distinct** de celui des anecdotes (le même
  `cached_until` aurait fait apparaître un `card_insights` « frais » pour l'étude en jeu sans
  que les anecdotes n'aient jamais été générées, et réciproquement).
- `apps/api/migrations/versions/5e8f243e399f_...py` — table + colonnes, aller-retour
  upgrade/downgrade/upgrade vérifié sur `pbm_v4_jeu_test` (l'enum Postgres doit être
  explicitement supprimée en downgrade, absent de l'autogénération Alembic par défaut).
- `apps/api/src/pbm_api/worker.py` — `weekly_tournament_presence_task`, cron Lundi 08:00
  (décalé des jobs 06:00 pour ne pas cumuler catalogue+prix+tournoi sur la même fenêtre réseau).
- `apps/api/scripts/prove_ingame_20_cards.py` — preuve du livrable sur 20 cartes réelles
  (résultat collé ci-dessous, réseau réel vers Limitless TCG).
- `apps/api/scripts/test_ingame_manual.py` — essai manuel avec une vraie clé IA.
- `docs/ARCHITECTURE.md` — section « Étude d'utilisation en jeu (lot `v4-jeu`) ».
- `packages/api-client/src/schema.d.ts` régénéré (`pnpm gen:api`).
- Base dédiée sur l'infra partagée `pbm-shared` : `pbm_v4_jeu` (dev), `pbm_v4_jeu_test` (tests,
  migrées via `alembic upgrade head`), `apps/api/.env` local (gitignored), `REDIS_PREFIX=
  pbm:v4-jeu:`, `S3_BUCKET=pbm-v4-jeu` (inutilisé par ce lot — aucune photo touchée).

## Tests

```
$ cd apps/api && uv run ruff check .
All checks passed!

$ TZ=Europe/Paris uv run pytest -q   # avant rebase : 329 passed (284 préexistants + 45 nouveaux)
329 passed in 32.59s

$ TZ=Europe/Paris ... uv run pytest -q   # rejoué après le 2e rebase sur origin/main (v5-rgpd,
395 passed in 45.44s                     # v3-detection, v3-identification, v1-identite) :
                                          # 350 préexistants (dont les lots parallèles) + 45
                                          # nouveaux, base recréée de zéro sur la chaîne de
                                          # migration corrigée, payload /auth/register aligné
```

Détail des 45 nouveaux, isolément :

```
$ uv run pytest tests/test_ingame_rules.py tests/test_ingame_tournaments.py \
    tests/test_ingame_tournaments_job.py tests/test_in_game_study.py -q
45 passed in 2.7s
```

- `test_get_in_game_study_requires_authentication`/`test_get_in_game_study_returns_404_for_
  unknown_card` **échouent sans ce lot** (`404 Not Found` de FastAPI faute de routeur) et
  passent une fois branché.
- **Preuve ciblée « D4 partiel »** (choix de conception, mission points 1/2 indépendants du
  point 3) : `test_get_in_game_study_without_default_key_still_exposes_deterministic_data` —
  vérifié en retirant temporairement le retour anticipé dans `pbm_api.ingame.service` pour
  faire lever `NoAiKeyConfiguredError` sans clé (comme les anecdotes) : le test échoue alors en
  recevant un 502 (l'exception non attrapée par le routeur, qui n'a plus de branche pour elle)
  au lieu des légalités/règle des Prix/présence en tournoi ; remis en place, il repasse.
- **Preuve ciblée « étude figée »** : `test_get_in_game_study_regenerates_the_study_after_a_
  newer_tournament_refresh` — vérifié en retirant temporairement la comparaison
  `tournament_checked_at > card_insight.game_study_generated_at` dans `_study_fresh` : le test
  échoue alors en recevant l'ancien texte (« Rôle initial ») après le rafraîchissement du
  relevé de tournoi ; remis en place, il repasse avec le nouveau texte et un seul appel IA par
  génération (`len(created) == 1` à chaque étape).
- **Accès croisé (donnée partagée)** : comme `v4-anecdotes`, `card_insights`/
  `card_tournament_presence` sont des caches **partagés** entre utilisateurs par construction
  (une ligne par carte, pas de `user_id`) — pas de 404 à tester ici. L'équivalent :
  `test_second_user_reads_the_shared_study_cache_without_owning_a_key` (un utilisateur B sans
  clé IA lit la synthèse générée par A, sans jamais déclencher un second appel IA).
- **Rapprochement Limitless** (`tests/test_ingame_tournaments.py`, 15 tests) : parsing
  d'extraits HTML synthétiques mais structurellement fidèles aux pages réelles (mêmes classes
  CSS), `test_find_card_page_rejects_a_name_mismatch` est la preuve ciblée du risque
  « inventer un résultat de tournoi » — un rapprochement par date+numéro correct mais dont le
  titre affiché ne correspond pas est rejeté (`None`), jamais une carte « probable ».
- **Relevé périodique** (`tests/test_ingame_tournaments_job.py`, 6 tests) : reprise après échec
  d'une seule carte (`test_refresh_continues_after_a_single_card_failure`, la carte en échec
  n'est jamais écrite), idempotence de l'upsert, cartes hors format ignorées, blocage du site
  interrompt le relevé (`LimitlessBlockedError` propagée).
- **Cache** : `test_get_in_game_study_uses_cache_on_second_call_without_calling_ai_again` — un
  deuxième appel sur la même carte ne recrée aucun fournisseur IA.

Rejoué avec les variables d'environnement de la CI (`DATABASE_URL`/`TEST_DATABASE_URL`/
`REDIS_URL`/`S3_*`/`TZ=Europe/Paris`, comme `.github/workflows/ci.yml`), **après le second
rebase sur `origin/main`** (v5-rgpd, v3-detection, v3-identification, v1-identite — voir note de
rebase en tête de ce document) et base de test recréée de zéro sur la chaîne de migration
corrigée : suite complète verte (395 passés), aucune régression sur les lots parallèles.
Migration : `alembic upgrade head` → `downgrade -1` → `upgrade head` sur `pbm_v4_jeu_test` →
aller-retour propre après correction (l'enum `tournament_presence_status` doit être supprimée
explicitement en downgrade, l'autogénération Alembic ne le fait pas).

Recherche de motifs de clé/secret sur les fichiers ajoutés → aucun résultat (ce lot ne stocke ni
ne journalise aucune clé IA ; il lit la clé déjà déchiffrée par `pbm_api.security.crypto.
decrypt_api_key`, comme `v4-anecdotes`).

`pnpm --filter @pbm/web type-check` → aucune erreur (client régénéré compatible).

## Preuve du livrable « onglet En jeu alimenté pour 20 cartes de test » (réseau réel)

`scripts/prove_ingame_20_cards.py` interroge le vrai Limitless TCG pour 20 cartes réelles
couvrant chaque catégorie de règle des Prix (standard, ex, VSTAR, VMAX) et deux catégories de
carte (Pokémon, Dresseur) :

```
$ uv run python scripts/prove_ingame_20_cards.py
Charizard ex             status=unavailable prize=2 Prix (carte ex)
Pikachu ex               status=checked   decks=0 prize=2 Prix (carte ex)
Mewtwo                   status=checked   decks=0 prize=1 Prix (carte standard)
Gardevoir ex             status=unavailable prize=2 Prix (carte ex)
Miraidon ex              status=checked   decks=0 prize=2 Prix (carte ex)
Koraidon ex              status=checked   decks=8 prize=2 Prix (carte ex)
Chien-Pao ex             status=checked   decks=8 prize=2 Prix (carte ex)
Iron Hands ex            status=checked   decks=8 prize=2 Prix (carte ex)
Gholdengo ex             status=checked   decks=8 prize=2 Prix (carte ex)
Roaring Moon ex          status=checked   decks=8 prize=2 Prix (carte ex)
Rare Candy               status=checked   decks=8 prize=Non applicable (hors Pokémon)
Nest Ball                status=checked   decks=8 prize=Non applicable (hors Pokémon)
Ultra Ball               status=checked   decks=8 prize=Non applicable (hors Pokémon)
Boss's Orders            status=checked   decks=8 prize=Non applicable (hors Pokémon)
Professor's Research     status=checked   decks=8 prize=Non applicable (hors Pokémon)
Arceus VSTAR             status=checked   decks=8 prize=2 Prix (carte VSTAR)
Giratina VSTAR           status=checked   decks=8 prize=2 Prix (carte VSTAR)
Lugia VSTAR              status=checked   decks=8 prize=2 Prix (carte VSTAR)
Rayquaza VMAX            status=checked   decks=4 prize=3 Prix (carte VMAX)
Snorlax                  status=checked   decks=0 prize=1 Prix (carte standard)

18/20 cartes rapprochées avec succès sur Limitless TCG.
```

→ 18/20 cartes avec légalités+règle des Prix+présence en tournoi alimentées de bout en bout
contre le vrai site. Les **2 « unavailable » sont un succès du filtre anti-mismatch, pas un
échec** : `ASC/22` existe bien sur Limitless mais son titre réel est *« Mega Charizard Y ex »*,
pas *« Charizard ex »* (vérifié manuellement, `curl` collé ci-dessous) — le nom choisi pour la
preuve provenait d'une recherche approximative par mot-clé côté script, pas du vrai catalogue.
`find_card_page` a correctement rejeté le rapprochement plutôt que d'afficher la présence en
tournoi d'une **autre** carte sous le nom « Charizard ex » :

```
$ curl -s https://limitlesstcg.com/cards/ASC/22 | grep -o '<title>[^<]*</title>'
<title>Mega Charizard Y ex - Ascended Heroes (ASC) #22 – Limitless</title>
```

C'est exactement le risque de la mission (« ne jamais inventer un résultat de tournoi ») pris
sur le vrai site, pas seulement dans un test synthétique — la défense tient en conditions
réelles. Dans le vrai flux (catalogue importé par `v2-catalogue`), ce problème ne se posera pas :
le nom/numéro/extension proviennent de TCGdex, pas d'une recherche par mot-clé.

## Choix techniques

- **Rapprochement par date de sortie d'extension, jamais par similarité de nom** : Limitless TCG
  n'a aucun identifiant en commun avec notre catalogue (TCGdex/Pokémon TCG API), et les noms
  d'extension sont en français côté catalogue contre anglais côté Limitless. `Set.release_date`
  (posée par TCGdex, la vraie date d'impression officielle) est identique quelle que soit la
  source — une clé de jointure fiable là où le nom ne l'est pas. Départagé par nom normalisé
  seulement en cas d'ambiguïté sur la date (rare).
- **Vérification du titre affiché avant d'accepter un résultat** : même après un rapprochement
  d'extension et de numéro corrects, un décalage de catalogue pourrait pointer vers la mauvaise
  carte au sein de la bonne extension. Coût nul (le titre est déjà dans la page récupérée),
  gain : jamais de présence en tournoi affichée pour la mauvaise carte (preuve en conditions
  réelles ci-dessus).
- **Relevé hebdomadaire par job arq, jamais à la demande** : Limitless TCG est un site tiers
  sans API dédiée (contrairement à TCGdex/Pokémon TCG API) — une requête par ouverture de fiche
  serait discourtoise et lente (chimera plafonne à ~250 ko/s). Bridé aux cartes légales dans au
  moins un format (Standard ou Étendu) : une carte rotée depuis longtemps n'apporte rien à
  « est-ce que cette carte sert encore ? » et alourdirait le relevé sans utilité.
- **Parsing HTML par expressions régulières ciblées, pas de nouvelle dépendance** : deux pages
  seulement à exploiter (index des extensions, page carte), structure stable et étroite (une
  poignée de balises), vérifiées contre le vrai site le 2026-09-19. Cohérent avec le choix déjà
  fait pour les fournisseurs IA (`docs/ARCHITECTURE.md` § « Fournisseurs IA » : HTTP direct,
  « jamais un SDK de plus à auditer »).
- **`game_study_generated_at`/`cached_until`/`source_model` distincts de ceux des anecdotes** :
  les deux synthèses (anecdotes, étude en jeu) partagent la table `card_insights` mais sont
  générées à des moments différents ; un seul triplet aurait fait apparaître l'une "fraîche"
  sans que l'autre n'ait jamais été générée (bug détecté en conception, avant tout code, en
  relisant `pbm_api.insights.service._fresh`).
- **Régénération de la synthèse IA sur relevé de tournoi plus récent** : un cache figé à 30 jours
  pourrait continuer d'affirmer une absence de présence en tournoi devenue inexacte après le
  relevé hebdomadaire suivant — la fraîcheur de la synthèse suit désormais la fraîcheur des
  données qu'elle résume, pas seulement une horloge.
- **D4 partiel** (absence de clé IA) : contrairement aux anecdotes, ne masque que la synthèse.
  Légalités/règle des Prix/présence en tournoi ne dépendent d'aucune IA — les masquer aurait
  réduit un livrable entièrement disponible sans clé.
- **Attaques/talents en passthrough `list[dict]`, pas de schéma Pydantic dédié** : leur forme
  vient telle quelle de TCGdex (déjà stockée en JSONB par `v2-catalogue`) et n'est interprétée
  par aucun autre consommateur du dépôt à ce jour — un schéma strict aurait ajouté une
  abstraction sans bénéfice mesurable pour ce lot.

## Écarts au plan

- Aucune réduction de périmètre : les trois points de la mission (légalités/règles,
  présence en tournoi avec source/date affichées, synthèse IA en cache partagé) sont faits, sur
  20 cartes de test réelles.
- La mission envisageait explicitement que la présence en tournoi puisse être « sinon section
  masquée » si les conditions ne le permettent pas : `robots.txt` de Limitless TCG autorise tout
  (`Disallow:` vide, vérifié le 2026-09-19), le relevé est donc actif — la clause de masquage
  reste néanmoins codée et exercée (carte non rapprochée, ou blocage HTTP 403/429 en cours de
  relevé) plutôt que supprimée, pour rester robuste si Limitless changeait sa politique.

## Reste à faire (pour les lots suivants)

- `v4-fiche` : brancher l'onglet « En jeu » sur `GET /cards/{card_id}/in-game-study` (front
  actuellement un simple `EmptyState`, `apps/web/src/app/carte/[id]/page.tsx`) — aucun wrapper
  `apps/web/src/lib/api/in-game-study.ts` écrit par ce lot (back-end seul, comme
  `v4-anecdotes`/`v4-ranking`).
- Revalider le taux de rapprochement Limitless TCG (18/20 sur cet échantillon, dont les 2
  `unavailable` sont un choix de nom de test imprécis, pas un défaut du code — voir preuve
  ci-dessus) une fois le catalogue réel importé par `v2-catalogue` : les noms/numéros/extensions
  viendront alors de TCGdex, pas d'une recherche par mot-clé approximative.
- Historiser la présence en tournoi (actuellement un seul relevé écrasé chaque semaine,
  `UniqueConstraint(card_id)`) si un jour la mission demande une tendance dans le temps plutôt
  qu'un instantané — non demandé par ce lot.

## Décisions provisoires utilisées

D3 (sources de prix gratuites + historique par nos relevés) : étendu par analogie à la source de
tournoi (Limitless TCG, gratuite, publique) — cohérent avec l'esprit de la décision, pas de
nouvelle décision provisoire distincte nécessaire. D2/D8 hors périmètre, confirmé (aucun
déploiement, aucune tâche `release_uat`/`release_prod` traitée). D4 (sans clé IA →
reconnaissance désactivée, ajout manuel toujours possible) : appliqué avec la nuance documentée
ci-dessus (masque uniquement la synthèse, pas les données déterministes). D5/D6/D7 sans objet
pour ce lot (aucun e-mail, aucun classement, aucune photo touchés).
