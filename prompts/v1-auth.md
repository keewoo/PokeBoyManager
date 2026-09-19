# Lot `v1-auth` — Comptes : inscription, connexion, vérification d'e-mail, mot de passe oublié

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Compte privé & sécurité · couloir **DA1** — API, comptes & données (**devAI**) · prévu du 28 sept. au 2 oct. · jalon **MVP en UAT** · taille M · complexité 4/5 · difficulté 3/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v1-auth`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v1-auth -b roadmap/v1-auth origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-v1-auth && nohup claude -p --dangerously-skip-permissions < prompts/v1-auth.md > ~/dev/logs/v1-auth.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v1-auth` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-v1-auth`, branche `roadmap/v1-auth` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v1-auth
python3 docs/roadmap/suivi.py demarrer v1-auth --machine "$(hostname -s)" --branche roadmap/v1-auth
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v1-auth attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v1-auth — <raisons>`.
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

**Gain.** L'espace devient privé : chaque donnée appartient à un compte.

**Fonctionnalités.** Inscription e-mail + mot de passe, e-mail de vérification, connexion, déconnexion, mot de passe oublié, sessions multiples.

**Tenants — ce qu'il faut avant.** Schéma ; D5 (e-mails transactionnels) — Mailpit en local en attendant.

**Aboutissants — ce que ça ouvre.** Toutes les routes protégées, profil, coffre de clés IA.

**Dépend de :**
- `v0-schema` — Modèle de données PostgreSQL v1 et migrations Alembic

**Décision D5** (avant le 26 sept.) : Nom de domaine et fournisseur d'e-mails transactionnels (vérification d'adresse, mot de passe oublié) : Brevo, Resend ou SMTP existant. — lis la décision prise dans `etat.json` (`decisions_prises`) et applique-la à la lettre.

## 3. Mission

1. `POST /auth/register`, `/auth/login`, `/auth/logout`, `/auth/verify-email`, `/auth/forgot`, `/auth/reset` ; mots de passe argon2id, 10 caractères minimum, contrôle contre les mots de passe compromis (k-anonymat HIBP).
2. Session : cookie `HttpOnly; Secure; SameSite=Lax`, identifiant opaque stocké haché en base, rotation à la connexion, jeton CSRF sur les requêtes qui écrivent.
3. Limitation : 5 tentatives / 15 min par compte et par IP (Redis) ; réponses identiques pour e-mail inconnu.
4. Dépendance FastAPI `current_user` : toute route utilisateur filtre par `user_id` (jamais d'identifiant d'utilisateur reçu du client).
5. Tests : parcours complet, jeton expiré, jeton réutilisé, force brute, session révoquée.

## 4. Risques & pièges

Énumération de comptes (réponses identiques qu'un e-mail existe ou non), force brute (limitation par IP et par compte), CSRF avec cookie de session.

## 5. Livrables — définition de « fini »

- routes d'authentification + tests
- e-mails reçus dans Mailpit
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
- `maquette` — Conforme à la maquette (sans objet : back-end seul)
- `doc_tech` — Doc technique (CLAUDE.md, docs/)
- `release_uat` — Recette locale sur chimera
- `release_prod` — Livré en PROD (preuve)
- `backlog` — BACKLOG.md et état à jour
- `compte_rendu` — Compte rendu dans le suivi

```bash
python3 docs/roadmap/suivi.py tache v1-auth <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v1-auth --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v1-auth <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v1-auth: …" && git push -u origin roadmap/v1-auth && gh pr create --fill
```

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

