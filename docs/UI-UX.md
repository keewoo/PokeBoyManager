# UI / UX — la maquette, le design system, les écrans

> **À lire avant de toucher à `apps/web`.** Ce qui se voit : identité, jetons de style,
> composants, comportement des écrans livrés.
> Ce qui n'est pas ici : les règles de code (`docs/CODE.md`), ce que fait l'API
> (`docs/ARCHITECTURE.md`), le plateau de jeu (`docs/roadmap/jeu/BACKLOG-JEU.md`).
> Tous les chemins sont donnés **depuis la racine du dépôt**.

## Deux références, et laquelle l'emporte

| Référence | Ce qu'elle fixe | Statut |
|---|---|---|
| **Charte PokéBoy** — https://claude.ai/artifact/M2GyeGw6T6FeW5anfq1op8 | l'identité visuelle cible (couleurs, polices, effets, icônes, personnages) et 13 écrans dessinés | **fait foi pour tout écran nouveau ou repris**, depuis le 22/09/2026 |
| Maquette d'origine — onglet « Maquette du site » de `docs/roadmap/ROADMAP.html` (https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy) | la structure et le contenu des écrans livrés en V1–V4 | reste la référence **de structure** tant qu'un écran n'a pas été repris à la charte |

Un écart assumé se dit dans le compte rendu du lot ; un écart non dit est un défaut.

> ⚠️ **La charte n'est pas encore dans le code.** `globals.css` porte toujours les jetons d'origine
> (fond clair/sombre neutre, primaire `#d93a1e`) et `layout.tsx` les polices d'origine. Seules la
> marque (favicon, icône web, icône Apple, image Open Graph, `themeColor` `#050A30`) et les
> bibliothèques de visuels sont en ligne. **Reprendre les jetons est un lot à part entière** : ne
> pas le faire au passage d'un autre lot, sous peine de repeindre la moitié du produit sans que
> personne l'ait demandé.

### Ce que l'identité emprunte, et ce qu'elle n'emprunte pas

Aucun logo officiel Pokémon, aucune charte Nintendo / The Pokémon Company reconstituée : le
logotype, l'icône d'application et la Master Ball du produit sont des créations propres. Les cartes
affichées viennent du catalogue (image officielle de la carte) ou de la photo de l'utilisateur —
jamais d'un habillage de marque reconstitué.

**Une exception, à arbitrer par JF** : les neuf personnages de `apps/web/public/personnages/`,
fournis le 22/09/2026, représentent des créatures Pokémon. La mention « non affilié » (D8) couvre
le produit, pas l'usage de personnages en marque propre. Tant que ce n'est pas tranché, ils
restent **réservés aux maquettes internes** — ne pas les servir sur une page publique.

## Charte PokéBoy — couleurs, polices, relief

| Jeton | Valeur | Emploi | Ce qui se paie si on l'oublie |
|---|---|---|---|
| Fond | `#050A30` | toutes les surfaces, en dégradé vers `#03061C` | aucune surface ne s'en éloigne de plus de deux tons |
| Violet Master Ball | `#9D00FF` | halos, liserés, état actif | **jamais du texte** : 2,8:1 sur le fond. Un titre de section prend `#C77DFF` (6,2:1) |
| Or collectionneur | `#FFD700` | titres H1, appels à l'action, étincelles | 14,6:1 — sûr partout |
| Rose fuchsia | `#FF1493` | cadres de carte, surbrillance | par touches, et à 24 px minimum (4,0:1 seulement) |
| Texte | `#E0E0E0` | corps de texte | le secondaire descend à `#9BA3C7`, pas plus bas |

Polices : **Press Start 2P** (H1 uniquement, capitales, 20–32 px, ombre portée dorée — illisible
au-delà de trois mots), **Exo 2** (titres de section, onglets, étiquettes, chiffres), **Roboto**
(corps de texte, 15–17 px, interligne 1,7).

