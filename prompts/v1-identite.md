# Lot `v1-identite` — Identité du compte : prénom, nom, date de naissance, acceptation des conditions, création de compte par l'administrateur

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Compte privé & sécurité · couloir **CH1** — Front — comptes, accueil & collection (**chimera**) · prévu du 13 oct. au 14 oct. · jalon **MVP en UAT** · taille S · complexité 2/5 · difficulté 2/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v1-identite`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v1-identite -b roadmap/v1-identite origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/v1-identite.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v1-identite` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-v1-identite`, branche `roadmap/v1-identite` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v1-identite
python3 docs/roadmap/suivi.py demarrer v1-identite --machine "$(hostname -s)" --branche roadmap/v1-identite
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v1-identite attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v1-identite — <raisons>`.
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

**Gain.** Le compte porte l'identité demandée par JF (nom, date de naissance) et la preuve d'acceptation des conditions ; l'administrateur peut créer un compte déjà vérifié (premier utilisateur : Aymeric).

**Fonctionnalités.** Champs prénom (facultatif), nom, date de naissance à l'inscription et dans le profil ; case « J'accepte les conditions » obligatoire, horodatée avec la version des conditions ; commande d'administration `create-user` (e-mail vérifié, mot de passe fourni ou généré, changement forcé à la première connexion en option).

**Tenants — ce qu'il faut avant.** Pages d'authentification et profil livrés.

**Aboutissants — ce que ça ouvre.** Mise en PROD avec le compte d'Aymeric.

**Dépend de :**
- `v1-profil` — Page profil : photo, pseudo, e-mail, mot de passe, clés IA

## 3. Mission

1. Migration Alembic : `users.first_name` (nullable), `users.last_name`, `users.birth_date` (date), `users.terms_version`, `users.terms_accepted_at`, `users.must_change_password` (bool).
2. API : inscription et `PATCH /me` acceptent ces champs (validation : date passée, âge ≥ 15 ans pour l'inscription libre, conditions obligatoires) ; `GET /me` les renvoie ; export RGPD les inclut.
3. Front : champs Nom, Prénom, Date de naissance et case des conditions sur `/inscription` et dans Profil → Identité, conformes à la maquette (même style de champ).
4. Commande d'administration `uv run python -m pbm_api.admin create-user --email --pseudo --last-name --birth-date --accept-terms [--password-stdin] [--must-change-password]` : compte créé vérifié ; mot de passe lu sur l'entrée standard, jamais en argument ni journalisé.
5. Si `must_change_password` : après connexion, redirection vers l'écran de changement de mot de passe.
6. Tests : validation d'âge, conditions obligatoires, commande d'administration, accès croisé sur `/me`.

## 4. Risques & pièges

Mineurs : en France le consentement numérique seul est possible dès 15 ans (RGPD art. 8 + loi Informatique et Libertés) ; en dessous, consentement parental requis — refuser l'inscription libre sous 15 ans avec un message clair, l'administrateur peut créer le compte (consentement du parent porté par JF). Date de naissance = donnée personnelle : jamais exposée publiquement, incluse dans l'export RGPD.

## 5. Livrables — définition de « fini »

- champs d'identité en base, API et front
- commande create-user testée
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
- `release_uat` — Livré en UAT (preuve) (sans objet : déployé avec la mise en PROD)
- `release_prod` — Livré en PROD (preuve) (sans objet : déployé avec la mise en PROD)
- `backlog` — BACKLOG.md et état à jour
- `compte_rendu` — Compte rendu dans le suivi

```bash
python3 docs/roadmap/suivi.py tache v1-identite <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v1-identite --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v1-identite <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v1-identite: …" && git push -u origin roadmap/v1-identite && gh pr create --fill
```

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

