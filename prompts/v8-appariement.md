# Lot `v8-appariement` — Le moteur d'appariement : mes doublons contre tes souhaits

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Échanges entre collectionneurs · couloir **DA4** — Échanges — règles, transfert & argent (**devAI**) · prévu du 11 janv. au 15 janv. · jalon **En ligne** · taille L · complexité 4/5 · difficulté 3/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v8-appariement`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v8-appariement -b roadmap/v8-appariement origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-v8-appariement && nohup claude -p --dangerously-skip-permissions < prompts/v8-appariement.md > ~/dev/logs/v8-appariement.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v8-appariement` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-v8-appariement`, branche `roadmap/v8-appariement` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v8-appariement
python3 docs/roadmap/suivi.py demarrer v8-appariement --machine "$(hostname -s)" --branche roadmap/v8-appariement
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v8-appariement attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v8-appariement — <raisons>`.
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

**Gain.** C'est la seule raison d'échanger ici plutôt que dans un groupe Discord : PokeBoy connaît les deux collections, les deux listes de souhaits et les deux valeurs. Il peut proposer l'échange ; personne d'autre ne le peut.

**Fonctionnalités.** Appariement bilatéral (j'ai ce que tu cherches ET tu as ce que je cherche), classé par valeur échangée et par écart ; appariement unilatéral en second rang ; chaînes à trois (A→B→C) détectées et rapportées, même si la v1 ne les exécute pas ; score de compatibilité expliqué en une phrase lisible.

**Tenants — ce qu'il faut avant.** Collection, liste de souhaits, prix du jour.

**Aboutissants — ce que ça ouvre.** La vitrine et les suggestions d'équilibrage n'affichent que ce que ce moteur produit.

**Dépend de :**
- `v8-disponibilite` — Mes doublons, et ce que j'accepte d'échanger
- `v6-import-export` — Import/export CSV et liste de souhaits

## 3. Mission

1. Index des exemplaires cessibles et des souhaits, recalculé en tâche de fond ; résultats datés et réutilisables, pas un calcul à la volée.
2. Liste de souhaits implicite déduite des extensions entamées, clairement signalée comme déduite.
3. Détection des chaînes à trois : rapport uniquement, avec le nombre de chaînes trouvées — la v1 ne les exécute pas et l'écrit.
4. Tests sur jeu de données : deux collections qui se complètent, deux qui ne se complètent pas, liste de souhaits vide, 10 000 exemplaires (mesure du temps de calcul).

## 4. Risques & pièges

La liste de souhaits vient de v6-import-export : si elle est vide, le moteur ne trouve rien et l'écran paraît cassé — prévoir une liste implicite (cartes manquantes d'une extension entamée) et le dire à l'utilisateur. Le calcul est coûteux : il tourne en tâche de fond (arq), jamais à l'affichage, et se rafraîchit à chaque changement de collection ou de souhaits.

## 5. Livrables — définition de « fini »

- appariements bilatéraux classés et expliqués
- temps de calcul mesuré et consigné
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
- `maquette` — Conforme à la maquette (sans objet : moteur sans écran ; les écrans sont dans v8-vitrine)
- `doc_tech` — Doc technique (CLAUDE.md, docs/)
- `release_uat` — Recette locale sur chimera
- `release_prod` — Livré en PROD (preuve)
- `backlog` — BACKLOG.md et état à jour
- `compte_rendu` — Compte rendu dans le suivi

```bash
python3 docs/roadmap/suivi.py tache v8-appariement <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v8-appariement --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v8-appariement <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v8-appariement: …" && git push -u origin roadmap/v8-appariement
bash scripts/ouvrir-pr.sh roadmap/v8-appariement   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