Le relief, c'est ce qui distingue la charte d'un aplat — on ne le retire pas sans raison :
liseré or de 3 px et reflet holographique en diagonale sur **toute** vignette de carte ; légère
rotation des cartes ; **pilule (rayon 999 px) pour tout ce qui se clique**, 22–26 px pour les
surfaces, avec un filet clair en haut (la lumière vient d'en haut, toujours) ; un seul halo par
surface, allumé au survol uniquement sur ce qui est cliquable ; étincelles dorées à quatre
branches, parcimonieuses.

## Icônes et personnages

| | Où | Règle d'emploi |
|---|---|---|
| 12 icônes, 256 px | `apps/web/public/icons/ui/` | 28 px en navigation, 40 px sur une carte, 64 px sur un titre, 96 px sur un état vide. **En dessous de 28 px, un tracé SVG** : le détail se perd |
| 9 personnages, 512 px | `apps/web/public/personnages/` | une **présence**, jamais un décor : état vide, réussite à fêter, attente longue. **Un seul par écran** |
| Logotype | `apps/web/public/brand/pokeboy-logotype.png` | fond **transparent**. Ne jamais réintroduire une version sur fond plein : posée sur un dégradé, elle se voit comme un rectangle collé |

### Icône et logotype ne cohabitent pas

Ce sont **deux marques**, pas une marque et son accessoire : le logotype porte déjà son symbole
(le classeur et la Master Ball), son nom et sa signature. Posés côte à côte dans un même en-tête,
ils se concurrencent et le bandeau devient une planche de logos.

- En-tête de page, écran de connexion, pied de page de marque → **le logotype seul**.
- Barre d'application, onglet du navigateur, écran d'accueil du téléphone, avatar → **l'icône
  seule**, sans le mot « PokéBoy » à côté si le logotype est déjà visible ailleurs sur l'écran.

Le halo n'est **pas** dans les fichiers : il est posé en CSS (`filter: drop-shadow`), ce qui le rend
teintable écran par écran et cohérent d'un écran à l'autre. Correspondance icône → emploi et règle
des personnages : `apps/web/public/VISUELS.md`.

Les icônes de l'application elle-même (`apps/web/src/app/favicon.ico`, `icon.png`, `apple-icon.png`,
`opengraph-image.jpg`) sont des **conventions de fichiers Next.js** : détectées à la construction,
aucune balise à écrire. Les redéclarer dans `metadata.icons` produirait des balises concurrentes.

## Design system

| | Où |
|---|---|
| Jetons de couleur, rayons, ombres | `apps/web/src/app/globals.css` (variables CSS `--background`, `--primary`, `--gold`, `--success`…, déclinées en clair et en sombre) |
| Polices **en place** | `apps/web/src/app/layout.tsx` — Instrument Sans (texte), Bricolage Grotesque (titres), JetBrains Mono (chiffres et identifiants), Press Start 2P (logo seulement). **Cible de la charte** : Press Start 2P / Exo 2 / Roboto — pas encore appliquée |
| Composants de base | `apps/web/src/components/ui/` — `button`, `input`, `label`, `badge`, `checkbox` |
| Composants produit | `apps/web/src/components/` — `app-shell`, `card-tile`, `condition-badge`, `empty-state`, `legal-footer`, et les dossiers `auth/`, `dashboard/`, `landing/`, `profile/` |
| Galerie de référence | `/design` (`apps/web/src/app/design/page.tsx`) — la page qui montre les composants tels qu'ils sont vraiment |

**Règles de tenue :** une couleur nouvelle se déclare en jeton dans `globals.css`, jamais en dur
dans un composant ; un composant qui sert deux fois monte dans `components/` ; aucune information
ne repose sur la seule couleur (daltonisme) ; le mode sombre se vérifie à chaque écran.

## Carte sans image officielle (lot `pbm-carte-remplacement`)

3 827 cartes du catalogue n'ont aucune image officielle. Deux composants s'enchaînent :

