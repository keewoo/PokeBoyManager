# Lot `v8-recherche-offres` — Chercher chez les autres : l'API de recherche des cartes proposées

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Échanges entre collectionneurs · couloir **DA4** — Échanges — règles, transfert & argent (**devAI**) · prévu du 11 janv. au 15 janv. · jalon **En ligne** · taille M · complexité 3/5 · difficulté 3/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v8-recherche-offres`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v8-recherche-offres -b roadmap/v8-recherche-offres origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-v8-recherche-offres && nohup claude -p --dangerously-skip-permissions < prompts/v8-recherche-offres.md > ~/dev/logs/v8-recherche-offres.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v8-recherche-offres` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-v8-recherche-offres`, branche `roadmap/v8-recherche-offres` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v8-recherche-offres
python3 docs/roadmap/suivi.py demarrer v8-recherche-offres --machine "$(hostname -s)" --branche roadmap/v8-recherche-offres
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v8-recherche-offres attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v8-recherche-offres — <raisons>`.
- Tu n'accordes **jamais** toi-même une dérogation.

## 1. Cadre — relire avant d'agir

| Document | Pourquoi |
|---|---|
| `CLAUDE.md` | règles du dépôt, commandes, conventions |
| `docs/ARCHITECTURE.md` | stack, données, coffre de clés, reconnaissance |
| `docs/roadmap/PROCESSUS.md` | suivi, garde-fou, clôture |
| `docs/roadmap/ROADMAP.html` — onglet **Maquette** | l'écran à reproduire (front) |
| `BACKLOG.md` | l'état des autres lots |
| `~/.claude/CLAUDE.md` de la machine | règles de la flotte (construire ≠ servir, Python 3.12, WSL) |

Le cadre l'emporte sur ce prompt : en cas de contradiction, passe en `attente_validation` avec la contradiction en motif.

## 2. Contexte

**Gain.** La recherche qu'on a cherche dans le CATALOGUE (toutes les cartes qui existent) et dans MA collection. Échanger demande la troisième, qui n'existe pas encore : chercher dans ce que les AUTRES proposent.

**Fonctionnalités.** Recherche plein texte sur les exemplaires marqués échangeables, tous membres confondus ; réutilise l'analyse de requête et le score trigram de `catalog/search.py` (numéros `236/217`, `XY121`, `TG05`, noms FR/EN désaccentués) ; facettes extension, série, rareté, langue, état et tranche de valeur avec leurs compteurs ; tri par pertinence, valeur ou fraîcheur ; pagination par curseur, mêmes conventions que `GET /collection`.

**Tenants — ce qu'il faut avant.** `catalog/search.py` (`parse_query`, `match_candidates`, index GIN `pg_trgm` déjà posés), `collection/service.py` (filtres, curseur), exemplaires échangeables de `v8-disponibilite`.

**Aboutissants — ce que ça ouvre.** La vitrine, les suggestions d'équilibrage, et plus tard la question directe « qui a cette carte ? ».

**Dépend de :**
- `v8-disponibilite` — Mes doublons, et ce que j'accepte d'échanger

## 3. Mission

1. Réutiliser `parse_query` et le score trigram plutôt que d'écrire une seconde recherche : une requête qui marche dans le catalogue doit marcher ici, y compris les formats de numéro.
2. Clause de visibilité écrite UNE fois, réutilisable, et testée pour elle-même : exemplaire non échangeable, exemplaire réservé, compte bloqué ou signalé, mes propres cartes, compte supprimé.
3. Facettes avec compteurs, tris et pagination par curseur, alignés sur `GET /collection`.
4. Mesure sur jeu de données : 10 000 exemplaires échangeables répartis sur 200 comptes — temps de réponse relevé, plan de requête lu, index posés en conséquence.

## 4. Risques & pièges

C'est la PREMIÈRE requête du produit qui sort du `user_id` courant : aujourd'hui `_apply_cheap_filters` commence par `where(CollectionItem.user_id == user_id)`, et c'est ce mur qui garantit que l'espace est privé. On ne l'enlève pas, on ouvre une porte étroite — uniquement les exemplaires explicitement marqués échangeables, jamais le reste de la collection, jamais l'identité au-delà du pseudo, jamais un compte bloqué, sous signalement ou supprimé. C'est aussi la première requête qui balaie les données de tout le monde : index et plan de requête MESURÉS, pas supposés.

## 5. Livrables — définition de « fini »

- API de recherche des offres : facettes, tris, curseur
- clause de visibilité unique, testée à part
- temps de réponse et plan de requête consignés
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Aucun secret dans le dépôt, les journaux ou les sorties.

## 6. Tests exigés

- Un test qui **échoue sans** ton changement et passe avec.
- Route utilisateur → test d'accès croisé (l'utilisateur B reçoit 404 sur les objets de A).
- Front → conformité à l'écran de la maquette (capture jointe au compte rendu).
- Suites complètes lancées sur la flotte (`fleet-run` depuis le Mac, ou directement sur la machine), jamais sur le Mac de JF.

## 7. Clôture — obligatoire

Grille de tâches du lot :
- `dev` — Développement
- `tests` — Tests (unitaires, API, e2e)
- `securite` — Contrôle sécurité (isolation, secrets)
- `maquette` — Conforme à la maquette (sans objet : API sans écran ; la vitrine est dans v8-vitrine)
- `doc_tech` — Doc technique (CLAUDE.md, docs/)
- `release_uat` — Recette locale sur chimera
- `release_prod` — Livré en PROD (preuve)
- `backlog` — BACKLOG.md et état à jour
- `compte_rendu` — Compte rendu dans le suivi

```bash
python3 docs/roadmap/suivi.py tache v8-recherche-offres <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v8-recherche-offres --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v8-recherche-offres <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v8-recherche-offres: …" && git push -u origin roadmap/v8-recherche-offres
bash scripts/ouvrir-pr.sh roadmap/v8-recherche-offres   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

