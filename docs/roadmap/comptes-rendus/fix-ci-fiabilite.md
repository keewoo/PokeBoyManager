# fix-ci-fiabilite — une CI qui ne ment pas

> Correctif hors plan ouvert le 01/10/2026 après trois échecs de CI sur `main` sur un arbre
> identique à une branche verte (`f105cef`), « réparés » par trois commits vides (`0c544c5`,
> `f11cabf`, `5b3916b`). Deux causes, indépendantes. Les deux sont corrigées à la racine.

## 1. Build web — `next/font/google` tiré du réseau au build

**Symptôme.** `next build` échouait par intermittence (~50 %) avec
`TypeError: Cannot read properties of null (reading '1')` dans `nextFontGoogleFontLoader`
(runs `36915337319`, `36917084943`, et déjà le 01/10 à 12:03).

**Cause.** `apps/web/src/app/layout.tsx` chargeait **Exo 2, JetBrains Mono, Press Start 2P et
Roboto** via `next/font/google`, qui **télécharge les polices depuis `fonts.googleapis.com`
pendant la construction**. La moindre réponse incomplète de Google cassait le build. Rien dans le
dépôt ne le garantissait : le build dépendait d'un service tiers.

**Correctif.** Polices **embarquées** dans le dépôt, servies par `next/font/local` — plus aucun
appel réseau au build.
- `apps/web/src/app/fonts/` : un `.woff2` par famille (sous-ensembles **latin + latin-ext**
  réunis, axe `wght` complet conservé pour les trois familles variables ; Press Start 2P statique
  400), découpés avec `fonttools`/`pyftsubset` depuis la police amont de `google/fonts`.
- `apps/web/src/app/fonts.ts` : les quatre déclarations `localFont`, **mêmes variables CSS**
  (`--font-roboto`, `--font-exo2`, `--font-jetbrains-mono`, `--font-press-start`), mêmes graisses
  et styles qu'avant. `layout.tsx` les importe au lieu de `next/font/google`.
- Licences dans `apps/web/src/app/fonts/` : `LICENSE-*-OFL.txt`. **Les quatre sont sous OFL 1.1**,
  y compris Roboto : la mission annonçait Apache 2.0, mais Google a relicencié Roboto en OFL en
  2024 (le dépôt `google/fonts` le sert désormais depuis `ofl/roboto/`, plus `apache/`). La
  licence embarquée est celle qui gouverne réellement ces octets.

**Preuve.** Plus aucun `import … from "next/font/google"` dans le dépôt (il ne reste que des
mentions en commentaire expliquant le pourquoi). Build web vert en CI. Rendu identique avant/après
(mêmes familles/graisses/variables ; glyphes français — é à ç è ô û œ Œ Ÿ « » — vérifiés présents
dans chaque `.woff2`). **Pas de capture d'écran avant/après** produite : la session de correctif tourne en autonomie sur chimera, sans navigateur (les navigateurs Playwright y exigent `sudo`/`libnspr4`) et sans serveur de rendu. La parité visuelle repose sur l'identité des octets de police avec ceux que servait Google et sur le **build web vert** (`pnpm build:web`, 25/25 pages) — à confirmer à l'œil à la prochaine livraison UAT si on veut la preuve visuelle.

## 2. e2e — interblocage Postgres (`DeadlockDetectedError`)

**Symptôme.** Run `36916045307`, job e2e `110550141463` :
`asyncpg.exceptions.DeadlockDetectedError: deadlock detected`, levé par l'API pendant un parcours
Playwright. Trace : `routers/uploads.py:confirm_all_detections` → `validation/service.py:confirm_all`
→ `db.commit()` → `bind_execute_many`. DETAIL Postgres : cycle entre deux transactions
(`Process 223 waits for … blocked by 221 ; 221 waits for … blocked by 223`).

**Cause (établie, pas supposée — reproduite sur Postgres).** Deux transactions concurrentes
écrivent les **mêmes lignes `detections`** d'un envoi :
- le **passage d'état** du worker (`state/service.py:run_state_estimation_for_upload`, chaîné dans
  `detect_cards`) verrouille les détections **une par une**, dans l'ordre de son `SELECT` : chaque
  détection d'une vraie photo pointe une carte **différente**, donc le `db.get(Card)` de
  `_matched_card_signals` fait une requête à chaque tour → autoflush → un verrou `NO KEY UPDATE`
  de plus, dans l'ordre du tas ;