- **`CardImage`** (`apps/web/src/components/card-image.tsx`) — le SEUL point qui décide quoi afficher.
  Image officielle si elle existe ET se charge ; sinon repli. Quand le proxy avait une URL et
  échoue (`onError`), il **journalise l'incident** (`console.warn`) avant de basculer : un repli là
  où une image officielle existe est une panne, jamais un cas normal (règle « pas de repli
  silencieux »). Un simple cadre à `label` reste pour les cas sans données de carte (photo
  personnelle absente, accueil visiteur).
- **`ReplacementCard`** (`apps/web/src/components/replacement-card.tsx`) — la carte **composée** à
  partir des vraies données : cadre doré, bandeau nom + PV en haut (teinté par le type, sous un
  voile sombre pour que le texte clair reste lisible), fond générique en plein cadre, mention
  **« visuel non disponible »** en bas de l'illustration, extension · numéro et rareté en pied. Pour
  un Dresseur/une Énergie (pas de PV, pas de type) : la **catégorie** remplace les PV, fond
  `colorless`. Le texte se mesure en `cqw` (`@container`) : lisible en vignette comme en grand.

**Fonds** : 99 fichiers `apps/web/public/fonds/<type>-01.webp`…`-09.webp` (11 types × 9), servis avec
un cache immuable d'un an (`next.config.ts`, `headers()`). Le fond d'une carte est **déterministe** :
`empreinte(card_id) % 9` sur son type (`apps/web/src/lib/replacement-card.ts`) — la même carte garde
toujours le même visuel. Couleurs des types : jetons `--type-<code>` dans `globals.css` (teinte
seulement, jamais un texte). Trois usages : vignette de collection, fiche carte, et repli du proxy.

## Les écrans

| Route | Écran | Lot |
|---|---|---|
| `/` | accueil visiteur | `v1-accueil` |
| `/inscription`, `/connexion`, `/mot-de-passe-oublie`, `/verifier`, `/reinitialiser`, `/confirmer-email` | comptes | `v1-pages-auth` |
| `/profil` | profil, clés IA, identité | `v1-profil`, `v1-identite` |
| `/ajouter`, `/ajouter/validation` | envoi de photos puis validation des cartes reconnues | `v3-upload`, `v3-validation` |
| `/collection` | grille, filtres, tris, valeur totale | `v4-collection` |
| `/carte/[id]` | fiche carte | `v4-fiche` |
| `/` (connecté) | tableau de bord | `v4-dashboard` |
| `/conditions`, `/confidentialite`, `/mentions-legales` | pages légales | `v5-securite`, `v5-rgpd` |

Les chemins `/verifier?token=…` et `/reinitialiser?token=…` doivent rester **alignés avec les liens
envoyés par e-mail** (`pbm_api.auth.service.register_user` / `request_password_reset`) : les changer
d'un côté casse le parcours de l'autre. e2e Playwright du parcours inscription → vérification → connexion :
`apps/web/e2e/auth.spec.ts` (`pnpm --filter @pbm/web test:e2e`, **nécessite Mailpit** ;
navigateurs déjà en cache sur chimera).

## Accessibilité et confort — le socle attendu

Le produit est utilisé par un enfant de onze ans et par ses parents. À chaque écran : contraste
suffisant, cibles tactiles confortables, navigation clavier complète, `prefers-reduced-motion`
respecté, textes lisibles sans jargon. Un écran qui ne se navigue qu'à la souris n'est pas fini.

## Écran de validation (lot `v3-validation`)

Routes (`apps/api/src/pbm_api/routers/uploads.py`, `routers/detections.py`) : `GET
/uploads/{id}` (état de l'envoi + job de reconnaissance le plus récent + détections — chargement
initial de l'écran), `GET /uploads/{id}/events` (flux SSE, `event: snapshot` à chaque changement
détecté par sondage puis `event: done`/`timeout` en fin de job), `POST
/detections/{id}/confirm`/`/reject`, `POST /uploads/{id}/confirm-all`. `Upload.status` ne reflète
que le traitement de la photo brute (EXIF, HEIC), pas la reconnaissance : la progression réelle
vient du `Job` (`type="detect_cards"`) le plus récent pour cet envoi
(`pbm_api.uploads.service.get_latest_recognition_job`). `pbm_api.detection.service` et
`pbm_api.identification.service` commitent désormais une détection à la fois (pas un seul commit
en fin de job) pour que le flux SSE voie une progression réelle et qu'un job interrompu (clé
épuisée) garde les cartes déjà traitées.

