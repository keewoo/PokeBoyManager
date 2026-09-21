# Lot `v1-byok` — Coffre de clés IA : Claude, Gemini ou OpenAI par utilisateur

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Compte privé & sécurité · couloir **DA1** — API, comptes & données (**devAI**) · prévu du 19 sept. au 19 sept. · jalon **MVP en UAT** · taille M · complexité 3/5 · difficulté 3/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v1-byok`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v1-byok -b roadmap/v1-byok origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-v1-byok && nohup claude -p --dangerously-skip-permissions < prompts/v1-byok.md > ~/dev/logs/v1-byok.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v1-byok` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-v1-byok`, branche `roadmap/v1-byok` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v1-byok
python3 docs/roadmap/suivi.py demarrer v1-byok --machine "$(hostname -s)" --branche roadmap/v1-byok
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v1-byok attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v1-byok — <raisons>`.
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

**Gain.** Chaque utilisateur branche sa propre IA : pas de coût IA pour la plateforme, pas de dépendance à un seul fournisseur.

**Fonctionnalités.** Ajouter, tester, remplacer, supprimer une clé par fournisseur ; choisir le fournisseur par défaut ; voir l'usage (appels, coût estimé).

**Tenants — ce qu'il faut avant.** Comptes ; D4 (comportement sans clé).

**Aboutissants — ce que ça ouvre.** Couche fournisseurs IA, reconnaissance, anecdotes, étude en jeu.

**Dépend de :**
- `v1-auth` — Comptes : inscription, connexion, vérification d'e-mail, mot de passe oublié

**Décision D4** (avant le 19 sept.) : Sans clé IA personnelle : reconnaissance désactivée (ajout manuel possible). RÉVISÉE le 19/09 puis le 21/09 : la clé d'Aymeric sert à pré-générer les fiches, plafond 50 €, contenu réduit à 2 anecdotes en français + règles de jeu, ciblage large (80 % des cartes). — lis la décision prise dans `etat.json` (`decisions_prises`) et applique-la à la lettre.

## 3. Mission

1. `PUT/DELETE /me/ai-keys/{provider}`, `POST /me/ai-keys/{provider}/test` (appel minimal au fournisseur), `GET /me/ai-keys` (masques seulement), `PATCH /me/ai-settings` (fournisseur et modèle par défaut).
2. Chiffrement : AES-256-GCM, nonce aléatoire, `user_id` en données associées (une clé copiée dans un autre compte ne se déchiffre pas) ; rotation de la clé maître documentée.
3. Filtre de journalisation qui masque tout motif de clé (`sk-`, `AIza`, `sk-ant-`) ; test qui échoue si une clé apparaît dans les logs.
4. Table d'usage : appels, jetons, coût estimé par fournisseur et par mois.

## 4. Risques & pièges

La clé est le secret le plus sensible du système : chiffrement enveloppe AES-256-GCM (clé maître dans l'environnement, jamais en base), jamais renvoyée (affichage `sk-ant-…4f2a`), jamais journalisée, déchiffrée seulement dans le worker au moment de l'appel.

## 5. Livrables — définition de « fini »

- routes du coffre + tests
- test de non-fuite dans les journaux
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
- `maquette` — Conforme à la maquette (sans objet : back-end ; l'écran est porté par v1-profil)
- `doc_tech` — Doc technique (CLAUDE.md, docs/)
- `release_uat` — Recette locale sur chimera
- `release_prod` — Livré en PROD (preuve)
- `backlog` — BACKLOG.md et état à jour
- `compte_rendu` — Compte rendu dans le suivi

```bash
python3 docs/roadmap/suivi.py tache v1-byok <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v1-byok --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v1-byok <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v1-byok: …" && git push -u origin roadmap/v1-byok && gh pr create --fill
```

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

