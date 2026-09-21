# Lot `v4-insights-batch` — Pré-générer histoire et étude en jeu de TOUTES les cartes, en un seul passage par carte

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P1** · piste Collection & fiche carte · couloir **CH2** — IA & vision (**chimera**) · prévu du 20 sept. au 20 sept. · jalon **MVP en UAT** · taille M · complexité 3/5 · difficulté 3/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v4-insights-batch`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v4-insights-batch -b roadmap/v4-insights-batch origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/v4-insights-batch.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v4-insights-batch` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-v4-insights-batch`, branche `roadmap/v4-insights-batch` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v4-insights-batch
python3 docs/roadmap/suivi.py demarrer v4-insights-batch --machine "$(hostname -s)" --branche roadmap/v4-insights-batch
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v4-insights-batch attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v4-insights-batch — <raisons>`.
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

**Gain.** Décision de JF (19/09) : « autant tout prendre dès le premier tir » — plus aucun appel IA à l'ouverture d'une fiche ; chaque carte est traitée une fois, toutes ses informations d'un coup.

**Fonctionnalités.** Traitement par lots (Message Batches API d'Anthropic, moitié prix, asynchrone) : pour chaque carte, UN appel qui rend ensemble anecdotes sourcées FR + EN, synthèse d'usage en jeu et note de jouabilité ; reprise, plafond de dépense, rapport de coût réel ; relance incrémentale pour les nouvelles extensions.

**Tenants — ce qu'il faut avant.** Anecdotes et étude en jeu à la demande (v4-anecdotes, v4-jeu), catalogue complet ; clé plateforme et budget (D4 révisée).

**Aboutissants — ce que ça ouvre.** Fiche carte instantanée pour toutes les cartes ; l'IA de l'utilisateur ne sert plus qu'à identifier et estimer l'état.

**Dépend de :**
- `v4-jeu` — Étude d'utilisation en jeu (légalité, attaques, présence en tournoi)
- `v2-catalogue-complet` — Base de référence complète : toutes les cartes, toutes leurs infos, tous les prix — avant la première photo

**Décision D4** (avant le 5 oct.) : Sans clé IA personnelle : reconnaissance désactivée (saisie manuelle seulement) ou quota d'essai offert sur une clé plateforme (coût à plafonner). — lis la décision prise dans `etat.json` (`decisions_prises`) et applique-la à la lettre.

## 3. Mission

1. Pipeline `insights_batch` : collecte du contexte sourcé par carte (MediaWiki API, cache local), puis requêtes Message Batches (un appel par carte : anecdotes FR + EN + étude en jeu, sortie structurée), import idempotent dans `card_insights` avec version du prompt et du modèle.
2. Clé plateforme lue depuis `PLATFORM_ANTHROPIC_API_KEY` (jamais une clé d'utilisateur), plafond `INSIGHTS_BUDGET_EUR` : le traitement s'arrête proprement avant de le dépasser et le dit.
3. Mesure sur 100 cartes représentatives : coût réel, durée, taux d'anecdotes rejetées faute de source ; extrapolation au catalogue complet dans le compte rendu.
4. Les routes à la demande (v4-anecdotes, v4-jeu) deviennent un repli pour une carte pas encore traitée — la fiche ne déclenche plus d'appel si l'insight existe.
5. Tests avec réponses enregistrées ; aucun appel réel en CI.

## 4. Risques & pièges

Coût : mesuré sur 100 cartes AVANT le passage complet, extrapolé, et plafonné par un budget explicite de JF ; sources (Poképédia/Bulbapedia) récupérées par leur API MediaWiki avec un débit raisonnable et un User-Agent identifié ; aucune anecdote sans source ; une clé PLATEFORME distincte de toute clé d'utilisateur.

## 5. Livrables — définition de « fini »

- pipeline par lots testé
- mesure de coût sur 100 cartes et extrapolation
- plafond de budget vérifié
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
- `maquette` — Conforme à la maquette (sans objet : back-end)
- `doc_tech` — Doc technique (CLAUDE.md, docs/)
- `release_uat` — Recette locale sur chimera (sans objet : appliqué au déploiement)
- `release_prod` — Livré en PROD (preuve) (sans objet : appliqué au déploiement)
- `backlog` — BACKLOG.md et état à jour
- `compte_rendu` — Compte rendu dans le suivi

```bash
python3 docs/roadmap/suivi.py tache v4-insights-batch <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v4-insights-batch --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v4-insights-batch <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v4-insights-batch: …" && git push -u origin roadmap/v4-insights-batch && gh pr create --fill
```

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

