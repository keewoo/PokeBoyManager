# Lot `v7-plateau` — Plateau de jeu graphique

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Jeu — decks et parties · couloir **CH4** — Front — photos, validation & fiche carte (**chimera**) · prévu du 22 févr. au 5 mars · jalon **En ligne** · taille L · complexité 4/5 · difficulté 3/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v7-plateau`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v7-plateau -b roadmap/v7-plateau origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/v7-plateau.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v7-plateau` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-v7-plateau`, branche `roadmap/v7-plateau` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v7-plateau
python3 docs/roadmap/suivi.py demarrer v7-plateau --machine "$(hostname -s)" --branche roadmap/v7-plateau
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v7-plateau attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v7-plateau — <raisons>`.
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

**Gain.** C'est ce que le joueur voit : un plateau lisible, avec ses vraies cartes.

**Fonctionnalités.** Plateau 16/9 conçu en 1920×1080 avec une zone utile centrale de 1500×900 ; carte de référence 126×176, actif 145×203, banc 105×147 (5 emplacements, 12-16 d'écart), actif adverse 110×154, pioche/défausse/récompenses 75×105, badge PV 70×28, marqueurs de dégâts 22-26 ; main en éventail, glisser-déposer, mise en évidence des actions possibles, adaptatif mobile.

**Tenants — ce qu'il faut avant.** Temps réel, images jouables, design system.

**Aboutissants — ce que ça ouvre.** Déroulé de la partie.

**Dépend de :**
- `v7-temps-reel` — Temps réel et reprise après F5
- `v7-images-jeu` — Cartes jouables : ma photo ou l'image officielle

## 3. Mission

1. Plateau à l'échelle : toutes les tailles dérivent d'une seule unité (largeur du plateau / 120), d'après le tableau de dimensions de la maquette — rien à recalculer quand la fenêtre change.
2. Structure verticale imposée : décor 8 % en haut, actif adverse, pioche et défausse adverses, ligne centrale, mon actif, mon banc de 5, mes récompenses et ma pioche, décor 8 % en bas ; la main reste sous le plateau.
3. Glisser-déposer des cartes de la main vers le banc, énergie sur un Pokémon, sélection d'une attaque ; les actions illégales ne sont même pas proposées.
4. Rendu à partir de la seule vue serveur ; rafraîchir la page redonne le même plateau.

## 4. Risques & pièges

**Les emplacements ne sont jamais dessinés dans le décor** (règle posée par JF le 20/09) : le fond ne fournit que l'arène, la ligne médiane, l'ambiance et les gradins, avec un centre mat et peu contrasté et les effets lumineux cantonnés aux 15-20 % périphériques ; tout emplacement est produit en HTML/CSS par-dessus, sinon la moindre évolution (taille du deck, nombre de cartes au banc, disposition mobile) casse l'image. Lisibilité sur téléphone : plateau compact, zoom au toucher long. Aucune information cachée dans le DOM (la main adverse n'est jamais envoyée).

## 5. Livrables — définition de « fini »

- plateau jouable sur ordinateur et téléphone
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
python3 docs/roadmap/suivi.py tache v7-plateau <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v7-plateau --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v7-plateau <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v7-plateau: …" && git push -u origin roadmap/v7-plateau
bash scripts/ouvrir-pr.sh roadmap/v7-plateau   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

