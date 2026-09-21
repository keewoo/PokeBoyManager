# Lot `v8-disponibilite` — Mes doublons, et ce que j'accepte d'échanger

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Échanges entre collectionneurs · couloir **DA4** — Échanges — règles, transfert & argent (**devAI**) · prévu du 4 janv. au 8 janv. · jalon **En ligne** · taille M · complexité 2/5 · difficulté 2/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v8-disponibilite`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v8-disponibilite -b roadmap/v8-disponibilite origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-v8-disponibilite && nohup claude -p --dangerously-skip-permissions < prompts/v8-disponibilite.md > ~/dev/logs/v8-disponibilite.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v8-disponibilite` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-v8-disponibilite`, branche `roadmap/v8-disponibilite` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v8-disponibilite
python3 docs/roadmap/suivi.py demarrer v8-disponibilite --machine "$(hostname -s)" --branche roadmap/v8-disponibilite
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v8-disponibilite attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v8-disponibilite — <raisons>`.
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

**Gain.** Un échange commence par une phrase simple : « celle-là, je l'ai en double ». L'appli sait déjà qui possède quoi ; encore faut-il qu'elle sache ce que le propriétaire est prêt à laisser partir.

**Fonctionnalités.** Détection automatique des doublons (même carte, plusieurs exemplaires) ; marquage « échangeable » sur un EXEMPLAIRE précis, jamais sur la carte ; exemplaire réservé dès qu'une offre l'engage et libéré si l'offre tombe ; rien n'est échangeable par défaut.

**Tenants — ce qu'il faut avant.** Collection, exemplaires, decks.

**Aboutissants — ce que ça ouvre.** Toute la vague : sans stock déclaré, il n'y a rien à apparier.

**Dépend de :**
- aucune

## 3. Mission

1. Champs d'échangeabilité et de réservation sur l'exemplaire, avec l'offre qui le retient ; contrainte d'unicité en base, pas un simple contrôle applicatif.
2. Vue « mes doublons » : regroupement par carte, exemplaire conseillé à céder (le moins bien noté en état à valeur égale), valeur du lot cessible.
3. Alerte si l'exemplaire sert dans un deck : on prévient, on ne retire rien.
4. Tests : deux offres concurrentes sur le même exemplaire — la seconde échoue proprement ; annulation d'offre — l'exemplaire redevient disponible ; suppression de compte — les réservations tombent.

## 4. Risques & pièges

Le même exemplaire engagé dans deux offres à la fois est la faute classique : la réservation se pose en base (contrainte d'unicité), pas dans l'écran. Un exemplaire employé dans un deck doit le dire — même mécanique que v7-decks-collection-sync, et même règle : on prévient, on ne corrige jamais en silence.

## 5. Livrables — définition de « fini »

- doublons détectés, exemplaires marqués échangeables
- réservation garantie en base, prouvée par un test de concurrence
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
- `maquette` — Conforme à la maquette (sans objet : écran minimal, rattaché à la collection existante)
- `doc_tech` — Doc technique (CLAUDE.md, docs/)
- `release_uat` — Recette locale sur chimera
- `release_prod` — Livré en PROD (preuve)
- `backlog` — BACKLOG.md et état à jour
- `compte_rendu` — Compte rendu dans le suivi

```bash
python3 docs/roadmap/suivi.py tache v8-disponibilite <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v8-disponibilite --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v8-disponibilite <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v8-disponibilite: …" && git push -u origin roadmap/v8-disponibilite && gh pr create --fill
```

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