`confirm` crée `quantity` `CollectionItem` (une ligne par exemplaire, `CollectionItem` n'a pas de
colonne quantité) et écrit une `IdentificationCorrection` (`pbm_api.models.identification`) :
candidat proposé (premier de `Detection.candidates`, `None` si aucun) contre celui réellement
retenu (`None` = rejetée) — le jeu de régression de l'identification, jamais consulté par le
produit lui-même. `confirm-all` (« Tout ajouter ») n'agit que sur les détections dont le premier
candidat est présélectionné (`preselected`, score > `PRESELECTION_THRESHOLD` — voir
`pbm_api.identification.reconciliation`), langue "fr"/variante normale/un exemplaire par défaut ;
le reste reste `pending`, jamais ajouté sans qu'un candidat se soit démarqué même implicitement.

Front (`apps/web/src/app/ajouter/validation/`) : un envoi peut regrouper plusieurs photos (donc
plusieurs `upload_id`, l'API n'ayant pas de notion de lot) — `upload-view.tsx` redirige vers
`/ajouter/validation?uploads=<id1>,<id2>,…` après l'envoi, la liste des détections de tous les
envois est fusionnée côté client et triée par ordre de lecture. Raccourcis clavier (mission point
2) : Entrée valide la détection active (premier `pending` de la liste), 1/2/3 changent son
candidat sélectionné — désactivés quand le focus est dans un champ de saisie. Recherche manuelle :
réutilise `GET /catalog/search` tel quel (`pbm_api.routers.catalog`, lot `v2-recherche`).

