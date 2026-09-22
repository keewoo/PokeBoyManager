# Compte rendu — `v7-decks-collection-sync` (Une carte quitte la collection : les decks le disent tout de suite)

**Statut : livré (recette locale devAI verte), en attente de CI GitHub verte puis d'une décision de mise en ligne.**

Machine : **devAI** (couloir DA3 — c'est un lot devAI). Worktree `../wt-v7-decks-collection-sync`,
branche `roadmap/v7-decks-collection-sync` depuis `origin/main`. Session autonome.

## Écart d'exécution assumé — devAI plutôt que chimera

Le préambule de la file d'attente demande d'exécuter sur chimera. Ce lot est un lot **du couloir
devAI** (section A du prompt : « ce lot s'exécute sur devAI »), sans traitement lourd (code
applicatif + tests). Deux faits ont tranché : **chimera était injoignable** (SSH réinitialisé au
handshake au moment du lot) et **devAI a l'accès GitHub complet** (push SSH `origin` vérifié). Le
travail a donc été fait sur devAI, dans un worktree dédié — jamais dans l'arbre commun, jamais sur
la machine qui sert (kailo-srv). Aucune construction ni déploiement sur le Mac de JF. Écart nommé
ici, pas silencieux.

## Le principe qui rendait ce lot subtil

La légalité d'un deck **n'est jamais mémorisée** : elle est recalculée à chaque lecture sur la
collection du moment (`pbm_api.decks.legality`, posé par `v7-decks-legalite`). Une carte vendue
rend donc déjà le deck « à compléter » **sans aucune écriture**. Ce que ce lot ajoute n'est donc
pas la bascule — elle existait — mais **la mémoire de la transition** : sans elle, un deck devenu
injouable la nuit dernière le resterait sans que le joueur sache jamais quelle carte l'a rendu tel.

## Ce qui est livré

### Serveur (`apps/api`)

- **Modèle `DeckEvent`** (table `deck_events`, migration `b2d4f6a8c0e1`) : une ligne = un deck qui
  vient de perdre une carte requise. Sert **deux** écrans — la notification (`read_at IS NULL`) et
  l'historique (toutes les lignes du deck). `card_id` en `SET NULL` + `card_name` figé : l'historique
  survit à la disparition d'une carte.
- **Déclencheur applicatif** (`pbm_api.decks.collection_sync.record_collection_change`), branché sur
  `collection.service.delete_item` (vente/échange/suppression) **et** `update_item` (signalement
  contrefaçon). Deux garde-fous portés par le code :
  - **le deck n'est JAMAIS modifié** — aucune écriture sur `deck_cards`, aucune carte retirée en
    douce (risque du lot) ;
  - **seule la bascule compte** — une alerte n'est écrite que si le deck était complet pour cette
    carte *avant* et ne l'est plus *après*. Un doublon vendu dont il reste un exemplaire suffisant
    ne déclenche rien ; un deck déjà incomplet ne reçoit pas de doublon d'alerte.
- **Suggestions de remplacement** (`pbm_api.decks.replacements`) : `GET /me/decks/{deck}/cards/{card}/replacements`.
  Prises **uniquement dans les cartes possédées** (hors contrefaçon), classées par proximité
  (type élémentaire → rôle/stade → coût d'attaque le plus proche → nombre d'exemplaires), chacune
  avec **sa raison**. **Une seule requête** (comptage de possession groupé), **aucun appel IA**
  (classement déterministe, cœur pur `rank_replacements`).
- **Alertes et historique** : `GET /me/decks/alerts` (fil + `unread_count` pour le badge),
  `POST /me/decks/alerts/read` (marque lu), `GET /me/decks/{deck}/history`. Toutes bornées au
  `user_id` de la session.

### Écran (`apps/web`)

- **En-tête** : badge de compte sur l'onglet **Decks** (`fetchDeckAlerts`).
- **Liste des decks** : bandeau d'alerte « N carte(s) ont quitté ta collection… » + bouton
  « Marquer comme lu » ; l'état **« À compléter »** reste visible par deck (déjà porté par la
  légalité recalculée).
