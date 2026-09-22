# Services tiers — ce qui est branché, ce qui ne l'est pas

> **À lire avant d'ajouter une dépendance externe.** Tout ce que le produit appelle hors de chez
> lui : catalogue, prix, IA, e-mails, stockage — et les outils de pilotage qu'on envisage de
> brancher.
> Ce qui n'est pas ici : la façon dont l'API s'en sert (`docs/ARCHITECTURE.md`), les clés en
> production (`docs/LIVRAISON.md`).
> Tous les chemins sont donnés **depuis la racine du dépôt**.

## Les quatre règles

1. **Une clé ne vit jamais dans le dépôt.** Variable d'environnement, hors dépôt, jamais dans un
   journal, jamais dans une réponse d'API, jamais dans une sortie de commande.
2. **Un service tiers a un mode dégradé écrit.** Que se passe-t-il quand il répond 500, quand il
   est lent, quand le quota est atteint ? La réponse est dans le code ET dans cette fiche. « Ça
   n'arrivera pas » n'est pas un mode dégradé.
3. **Un service payant a un plafond**, vérifié avant la dépense, pas après.
4. **Un seul point d'entrée par service** dans le code. Deux appels au même service depuis deux
   endroits, c'est deux comportements le jour où il tombe.

## Branché, en service

| Service | Ce qu'il apporte | Où, dans le code | Clé | Si ça tombe |
|---|---|---|---|---|
| **TCGdex** (`api.tcgdex.net`) | catalogue FR + EN, images officielles, prix Cardmarket | `pbm_api.worker`, `pbm_api.routers.images` | aucune | le catalogue est déjà en base : lecture inchangée, seule la mise à jour attend |
| **Pokémon TCG API** (`api.pokemontcg.io`) | prix TCGplayer, légalités | `pbm_api.catalog.ptcg_client` | aucune à ce jour | idem : le relevé du jour manque, et **ça se voit** (un relevé vide est une panne, pas un zéro) |
| **BCE** (`ecb.europa.eu`) | taux de change pour ramener les prix en euros | `pbm_api.pricing.exchange_rates` | aucune | dernier taux connu conservé, avec sa date — jamais un taux inventé |
| **Anthropic / Google / OpenAI** | reconnaissance des cartes par l'IA **de l'utilisateur** | `pbm_api.ai.{anthropic,gemini,openai}`, fabriqués par `pbm_api.ai.factory` | **celle de l'utilisateur** (coffre chiffré AES-256-GCM, lot `v1-byok`) | erreurs normalisées (`pbm_api.ai.errors`), chacune avec un message prêt à afficher ; sans clé, la reconnaissance est désactivée et l'ajout manuel reste possible (D4) |
| **Anthropic / Google / OpenAI — assistant de deck** | un deck légal proposé à partir de la collection, expliqué carte par carte (lot `v7-deck-ia`) | `pbm_api.decks.ai_builder` (`POST /me/decks/{id}/propose`) | **celle de l'utilisateur** (coffre chiffré) | **un seul appel** par proposition ; sans fournisseur par défaut → 409 (D4) ; la proposition est corrigée et sa légalité recalculée côté serveur, jamais montrée telle quelle |
| **Anthropic — clé PLATEFORME** | pré-génération des anecdotes et de l'étude en jeu pour **toutes** les cartes | `scripts/run_insights_batch.py` | `PLATFORM_ANTHROPIC_API_KEY` + `INSIGHTS_BUDGET_EUR` | sans clé **ni** budget, le script **refuse de dépenser** — c'est voulu (D4) |
| **PokéPedia** (`pokepedia.fr`) | sources des anecdotes | `pbm_api.insights.service`, `pbm_api.routers.card_insights` | aucune | l'anecdote est rendue sans sa source plutôt qu'inventée |
| **Limitless TCG** (`limitlesstcg.com`) | présence en tournoi | `pbm_api.ingame.tournaments` | aucune | l'étude en jeu se rend sans la partie tournoi, et le dit |
| **Have I Been Pwned** | refus des mots de passe déjà compromis | `pbm_api.security.compromised` | aucune (k-anonymat : le mot de passe ne sort jamais) | on **n'assouplit pas** la règle en silence : indisponible = on le journalise |
| **SMTP** | vérification d'adresse, mot de passe oublié, lien d'export RGPD | `SMTP_*` de `pbm_api.config.Settings` | selon l'hôte | Mailpit en dev (port 51025) ; en PROD, un e-mail non parti est une panne visible |
| **Stockage objet S3 / MinIO** | photos envoyées | `STORAGE_BACKEND=s3` (dev/CI) — `local` en PROD (D7, `PHOTOS_STORAGE_PATH`) | `S3_*` | en `s3`, l'origine doit être dans la CSP `connect-src` du middleware, sinon **tout envoi de photo échoue** |

