# Lot `v3-identification-visuelle` — Identifier sans IA : comparer chaque carte détectée aux images officielles de la base

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P1** · piste IA — des photos aux cartes · couloir **CH3** — Catalogue, prix & e2e (**chimera**) · prévu du 23 oct. au 29 oct. · jalon **MVP en UAT** · taille M · complexité 4/5 · difficulté 4/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v3-identification-visuelle`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v3-identification-visuelle -b roadmap/v3-identification-visuelle origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/v3-identification-visuelle.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v3-identification-visuelle` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-v3-identification-visuelle`, branche `roadmap/v3-identification-visuelle` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v3-identification-visuelle
python3 docs/roadmap/suivi.py demarrer v3-identification-visuelle --machine "$(hostname -s)" --branche roadmap/v3-identification-visuelle
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v3-identification-visuelle attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v3-identification-visuelle — <raisons>`.
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

**Gain.** La plupart des cartes sont reconnues sans aucun appel IA, y compris sur une photo de classeur (chaque carte est d'abord découpée) ; l'IA n'intervient que si la comparaison hésite — et alors avec 2-3 candidats seulement.

**Fonctionnalités.** Index d'empreintes visuelles de toutes les images officielles (zone d'illustration + carte entière) ; pour chaque recadrage redressé : plus proches voisins, score, décision « reconnue sans IA » au-delà d'un seuil ; sinon l'IA tranche entre les candidats et estime l'état dans le même appel.

**Tenants — ce qu'il faut avant.** Détection et redressement (v3-detection), identification par IA (v3-identification), images officielles de toutes les cartes (v2-catalogue-complet).

**Aboutissants — ce que ça ouvre.** Coût IA par photo divisé ; reconnaissance possible même sans clé IA pour les cartes non ambiguës (à confirmer avec D4).

**Dépend de :**
- `v3-identification` — Identifier chaque carte et la rapprocher du catalogue (top 3 avec confiance)
- `v2-catalogue-complet` — Base de référence complète : toutes les cartes, toutes leurs infos, tous les prix — avant la première photo

## 3. Mission

1. Construire l'index : télécharger les images officielles basse définition de toutes les cartes (hors serveur de PROD : sur devAI ou chimera), calculer des empreintes perceptuelles robustes (pHash/dHash sur la zone d'illustration et la carte entière, éventuellement un descripteur couleur), stocker en base (`card_visual_index`) et dans la graine du catalogue.
2. Recherche : pour chaque recadrage, top 5 par distance, score calibré ; groupe « même illustration » résolu par le numéro lu (OCR local léger du bas de carte) quand c'est possible.
3. Intégration dans le pipeline existant, dans cet ordre : cache d'empreinte (photo déjà vue) → comparaison visuelle → IA seulement si ambiguïté, avec les candidats visuels dans le même appel que l'estimation d'état.
4. Mesure sur le jeu de 100 cartes étiquetées de v3-identification (dont les 9 de la photo de référence) : part reconnue sans IA, précision top-1 sans IA, appels IA économisés ; seuil choisi pour ne pas dégrader la précision.
5. Ressources : temps de recherche < 200 ms par carte et empreinte mémoire compatible avec le serveur de 4 Go (mesurées).

## 4. Risques & pièges

Même illustration pour plusieurs cartes (réimpressions, reverse, versions FR/EN, promos) : la comparaison visuelle donne un groupe, pas une carte — le numéro et la langue départagent (lecture OCR locale légère, sinon IA) ; pochettes et reflets dégradent le score : seuil calibré sur le jeu de photos réelles ; taille de l'index (≈ 20 000 × 2 langues) : empreintes compactes, pas de modèle lourd sur le serveur de 4 Go.

## 5. Livrables — définition de « fini »

- index visuel de toutes les cartes
- part reconnue sans IA et précision mesurées
- pipeline cache → visuel → IA
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
- `maquette` — Conforme à la maquette (sans objet : back-end ; le badge « reconnue sans IA » est affiché par l'écran de validation)
- `doc_tech` — Doc technique (CLAUDE.md, docs/)
- `release_uat` — Recette locale sur chimera
- `release_prod` — Livré en PROD (preuve)
- `backlog` — BACKLOG.md et état à jour
- `compte_rendu` — Compte rendu dans le suivi

```bash
python3 docs/roadmap/suivi.py tache v3-identification-visuelle <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v3-identification-visuelle --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v3-identification-visuelle <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v3-identification-visuelle: …" && git push -u origin roadmap/v3-identification-visuelle && gh pr create --fill
```

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

