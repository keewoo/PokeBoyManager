# Compte rendu — lot `pbm-carte-remplacement`

Session autonome sur **devAI**, 2026-09-22. Afficher une carte **même sans image officielle** :
composer la carte à partir de ses vraies données au lieu d'un cadre vide.

## Verdict

**FAIT.** Livré en PROD (`pokeboy.lol`), release `20260922-203454`, commit `69cf775`. CI GitHub
**verte** sur `main` (web + api + e2e). Sites voisins (`kailo.life`, `acx-connect.com`, UAT) non
affectés, mesurés avant/après.

## Ce qui a été fait

- **`ReplacementCard`** (`apps/web/src/components/replacement-card.tsx`) : carte composée — cadre
  doré (référence validée par JF), bandeau nom + PV teinté par le type, fond générique en plein
  cadre, mention **« visuel non disponible »** permanente, extension · numéro + rareté en pied.
  Dresseur/Énergie : la catégorie remplace les PV, fond `colorless`. Texte en `cqw` (`@container`)
  pour rester lisible en vignette comme en grand format.
- **Fond déterministe** : `empreinte(card_id) % 9` sur le type (`lib/replacement-card.ts`, FNV-1a) —
  la même carte garde toujours le même visuel. 99 fonds `public/fonds/`, cache immuable d'un an
  (`next.config.ts`). Jetons `--type-<code>` dans `globals.css` (teinte seulement, jamais un texte).
- **`CardImage`** reste le seul point de décision : compose `ReplacementCard` quand les données de
  la carte sont là, sinon un cadre sobre. `onError` du proxy **journalise** l'incident
  (`console.warn`) avant de basculer — un repli là où une image existe est une panne, pas un cas
  normal. Trois usages : vignette de collection, fiche, repli du proxy.
- **Serveur** : colonne `Card.element_type` (type élémentaire normalisé au code du jeu, depuis
  TCGdex `types`, `catalog/element_type.py`), captée à l'import, exposée par `GET /cards/{id}` et
  `GET /me/collection` (+ `hp`). Migration additive nullable `c3a7e1f4d820`. Détail :
  `docs/ARCHITECTURE.md`, `docs/UI-UX.md`.

## Déploiement (chimera → devAI → kailo-srv)

- **Construit sur chimera** (WSL, node 24.21 / pnpm 12.4.2 / uv), `NEXT_PUBLIC_API_URL=https://pokeboy.lol/api`
  figé au build. Artefacts `web-20260922-203454.tgz` (25 Mo) + `api-…tgz`, sha256 vérifié à chaque
  saut chimera→devAI→serveur.
- Release `/srv/pokeboy/prod/releases/20260922-203454/`, `uv sync --frozen`, **`alembic upgrade head`**
  (`23a3f88da88d → c3a7e1f4d820`, colonne `element_type` ajoutée), bascule du symlink `app/`,
  `systemctl restart pokeboy-prod-{api,worker,web}` — les trois **actifs**, journaux propres.
- **Preuve d'exécution** (pas une ligne de journal) : le schéma OpenAPI **servi** par `pokeboy.lol/api`
  expose `element_type` et `hp` sur `CardDetailResponse` et `CollectionListItem`.

## Backfill `element_type` (2026-09-22)

`apps/api/scripts/backfill_element_type.py` lancé contre la base de PROD (Pokémon sans image dont
`element_type IS NULL`, type récupéré chez TCGdex) : **3 987 cartes sans image, 3 407 typées**,
7 sans type TCGdex, **0 erreur**, en 14 s. Les 580 restantes (Dresseurs/Énergies + 7 Pokémon sans
type) prennent le fond `colorless`, comme prévu. Additif et idempotent ; l'import hebdo étant
insert-only, il n'est pas écrasé (voir la dette flotte dans `docs/ARCHITECTURE.md`).

## Captures (proof visuelle)

`~/dev/logs/pbm-carte-remplacement-captures/` sur devAI :
- `collection.png` — 7 cartes composées, fonds **variés par type** (Feu, Eau, Plante, Psy,
  Électrique, Combat) + un Dresseur en `colorless` ; chacune porte « VISUEL NON DISPONIBLE ».
- `fiche.png` — carte « Aflamanoir » (Feu) en grand format, avec la mention
  « Aucune image officielle pour cette carte : visuel composé à partir de ses données ».

Comptes de campagne créés/supprimés proprement (`admin create-user` puis suppression : `DELETED_OK`).

## Écart assumé, corrigé dans la foulée

La CI de `main` était **rouge avant ce lot** (préexistant) : `responsive.spec.ts` détectait un
débordement horizontal sur `/ajouter @ 320px` (bouton « Configurer une clé dans Profil → Mon IA »
en `whitespace-nowrap`, libellé trop long). Corrigé (le libellé passe sur deux lignes en gardant la
hauteur de pilule) — CI redevenue **verte**. Rien d'autre touché sur cet écran (lot voisin
`pbm-debordements`).

## Reste à faire (hors de ce lot)

- **Chaîne flotte** : `pbm_catalogue_ref` (chimera) est à un alembic ancien (`216ae1bf9f95`), sans
  `element_type` (ni `energy_type`/`stage`) ; `export_cards.sql` ne les transporte pas. Une carte
  **nouvelle** sans image, ajoutée par l'import hebdo, naît `element_type = NULL` (fond `colorless`)
  jusqu'au prochain backfill. Remettre la base de référence à `head` réglerait les trois d'un coup.
- **`packages/api-client/src/schema.d.ts`** (types OpenAPI générés) non régénéré : les écrans
  touchés utilisent des types écrits à la main (à jour), la CI ne le contrôle pas — dette mineure.
