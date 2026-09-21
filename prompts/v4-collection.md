# Lot `v4-collection` — Page collection : grille, filtres, tris et valeur totale

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Collection & fiche carte · couloir **CH1** — Front — comptes, accueil & collection (**chimera**) · prévu du 28 oct. au 30 oct. · jalon **MVP en UAT** · taille M · complexité 3/5 · difficulté 2/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v4-collection`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v4-collection -b roadmap/v4-collection origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/v4-collection.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v4-collection` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-v4-collection`, branche `roadmap/v4-collection` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v4-collection
python3 docs/roadmap/suivi.py demarrer v4-collection --machine "$(hostname -s)" --branche roadmap/v4-collection
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v4-collection attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v4-collection — <raisons>`.
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

**Gain.** La collection devient lisible et valorisée d'un coup d'œil.

**Fonctionnalités.** Grille ou liste ; filtres : extension, série, rareté, type, langue, état, variante, valeur min/max, date d'ajout, doublons (filtre dédié, badge ×n sur la vignette, résumé « n cartes en double, valeur des exemplaires en trop », marquage à vendre ou à échanger, suppression d'un exemplaire, choix de l'exemplaire principal), contrefaçons signalées ; recherche ; tris (valeur, variation 30 j, date, numéro) ; valeur totale et variation.

**Tenants — ce qu'il faut avant.** Validation (des cartes existent), prix.

**Aboutissants — ce que ça ouvre.** Fiche carte, tableau de bord.

**Dépend de :**
- `v3-validation` — Écran de validation : vérifier, corriger et ajouter les cartes reconnues
- `v2-prix` — Relevé quotidien des prix et historique de valeur

## 3. Mission

1. `GET /me/collection` (filtres, tri, pagination par curseur, agrégats : nombre, valeur totale, variation 7/30 j) ; `PATCH/DELETE /me/collection/{item}`.
2. Page `/collection` conforme à la maquette, filtres en panneau latéral (tiroir sur mobile), état dans l'URL.
3. Doublons : regroupement par carte avec le nombre d'exemplaires, filtre « doublons seulement », actions par exemplaire (à vendre, à échanger, supprimer, exemplaire principal) et valeur des exemplaires en trop.
4. Ajout manuel d'une carte (recherche catalogue) sans photo.
5. Test de charge : 5 000 exemplaires, réponse < 300 ms.

## 4. Risques & pièges

Performances à 5 000 cartes : pagination côté serveur, filtres en paramètres d'URL (partageables avec soi-même).

## 5. Livrables — définition de « fini »

- page collection filtrable
- mesure de performance
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
- `maquette` — Conforme à la maquette
- `doc_tech` — Doc technique (CLAUDE.md, docs/)
- `release_uat` — Recette locale sur chimera
- `release_prod` — Livré en PROD (preuve)
- `backlog` — BACKLOG.md et état à jour
- `compte_rendu` — Compte rendu dans le suivi

```bash
python3 docs/roadmap/suivi.py tache v4-collection <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v4-collection --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v4-collection <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v4-collection: …" && git push -u origin roadmap/v4-collection && gh pr create --fill
```

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