## Envisagé, **pas** branché

Vérifié dans le dépôt et dans la configuration de ce poste le 22/09/2026 :

| Candidat | Pour quoi faire | État réel | Ce qu'il manque |
|---|---|---|---|
| **Resend** | e-mails transactionnels | **non branché.** Le produit envoie par SMTP ; Resend n'apparaît que comme option de la décision **D5**, non tranchée. Expéditeur prévu : `no-reply@acx-connect.com` | la décision de JF, puis une clé et un domaine vérifié |
| **ClickUp** | suivi des lots hors du dépôt | **non branché côté produit.** Un connecteur ClickUp existe côté Claude (outils `clickup_*`) mais rien dans PokeBoyManager ne l'appelle, et le plan ne s'y synchronise pas — la source du suivi reste `docs/roadmap/roadmap.json` + `etat.json` | savoir ce que JF veut y voir : les lots ? les décisions ? et dans quel sens (miroir, ou source) |

### Outillage de développement — Graphify (installé le 22/09/2026)

**Ce n'est pas un service du produit** : l'API ne l'appelle jamais. C'est un outil pour *nous* —
il transforme le dépôt en graphe de connaissance interrogeable, pour qu'un agent trouve une
réponse sans relire vingt fichiers.

| | |
|---|---|
| Quoi | [`Graphify-Labs/graphify`](https://github.com/Graphify-Labs/graphify) — Apache-2.0, 120 k étoiles, actif |
| Paquet | **`graphifyy`** sur PyPI (le double `y` est le vrai nom ; `graphify` seul n'existe pas) |
| Installation | `uv tool install "graphifyy[mcp,sql]"` — les deux extras sont **nécessaires** : sans `[mcp]` le serveur refuse de démarrer, sans `[sql]` les 9 fichiers `infra/**/*.sql` ne sont pas indexés |
| Construction du graphe | `graphify update .` à la racine — **~25 s**, AST local, **aucun LLM, aucune clé, aucun coût** |
| Ce qu'il produit | `graphify-out/` (16 Mo, **ignoré par git** : il se reconstruit en 25 s et changerait à chaque commit) — au 22/09 : 5 381 nœuds, 13 614 arêtes, 267 communautés |
| Branchement | `.mcp.json` à la racine du dépôt, transport **stdio** (aucun port ouvert, aucune clé d'API) |
| Outils exposés | `query_graph`, `get_node`, `get_neighbors`, `get_community`, `god_nodes`, `graph_stats`, `shortest_path`, `list_prs`, `get_pr_impact`, `triage_prs` |

**Quand le rafraîchir** : après un gros changement de code ou de documentation — `graphify update .`
(ou `graphify watch .` pendant une session de développement). Un graphe périmé répond faux avec
aplomb : c'est son seul vrai défaut.

**Ce qui n'a délibérément PAS été fait** : `graphify install --platform claude`. Cette commande
écrit dans `~/.claude/`, pose des **hooks git** (`post-commit`, `post-checkout`) et un hook
`PreToolUse`. Ce poste fait déjà tourner **six hooks** pour le registre `liaison` et jusqu'à six
sessions Claude en parallèle : ajouter des hooks tiers qui s'exécutent à chaque commit et à chaque
appel d'outil est une décision de JF, pas d'un lot. Le serveur MCP donne déjà les dix outils sans
rien toucher au poste. **Vérifié après installation : `~/.claude/settings.json` est inchangé
(même empreinte SHA-256).**

**Ce qu'il reste à faire, et qui demande une session interactive** : Claude Code demande une
approbation avant d'utiliser un serveur MCP déclaré par un dépôt. JF doit donc l'approuver une
fois (`/mcp` dans une session interactive sur ce dépôt). Cette session-ci, non interactive, ne peut
pas le faire à sa place.

## Fournisseurs IA (lot `v3-ia-providers`)

Interface unique `AIProvider.extract(images, schema, prompt) -> (objet validé, usage)`
(`apps/api/src/pbm_api/ai/base.py`) — implémentations `AnthropicProvider`/`OpenAiProvider`/
`GeminiProvider` (`apps/api/src/pbm_api/ai/`), fabriquées par `pbm_api.ai.factory.
create_provider(provider, api_key)`. Sortie structurée native par fournisseur + validation
Pydantic (schéma traduit par `pbm_api.ai.json_schema`, `$ref` repliés) ; une nouvelle tentative
guidée si le JSON ne valide pas. Erreurs normalisées (`pbm_api.ai.errors` :
`InvalidApiKeyError`/`QuotaExceededError`/`ProviderOverloadedError`/`ProviderUnreachableError`/
`ContentRefusedError`), chacune avec un `user_message` prêt à consigner sur un `Job`. Détail :
`docs/ARCHITECTURE.md` § « Fournisseurs IA ». Tests sur réponses enregistrées
(`apps/api/tests/test_ai_providers.py`, `httpx.MockTransport`, aucune clé réelle sur chimera) ;
essai manuel avec une vraie clé : `uv run python scripts/test_ai_extraction_manual.py <provider>
<clé>` depuis `apps/api`.

## Insights par lots (lot `v4-insights-batch`)

Pré-génération, pour TOUTE carte du catalogue, de ce que `v4-anecdotes`/`v4-jeu` généraient
jusqu'ici à la demande (« autant tout prendre dès le premier tir », JF 19/09) — un seul appel
Anthropic par carte (Message Batches API, -50 %, `pbm_api.insights_batch.anthropic_batches`)
rend ensemble anecdotes sourcées FR + EN et étude en jeu (`pbm_api.insights_batch.
combined_generation.CombinedCardInsightExtraction`), écrit dans le même `card_insights` que les
routes à la demande — celles-ci deviennent un repli automatique pour une carte pas encore
couverte (leur logique de cache existante suffit, aucun changement côté `v4-anecdotes`/`v4-jeu`).
Anecdotes EN dans une colonne dédiée `card_insights.anecdotes_en` (même forme que `anecdotes`) :
mélanger les deux langues dans la liste déjà exposée par `GET /cards/{id}/insights` aurait fait
apparaître du texte anglais sans prévenir sur un produit francophone ; non exposée par une route
pour l'instant.

Orchestration (`pbm_api.insights_batch.runner.run_once`, appelé par
`scripts/run_insights_batch.py`, jamais depuis une route HTTP) : sélection idempotente (une
carte sans `CardInsight`, ou dont les anecdotes ou l'étude en jeu manquent encore, reste
candidate — jamais de re-dépense sur une fiche déjà utilisable), soumission d'un lot Anthropic
borné par `INSIGHTS_BATCH_CHUNK_SIZE` (défaut 100, très en-deçà de la limite réelle de 100 000
requêtes/256 Mo), sondage puis application idempotente des résultats. Clé **plateforme**
(`PLATFORM_ANTHROPIC_API_KEY`, jamais une clé d'`ai_credentials`) et budget cumulé
(`INSIGHTS_BUDGET_EUR`) lus depuis `pbm_api.config.Settings` — absents par défaut (dev),
`run_once` refuse alors de dépenser quoi que ce soit plutôt que de se replier silencieusement ;
D4 : à fournir par JF hors dépôt avant tout passage réel. Coût réel converti en EUR via
`pbm_api.pricing.exchange_rates` (même taux BCE que `v2-prix`) — un taux manquant bloque la
soumission (jamais un coût traité comme gratuit). Reprise : `var/insights_batch/ledger.json`
(non versionné) porte la dépense cumulée et le lot Anthropic en cours ; un script interrompu
entre soumission et récupération reprend ce même lot au lieu d'en resoumettre un second.

Tarifs (`pbm_api.insights_batch.pricing`, vérifiés le 20/09/2026 sur claude.com/pricing +
platform.claude.com/docs/en/build-with-claude/batch-processing, déjà remisés -50 % Batch) :
Haiku 4.5 (modèle par défaut du lot, le moins cher) 0,50 $/2,50 $ le Mtok entrée/sortie,
Sonnet 5 1 $/5 $. Mesure sur 100 cartes représentatives : `uv run python
scripts/measure_insights_batch_cost.py` (contexte wiki réel, `run_once(dry_run=True)` — aucun
appel Anthropic réel possible sur chimera, D4 ; coût ESTIMÉ par une heuristique
caractères/jeton documentée dans `pbm_api.insights_batch.runner`, jamais facturé) ; `--live`
relance ce même script pour la mesure réelle dès que la clé plateforme existera. User-Agent
identifié ajouté à `pbm_api.insights.context.MediaWikiClient` (risque « débit raisonnable » de
ce lot) — profite aussi à la collecte à la demande de `v4-anecdotes`, qui partage la classe.

Tests : `apps/api/tests/test_insights_batch_runner.py` (orchestration bout en bout, budget,
reprise, rejet d'anecdote hors contexte, idempotence — réponses enregistrées, aucune clé IA
réelle), `test_insights_batch_anthropic_client.py` (client Message Batches, réponses
enregistrées), `test_insights_batch_pricing.py`, `test_insights_batch_combined_generation.py`.
Pas de route HTTP dans ce lot (script/cron interne) : aucun test d'accès croisé utilisateur
propre à ajouter, `card_insights` reste le même cache partagé sans notion de propriétaire déjà
couvert par les tests de `v4-anecdotes`/`v4-jeu`.