- `confirm_all` (« Tout ajouter », déclenché par le front en `Promise.all` sur les envois)
  verrouille **toutes** ses détections d'un bloc à son unique `commit` — et SQLAlchemy trie ce
  flush par clé primaire (ordre **ascendant**).

Les deux ordres diffèrent (tas vs clé) → cycle → interblocage. Ce n'est pas qu'un défaut de CI :
la même course peut se produire en PROD (un utilisateur clique « Tout ajouter » pendant que la
reconnaissance finit l'estimation d'état).

**Ce qui a été éliminé par l'expérience** (sur `pbm-shared-postgres-1`, 55432) : deux `confirm_all`
concurrents, ou `confirm_all || état` avec une **carte partagée**, ne produisent **aucun**
interblocage (40 tours chacun) — la carte partagée met le `Card` en cache d'identité, supprime
l'autoflush incrémental, et les deux flux verrouillent alors dans le même ordre. Le défaut n'existe
qu'avec des cartes distinctes (le cas réel) : c'est ce qui a égaré le premier diagnostic.

**Correctif — un ordre de verrouillage global, à la racine.** `ORDER BY detections.id` sur **toutes**
les transactions qui écrivent ces lignes :
- `state/service.py:run_state_estimation_for_upload` — **le maillon essentiel** : verrouille
  désormais en id ascendant, comme `confirm_all` ;
- `validation/service.py:confirm_all` — `ORDER BY detections.id` **+ `with_for_update()`** : le
  flush ORM triait déjà par clé, mais le verrou est désormais pris **à la lecture**, en ordre
  ascendant explicite, avant toute écriture ;
- `identification/service.py:run_identification_for_upload` — même `ORDER BY` par discipline
  uniforme (ce passage committe par détection, il ne garde qu'un verrou à la fois, mais l'ordre
  commun le garde sûr si ce commit par détection venait à disparaître).

Un ordre total unique partagé par toutes les transactions rend le cycle **impossible** (elles se
sérialisent au pire, sans jamais s'interbloquer). **Aucune relance automatique** sur
`DeadlockDetectedError` : la cause est évitée, pas rattrapée.

**Test qui mord.** `apps/api/tests/test_confirm_all_deadlock.py` pilote le **vrai** passage d'état
concurremment à `confirm_all`, avec deux détections liées à des cartes distinctes semées pour que
le `SELECT` non ordonné les parcoure à rebours de l'ordre des clés, et un verrou (`monkeypatch`)
qui suspend l'état juste après son premier verrou. Vérifié sur Postgres :
- **avec** le correctif : passe ;
- **sans** l'`ORDER BY` du passage d'état : interblocage → le test échoue.

**Mesure refaite dans ce lot** (base jetable `pbm_dl_exp`, reproduction déterministe autonome hors pytest, sur `pbm-shared-postgres-1:55432`) : **avec** l'`ORDER BY` du passage d'état → *pas d'interblocage* ; **sans** → *deadlock*. Fichier restauré ensuite (diff final = le seul ajout de l'`ORDER BY`).

## 3. Relancer une CI instable sans polluer `main`

Le jeton de devAI (`~/.kailo-tokens`) a la permission `actions=read` mais **pas `actions=write`** :
`POST /repos/keewoo/PokeBoyManager/actions/runs/{id}/rerun-failed-jobs` répond **403**
(`x-accepted-github-permissions: actions=write`). devAI **ne peut donc pas** relancer un passage à
la place d'un commit vide. La permission manquante est **`actions: write`** (jeton à grain fin ;
équivalent classique : scope `workflow`). Documenté dans `docs/CODE.md`. Tant qu'elle n'est pas
accordée, la vraie parade reste celle de ce lot : rendre la CI déterministe pour n'avoir plus à la
relancer.

## Ce qui reste

- La relance de CI par API reste indisponible à devAI (permission `actions: write` manquante) —
  ce n'est pas un défaut de code, c'est un choix de périmètre du jeton, à trancher par JF.
- Flake connu hors de ce lot : aucun autre identifié après ce correctif.