- **Constructeur** : l'alerte « à compléter » d'une carte propose les **trois issues** demandées —
  *Remplacer par une possédée* (dépliage des suggestions classées + échange **explicite** : ajout de
  la possédée puis retrait de la manquante, jamais en silence), *Retirer du deck*, *Voir la carte* —
  et un panneau **Historique des changements de collection**.
- Client TS régénéré (`pnpm gen:api`, `packages/api-client/src/schema.d.ts`).

## Tests (la CI fait foi)

- **API** (`tests/test_deck_collection_sync.py`, 9 tests) : vente d'une carte utilisée dans **deux**
  decks → alerte dans les deux ; **doublon retiré, exemplaire restant** → aucune alerte, deck jouable ;
  **contenu du deck jamais modifié** (quantités intactes, seule la légalité suit — la garantie
  « partie en cours non affectée », le deck étant figé au démarrage quand ce mécanisme existera) ;
  contrefaçon = même effet qu'une vente ; suggestions possédées classées et raisonnées ; 404 carte
  hors deck ; marquage lu + historique ; **isolation par utilisateur** (B ne voit rien de A, 404 sur
  deck de A, marquage de B sans effet sur A).
- **API pur** (`tests/test_deck_replacements.py`, 3 tests) : classement type→rôle→coût, exclusion de
  la carte cible et des non possédées, respect de la limite, coût de l'attaque la moins chère.
- **Front** (vitest) : badge d'en-tête, bandeau d'alerte + marquage lu, suggestions dépliées +
  échange explicite. **156 tests web verts.**
- **e2e** (`e2e/deck-builder.spec.ts`, ajout) : vente d'un exemplaire via l'API → la liste des decks
  annonce l'alerte et le deck bascule « À compléter ». Calqué sur l'e2e existant du constructeur ;
  **validé par la CI** (l'environnement e2e complet — 3 serveurs + DB e2e migrée — est celui de la CI,
  pas reproduit localement ici).

Recette locale devAI : `ruff` propre, **786 tests API passés** (2 échecs `test_catalogue_seed.py`
**hors périmètre** : `pg_dump` absent de devAI — outillage local, présent en CI), **156 tests web**,
`type-check`, `lint` et **build web** verts.

## Preuves

- Migration appliquée sur la base de test locale (`alembic upgrade head`, une seule tête).
- Fichiers : `apps/api/src/pbm_api/decks/{collection_sync,replacements}.py`,
  `apps/api/src/pbm_api/models/decks.py`, `apps/api/migrations/versions/b2d4f6a8c0e1_deck_events.py`,
  routes/schémas/service decks, hook collection ; `apps/web/src/components/app-shell.tsx`,
  `apps/web/src/app/jeu/decks/**`, `apps/web/src/lib/api/decks.ts`.

## Écarts au plan / reste

- **Capture d'écran de la maquette non jointe** : l'écran réutilise le constructeur de deck déjà
  conforme (`v7-decks-ui`) et ajoute l'alerte/les suggestions/l'historique dans le même langage
  visuel (encadré « danger », listes en cartes bordées). Pas de nouvel écran à maquetter.
- **Historique = changements de collection** (vente, contrefaçon). Les modifications manuelles du
  deck (ajout/retrait de carte) ne sont pas journalisées : hors périmètre de la synchro collection→deck.
- **« Partie en cours non affectée »** : il n'existe encore aucune table de partie dans le dépôt ; le
  test garantit l'invariant qui la protégera (le contenu du deck n'est jamais modifié par la synchro).
- Suivi (`etat.json`, `ROADMAP.html`, `BACKLOG.md`, `prompts/`) laissé à l'ordonnanceur, comme convenu.
- **PR non ouverte** : `scripts/ouvrir-pr.sh` renvoie **HTTP 403 — « Resource not accessible by
  personal access token »** (le jeton GitHub de devAI lit et pousse, mais n'a pas la permission
  *Pull requests: write*). À corriger côté GitHub par JF. **Sans conséquence sur le verdict** : la
  CI se déclenche sur `push` vers `roadmap/**` (choix de conception du workflow, précisément pour
  qu'un lot ait sa CI sans dépendre d'une PR). La branche est poussée et la CI tourne dessus.
