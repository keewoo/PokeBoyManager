# Lot `v8-mineurs` — Échanger quand on a quinze ans

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Échanges entre collectionneurs · couloir **CH6** — Échanges — écrans, appariement & messagerie (**chimera**) · prévu du 4 janv. au 8 janv. · jalon **En ligne** · taille M · complexité 2/5 · difficulté 4/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v8-mineurs`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v8-mineurs -b roadmap/v8-mineurs origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/v8-mineurs.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v8-mineurs` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-v8-mineurs`, branche `roadmap/v8-mineurs` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v8-mineurs
python3 docs/roadmap/suivi.py demarrer v8-mineurs --machine "$(hostname -s)" --branche roadmap/v8-mineurs
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v8-mineurs attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v8-mineurs — <raisons>`.
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

**Gain.** Les premiers utilisateurs sont des collégiens. Une fonctionnalité d'échange pensée pour des adultes se retourne immédiatement contre eux : adresse postale exposée, argent, contact direct avec des inconnus.

**Fonctionnalités.** Âge calculé depuis la date de naissance (v1-identite) ; accord parental enregistré (adresse du responsable, trace horodatée) avant le premier échange d'un mineur ; adresse postale jamais affichée à qui que ce soit ; plafond de valeur pour les comptes jeunes ou neufs ; signalement en un geste sur toute offre et tout message.

**Tenants — ce qu'il faut avant.** Identité du compte, offre, expédition.

**Aboutissants — ce que ça ouvre.** Conditionne l'ouverture des modes payants à la population réelle.

**Dépend de :**
- aucune

**Décision D13** (avant le 14 déc.) : Âge minimum pour échanger et accord parental. Le public de départ est majoritairement mineur, et aucun mode où l'utilisateur avance de l'argent ne lui est ouvert. Proposition : échange direct dès 13 ans avec accord parental enregistré ; tout mode avec caution ou commission réservé aux 18 ans et plus. — lis la décision prise dans `etat.json` (`decisions_prises`) et applique-la à la lettre.

## 3. Mission

1. Calcul de l'âge et politique d'accès à l'échange, appliquée côté serveur et pas seulement à l'écran.
2. Accord parental : demande par e-mail au responsable, confirmation tracée, révocable.
3. Plafond de valeur par ancienneté et par nombre d'échanges aboutis, expliqué à l'utilisateur.
4. Signalement et blocage d'un membre, accessibles depuis chaque offre et chaque message.
5. Tests : compte de 12 ans, de 15 ans sans accord, de 15 ans avec accord, de 17 ans face à un mode payant.

## 4. Risques & pièges

C'est le lot qui peut interdire deux des trois mécaniques : aucun mode où l'utilisateur avance de l'argent n'est ouvert à un compte de moins de 18 ans. À trancher (D13) AVANT d'écrire une ligne de séquestre. Le plafond de valeur doit être une protection, pas une punition : il s'explique à l'écran et il se lève avec l'ancienneté.

## 5. Livrables — définition de « fini »

- politique d'âge appliquée côté serveur
- accord parental tracé et révocable
- aucune adresse postale visible dans l'interface
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
python3 docs/roadmap/suivi.py tache v8-mineurs <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v8-mineurs --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v8-mineurs <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v8-mineurs: …" && git push -u origin roadmap/v8-mineurs && gh pr create --fill
```

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

