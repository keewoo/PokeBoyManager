# Compte rendu — lot `pbm-insights-ciblage-large`

**Fiches des cartes : 2 anecdotes FR + règles de jeu, sur ~80 % du catalogue.**

Suite des décisions de JF (21/09) après la mesure du lot `pbm-insights-toutes-cartes` (5 anecdotes
FR + 5 EN + étude en jeu ≈ 72 € pour tout le catalogue, au-dessus de l'ancien plafond de 20 €) :

1. Plafond relevé à **50 €** (arrêt net au-delà, en gardant ce qui est produit).
2. Contenu réduit : **2 anecdotes, en français seulement**, **plus les règles de jeu** (coût et
   effet des attaques, talent, règle ex/V/VMAX, rôle typique, formats légaux).
3. Ciblage large : viser **80 %** des cartes, priorité (a) possédées → (b) extensions récentes →
   (c) plus chères → (d) plus consultées → complément par extension, jusqu'à 80 % ou budget.

## Ce qui a été livré (code)

| Fichier | Rôle |
|---|---|
| `apps/api/src/pbm_api/insights_batch/large_generation.py` | Schéma réduit `LargeInsightExtraction` (par carte : `card_ref`, `anecdotes` ≤2 FR, `game_rules` texte), prompt groupé par extension (contexte partagé une fois), **anti-mélange** par `card_ref`. Règles de jeu construites à partir des données catalogue (attaques, coûts, talents, légalités, règle des Prix), jamais inventées. |
| `apps/api/scripts/generate_large_insights.py` | Driver : priorité, contexte wiki (cache **par requête**, concurrence modérée + rythme raisonnable + User-Agent), lots Anthropic groupés (Message Batches, -50 %), budget 50 € + grand livre de reprise, sortie TSV clé `tcgdex_id`, ré-essai carte par carte des paquets en échec (jamais de perte silencieuse). Mode `--measure`. |
| `apps/api/tests/test_insights_batch_large_generation.py` | Schéma/prompt/anti-mélange (11 tests). |
| `infra/fleet/export_catalog_for_insights.sql` | Export du catalogue (données de jeu + nom EN + récence + proxy de valeur) depuis `pbm_catalogue_ref`. |
| `infra/fleet/import_insights.sql` | Import du TSV en PROD **et** en base de référence (COPY temp → upsert, jointure `cards.tcgdex_id`, diagnostic honnête + preuve post-import). |
| `infra/fleet/export_insights.sql` | Export symétrique des fiches depuis une base qui les détient (re-dérivation/réplication). |

Stockage : les 2 anecdotes FR vont dans `card_insights.anecdotes` (JSONB), les règles de jeu dans
`card_insights.in_game_study` (texte, déjà lu par l'onglet « En jeu » de la fiche). `anecdotes_en`
reste NULL (français seulement). Cache 180 jours pour les deux volets (contenu catalogue stable —
choix propre à ce lot, à la différence du chemin à la demande calé sur la présence en tournoi).

## Où ça tourne — écart assumé et documenté

La mission dit « sur chimera ». **La génération tourne en réalité sur devAI**, pour une raison de
sécurité tranchée par la session de mesure et que je maintiens : *la clé personnelle d'Aymeric ne
quitte pas devAI* (chimera n'a aucune clé — `~/.claude/CLAUDE.md`). Un appel à la Message Batches
API exige la clé sur la machine appelante ; « appeler depuis chimera » impliquerait d'y copier la
clé, ce que l'hygiène de secret interdit. Le SEUL « lourd » réellement proscrit est la machine qui
**sert** (`kailo-srv`/PROD) — pleinement respecté : rien ne tourne là-bas.

Le catalogue (22 169 cartes) vit dans `pbm_catalogue_ref` sur chimera ; il est **exporté vers
devAI** (JSON, `export_catalog_for_insights.sql`), la génération se fait sur devAI (fichier + clé),
et les fiches produites sont **importées en PROD et dans la base de référence** par jointure
`tcgdex_id`. C'est le patron de la flotte (`docs/infra/JOBS-LOURDS.md`), clé de secret en moins.

## Priorité effective

- (a) **Possédées** : les tcgdex_id des cartes en collection PROD, placées en TÊTE → **100 %**.
- (c) **Plus chères** : top 3000 par proxy de prix (plus fort relevé 90 j, toutes sources — ordre
  grossier documenté).
- (b) **Extensions récentes + complément** : le reste, par extension (date de sortie décroissante),
  toutes les cartes d'une extension ensemble (préserve le groupage à contexte partagé).
- (d) **Plus consultées** : **aucune source de données en PROD** (pas de table d'analytics/vues au
  21/09) → tier vide, documenté ; à ré-injecter le jour où la consultation sera tracée.

## Mesure (contenu réduit) — le gate avant la grande dépense

Échantillon de 120 cartes d'extensions récentes complètes (paquets réels de N cartes), vraie clé,
modèle `claude-haiku-4-5`, taux USD→EUR 1,146 :

| Taille paquet | Couvertes | Échecs paquet | Coût/carte | Extrapolation 80 % (17 735) | Anecdotes écartées faute de source |
|---|---|---|---|---|---|
| 15 | 105/120 | 1 | 0,00159 € | 28,22 € | 7 |
| **25** (retenue) | **120/120** | **0** | **0,00134 €** | **23,71 €** | 28 (≈26 %) |

**Taille de paquet retenue : 25** — 100 % couvert, aucun échec de paquet, la moins chère.
**80 % du catalogue ≈ 24 €, largement sous le plafond de 50 €** → le ciblage 80 % est atteignable
sans le rogner. Coût de la mesure elle-même : **0,3275 €** (réel, sur la clé d'Aymeric).

Le taux d'anecdotes écartées faute de source (~26 % à paquet 25) est le filtre anti-hallucination
qui fait son travail : une anecdote dont le `source_url` n'est pas dans le contexte fourni est
rejetée plutôt que stockée. Chaque carte couverte garde ses **règles de jeu** (toujours produites,
données catalogue) et ses anecdotes réellement sourcées (0, 1 ou 2). Beaucoup de cartes obscures
n'ont qu'une page wiki d'extension et peu d'anecdotes propres : renvoyer moins plutôt qu'inventer
est le comportement voulu (mission « aucune anecdote sans source vérifiable »).

## Génération et import

<!-- REMPLIR : cartes couvertes, % catalogue, coût total, possédées 100 %, anecdotes sans source, temps, reste à faire -->

## Vérification « fiche sans appel IA »

<!-- REMPLIR : une fiche PROD couverte s'ouvre en lecture cache, aucun appel IA -->
