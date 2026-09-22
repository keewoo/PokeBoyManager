# Lot `v7-effets-visuels` — Décors d'arène et animations de jeu (évolution, attaques spéciales, K.O.)

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P1** · piste Jeu — decks et parties · couloir **CH4** — Front — photos, validation & fiche carte (**chimera**) · prévu du 15 mars au 26 mars · jalon **En ligne** · taille M · complexité 3/5 · difficulté 3/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v7-effets-visuels`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v7-effets-visuels -b roadmap/v7-effets-visuels origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/v7-effets-visuels.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v7-effets-visuels` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-v7-effets-visuels`, branche `roadmap/v7-effets-visuels` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v7-effets-visuels
python3 docs/roadmap/suivi.py demarrer v7-effets-visuels --machine "$(hostname -s)" --branche roadmap/v7-effets-visuels
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v7-effets-visuels attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v7-effets-visuels — <raisons>`.
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

**Gain.** Demande de JF (19/09) : une partie doit être belle à regarder — c'est ce qui donne envie d'en refaire une.

**Fonctionnalités.** Choix du décor du plateau parmi plusieurs arènes (l'illustration fournie par JF et des variantes), mémorisé par joueur ; animations : évolution, attaque simple, attaque de carte spéciale (ex/GX/V/VMAX) avec mise en scène, mise K.O., prise de récompense, début et fin de tour.

**Tenants — ce qu'il faut avant.** Plateau de jeu, déroulé de la partie.

**Aboutissants — ce que ça ouvre.** —

**Dépend de :**
- `v7-plateau` — Plateau de jeu graphique

## 3. Mission

1. Cinq décors originaux (CSS et SVG, pas d'images lourdes), sélecteur dans la partie, mémorisé par joueur ; contraste vérifié : les cartes et les compteurs restent lisibles sur chacun.
2. Animations jouées à partir des événements du serveur (jamais décidées par le client) : évolution, attaque, attaque spéciale, K.O., prise de récompense.
3. Mise en scène des attaques de cartes spéciales (ex, GX, V, VMAX) : zoom sur la carte, effet lié au type, retour au plateau ; passable d'un clic.
4. Respect de `prefers-reduced-motion`, file d'animations (jamais deux en même temps), et reprise correcte si le joueur rafraîchit pendant une animation.
5. Mesure des images par seconde sur mobile et du poids ajouté à la page.

## 4. Risques & pièges

Décors **originaux** inspirés des ambiances du jeu, jamais des visuels officiels repris (propriété intellectuelle). Les animations ne doivent ni retarder le jeu ni masquer une information : chacune est courte (moins d'une seconde, sauf la mise en scène d'attaque spéciale), interruptible, et l'état du plateau est déjà à jour dessous. `prefers-reduced-motion` respecté (tout se joue alors en fondu court). Budget : 60 images par seconde sur un téléphone de milieu de gamme, mesuré.

## 5. Livrables — définition de « fini »

- cinq décors
- animations d'évolution, d'attaque, d'attaque spéciale et de K.O.
- mesure des images par seconde
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
- `securite` — Contrôle sécurité (isolation, secrets) (sans objet : rendu visuel)
- `maquette` — Conforme à la maquette
- `doc_tech` — Doc technique (CLAUDE.md, docs/)
- `release_uat` — Recette locale sur chimera
- `release_prod` — Livré en PROD (preuve)
- `backlog` — BACKLOG.md et état à jour
- `compte_rendu` — Compte rendu dans le suivi

```bash
python3 docs/roadmap/suivi.py tache v7-effets-visuels <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v7-effets-visuels --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v7-effets-visuels <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v7-effets-visuels: …" && git push -u origin roadmap/v7-effets-visuels
bash scripts/ouvrir-pr.sh roadmap/v7-effets-visuels   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