Rebasé sur `v3-etat`/`v1-identite` (fusionnés dans `origin/main` pendant cette session) :
`Detection.condition_assessment` (état estimé + contrefaçon, un seul appel IA partagé avec
l'identification) existe désormais — la carte de validation affiche l'état estimé et un badge
« contrefaçon probable » quand il est présent, pré-remplit (sans l'imposer) le champ « État »
manuel. `confirm`/`confirm-all` reprennent le drapeau `counterfeit_suspected` de la détection sur
le `CollectionItem` créé (`pbm_api.validation.service._counterfeit_suspected`) — sans ça, une
contrefaçon probable aurait été valorisée comme l'originale
(`pbm_api.pricing.valuation.item_value`).

Étendu par `v3-identification-visuelle` : `detection-card.tsx` affiche un badge « reconnue sans
IA » quand `Detection.identification_method === "visuel"` (comparaison à l'index visuel des
images officielles, aucun appel IA) — même emplacement que les badges statut/contrefaçon
existants, aucun autre changement d'écran.

Tests : `apps/api/tests/test_validation_routes.py` (confirm/reject/confirm-all, flux SSE, accès
croisé) — le worker arq n'étant pas démarré pendant les tests, `_simulate_worker` reproduit
`worker._run_detect_cards` (détection puis identification directement, `Job.status` transité à la
main). e2e Playwright de conformité à la maquette :
`apps/web/e2e/validation.spec.ts` — aucune clé IA réelle disponible sur chimera, l'envoi
« déjà identifié » est semé directement en base par `apps/api/scripts/seed_validation_e2e.py`
(même forme que `_simulate_worker`) ; seul l'écran de validation est exercé par le navigateur, pas
le pipeline de reconnaissance réel.

## Page collection (lot `v4-collection`)

`GET /me/collection` (`pbm_api.collection.service.list_collection`) : filtres extension
(`set_id`)/série/rareté/type/langue/variante/état/valeur min-max/date d'ajout (`acquired_from`/
`acquired_to`)/doublons/contrefaçons, tri (`sort`, valeur/variation 30 j/date d'ajout/numéro/nom),
pagination par curseur (`cursor`, opaque — id du dernier exemplaire de la page), agrégats (nombre,
valeur totale, variation 7/30 j). `GET /me/collection/facets` (valeurs de filtre, scopées à
l'utilisateur — jamais le catalogue entier). `POST /me/collection` (ajout manuel, `card_id` +
quantité, réutilise `GET /catalog/search`, aucun `Detection`/`photo_s3_key`). `PATCH`/`DELETE
/me/collection/{item_id}` (`PATCH` partiel : seuls les champs envoyés changent).

Valeur calculée à la demande pour chaque exemplaire (comme `pricing.valuation.item_value`),
jamais stockée : `list_collection` charge en une requête le sous-ensemble filtré par les critères
« bon marché » (catalogue, langue, variante, état, dates, colonnes explicites — jamais les
entités ORM `Card`/`Set` complètes, coûteuses à 5 000 lignes à cause de leurs colonnes JSONB),
valorise ce sous-ensemble par lots (`pricing.valuation.bulk_item_values_multi` — une requête de
prix `UNION ALL`/`DISTINCT ON` pour les 3 dates de référence à la fois, aujourd'hui/-7 j/-30 j,
jamais une requête par exemplaire ni par fenêtre), puis applique le filtre de valeur, le tri et
la pagination en mémoire (mission point 4 : 5 000 exemplaires en moins de 300 ms — mesuré,
`scripts/measure_collection_performance.py`). `collection_value` (`v4-ranking`) réutilise
désormais ce même chemin (corrige le N+1 qu'il portait depuis `v2-prix`).

Doublon = même `card_id` (toutes langues/variantes confondues) présent au moins deux fois dans
la collection entière de l'utilisateur, jamais recalculé sur un sous-ensemble filtré. `value_eur`
neutralisée à `0` pour un exemplaire signalé contrefaçon probable, `value_change_30d_pct` calculé
serveur (`None` si la référence 30 j est inconnue ou nulle) pour rejoindre le composant partagé
`apps/web/src/components/value-delta.tsx` (seule forme montrée par la maquette).
`rarity-badge.tsx`/`condition-badge.tsx` (même composant partagé) ne sont **pas** réutilisés ici :
leurs taxonomies fixes ne correspondent ni aux libellés bruts du catalogue TCGdex
(`Card.rarity`) ni au barème `pricing.valuation.CONDITION_MULTIPLIERS` — les forcer aurait
affiché des libellés inexacts (voir `docs/roadmap/comptes-rendus/v4-collection.md`).

Front `apps/web/src/app/collection/` : panneau de filtres (tiroir sur mobile), recherche + tri,
état entièrement dans l'URL (partageable, retour arrière du navigateur fonctionnel), pagination
« Charger plus » (curseur en état de composant, pas dans l'URL). Tests :
`apps/api/tests/test_collection_routes.py` (accès croisé compris),
`apps/web/src/__tests__/collection-view.test.tsx`.

## Accueil connecté (lot `v4-dashboard`)

`apps/web/src/app/page.tsx` (Server Component) lit le cookie de session (`cookies()`, jamais un
état client après montage — évite un flash de l'accueil visiteur) et bascule vers `HomeContent`
(`apps/web/src/app/home-content.tsx`, isolé du Server Component pour rester testable hors
runtime Next.js) : `DashboardView` avec session, `LandingPage`
(`apps/web/src/components/landing/`, extraite sans changement de l'ancien contenu de `page.tsx`)
sinon. `GET /me/dashboard` (`pbm_api.dashboard.service.get_dashboard`, appelé par
`routers/dashboard.py`) réutilise tel quel `pricing.valuation.bulk_item_values_multi`
(`v4-collection`) : une seule valorisation en masse couvre à la fois la valeur du jour, les
points de la courbe et la référence 30 jours — jamais une requête de prix par exemplaire ni par
date. Courbe sur 90 jours avec un point tous les 7 jours (`HISTORY_POINT_INTERVAL_DAYS`) plutôt
qu'un par jour : `bulk_item_values_multi` fait un `UNION ALL` d'une sous-requête par date
demandée, 90 dates multiplieraient le coût par 90 pour un agrément visuel qu'une dizaine de
points suffit à donner (job lourd = job bridé, `~/.claude/CLAUDE.md`). Plus fortes variations
triées par montant absolu (mouvements à variation nulle exclus) ; cinq derniers ajouts par
`created_at`.

`apps/web/src/components/dashboard/total-value-delta.tsx` (montant en euros signé, ▲/▼/=) est
**distinct** de `value-delta.tsx` (`v4-collection`, pourcentage) : l'agrégat de tête de la
maquette (« ▲ +42,50 € sur 30 j ») n'est pas la même donnée, pas le même composant à réutiliser
tel quel. Courbe : `value-chart.tsx` (Recharts `LineChart`/`ResponsiveContainer`, ajouté à
`package.json` — déjà dans la stack cible de `docs/roadmap/ROADMAP.html`) ; rien affiché en
dessous de 2 points (le montant du dessus porte déjà l'information, un graphe à un seul point
serait trompeur). `vitest.setup.ts` polyfill `ResizeObserver` (absent de jsdom,
`ResponsiveContainer` en a besoin). Tests : `apps/api/tests/test_dashboard_routes.py` (accès
croisé compris), `apps/web/src/__tests__/dashboard-view.test.tsx`,
`apps/web/src/__tests__/home-content.test.tsx`. Détail, capture de conformité maquette et écarts
connus (en-tête `AppShell` non sensible à la session, images de carte bloquées par ORB — tous
deux préexistants, hors périmètre de ce lot) :
`docs/roadmap/comptes-rendus/v4-dashboard.md`.

## Fiche carte (lot `v4-fiche`)

Routes (`apps/api/src/pbm_api/routers/cards.py`, module `pbm_api.cards`) : `GET /cards/{id}`
(catalogue + prix EUR par variante + classement + résumé du meilleur exemplaire possédé — voir
plus bas), `GET /cards/{id}/price-history?variant=&range=7|30|365|all` (courbe de valeur,
`pbm_api.pricing.valuation.price_history_eur` — un point par jour où au moins une source a un
relevé exploitable, jamais interpolé : risque documenté du lot, un historique court en début de
vie s'affiche tel quel), `GET /cards/{id}/my-items` (tous les exemplaires possédés par
l'utilisateur courant, onglet « Mes exemplaires » — jamais le `GET /me/collection/{item}` déjà
existant, mission initiale : une fiche montre systématiquement *tous* les exemplaires, pas un
seul connu d'avance). `GET /me/collection/{item}/photo` (`routers/collection.py`), ajoutée par ce
lot pour la bascule « Ma photo » de l'en-tête : sert la photo brute de l'exemplaire
(`CollectionItem.photo_s3_key`), 404 explicite si l'exemplaire n'a pas de photo (ajout manuel) ou
si l'objet a disparu du stockage — jamais un succès vide. Les onglets Histoire/En jeu ne passent
par aucune route de ce lot : ils réutilisent tels quels `GET /cards/{id}/insights` et
`GET /cards/{id}/in-game-study` (missions `v4-anecdotes`/`v4-jeu`, déjà en génération à la demande
si absente) — **premiers écrans à les consommer**.

`MyCardItemOut.purchase_price_eur` : prix d'achat converti au taux du jour d'**acquisition**
(`pbm_api.pricing.exchange_rates.get_rate_to_eur`, jamais celui du jour de lecture — ce qui a été
payé ne change pas rétroactivement), `None` sans prix d'achat ou si ce taux n'a jamais été
relevé. Sert la plus-value de l'en-tête (`value_eur - purchase_price_eur`) sans second aller-
retour serveur. Bug trouvé en écrivant ce champ : `Decimal.__truediv__` d'une conversion de
change dont le quotient est « rond » (ex. 40 USD à 2 USD/EUR) renvoie un `Decimal` en notation
scientifique (`2E+1`) que Pydantic sérialise tel quel — `.quantize(Decimal("0.000001"))` après
toute conversion de devise, appliqué ici et dans `price_history_eur` (les deux fonctions de ce
lot ; les usages plus anciens de `convert_to_eur` dans `pricing/valuation.py`, testés à l'égalité
exacte par `test_valuation.py`, n'ont pas été touchés — hors périmètre, risque de régression pour
un autre lot).

En-tête de fiche et « État »/« Ajoutée le »/« Prix d'achat »/« Plus-value » : dérivés côté front
(`apps/web/src/app/carte/[id]/card-detail-view.tsx`, `pickPrimaryItem`) du **meilleur** exemplaire
possédé (valeur la plus forte, `MyCardItemOut[]` déjà chargé pour l'onglet « Mes exemplaires »),
même choix que `CardDetailResponse.collection_rank` côté API (`pbm_api.cards.service.
_best_owned_item`) — jamais un second calcul qui pourrait diverger. `CardRankingOut.
value_percentile` est un `PERCENT_RANK()` **0 → 1, 1 = le plus cher** (`pbm_api.ranking.service`,
vue matérialisée `card_value_rank`) : le badge « top X % de l'extension » calcule
`(1 - value_percentile) * 100`, jamais `100 - value_percentile` (confondre les deux échelles
aurait affiché un pourcentage dix fois trop petit).

Page `apps/web/src/app/carte/[id]/` : onglet actif en état local (`useState`, pas dérivé de
`useSearchParams` à chaque rendu comme `/collection`) — changer d'onglet ne redemande rien au
serveur, la bascule doit être instantanée ; l'URL (`?onglet=`) n'est mise à jour qu'ensuite, pour
le partage et le retour arrière. Cinq onglets (Valeur, **État**, Histoire, En jeu, Mes
exemplaires) : la maquette (`ROADMAP.html`, `V.fiche`) en montre cinq alors que la mission n'en
listait que quatre (l'État en moins) — la maquette prime (`CLAUDE.md` racine : « le front
reproduit la maquette »), d'autant que le contenu de cet onglet existe déjà entièrement
(`v3-etat`). Courbe de valeur : Recharts (`value-chart.tsx`, propre à ce lot — homonyme sans
rapport avec celui de `v4-dashboard`), ligne de référence en pointillés pour le prix d'achat,
palette et specs de marque suivant la référence dataviz du poste (un seul hue pour la série, pas
de légende à une série, grille recessive) ; partage avec `v4-dashboard` le mock `ResizeObserver`
de `vitest.setup.ts` (absent de jsdom, requis par `ResponsiveContainer`, les deux lots l'ayant
ajouté indépendamment en parallèle).

Tests : `apps/api/tests/test_card_detail_routes.py` (accès croisé sur les trois routes + la
photo, conversion de devise), `apps/web/src/__tests__/card-detail-view.test.tsx`. e2e Playwright
de conformité à la maquette (captures jointes au compte rendu du lot) :
`apps/web/e2e/card-detail.spec.ts` — aucune clé IA réelle disponible sur chimera, une carte
possédée avec historique de prix, état estimé, anecdotes et étude en jeu déjà en cache est semée
directement en base par `apps/api/scripts/seed_card_fiche_e2e.py` (même forme que
`seed_validation_e2e.py`) ; connexion par appels API directs (`page.request`, cookies partagés
avec `page`) plutôt qu'en remplissant le formulaire d'inscription à l'écran — la case CGU de ce
formulaire s'est révélée instable à cliquer dans l'environnement Playwright de ce poste
(`auth.spec.ts` échoue au même endroit, non lié à ce lot) ; seule la fiche elle-même reste
exercée par le navigateur.
