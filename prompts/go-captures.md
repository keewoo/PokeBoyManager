# Lot `go-captures` — Pokémon GO : lire les captures d'écran et proposer les Pokémon à ajouter

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P1** · piste Collection & fiche carte · couloir **CH2** — IA & vision (**chimera**) · prévu du 12 oct. au 16 oct. · jalon **MVP en UAT** · taille M · complexité 3/5 · difficulté 3/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier go-captures`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-go-captures -b roadmap/go-captures origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/go-captures.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/go-captures` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-go-captures`, branche `roadmap/go-captures` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier go-captures
python3 docs/roadmap/suivi.py demarrer go-captures --machine "$(hostname -s)" --branche roadmap/go-captures
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut go-captures attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — go-captures — <raisons>`.
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

## 1 bis. Le dépôt est graphifié — interroge le graphe avant de lire dix fichiers

Le code, la documentation et les schémas de ce dépôt sont indexés par **Graphify**. Dans ton worktree, `graphify-out/` n'existe pas encore (il n'est pas versionné) : construis-le, puis pose tes questions au graphe.

```bash
export PATH=$HOME/.local/bin:$PATH   # sur la flotte, graphify vit là
graphify update .                     # ~5-25 s, sans LLM
graphify query "<ta question>"      # qui appelle quoi, où vit telle règle
graphify explain "<symbole>"        # un nœud et ses voisins
graphify affected "<symbole>"       # ce qui dépend de ce que tu vas modifier
```

Si le serveur MCP `graphify` est chargé dans ta session, `query_graph`, `get_neighbors` et `shortest_path` font la même chose. Le graphe **oriente**, il ne prouve pas : ouvre le fichier réel avant d'affirmer qu'une ligne existe. Mode d'emploi : `docs/CODE.md` § « Chercher dans le dépôt ».

## 2. Contexte

**Gain.** Les captures d'écran de la fiche d'un Pokémon dans Pokémon GO deviennent des propositions d'ajout à la collection, shiny repéré — sans ressaisie.

**Fonctionnalités.** Case à cocher « Pokémon GO » dans le profil (désactivée par défaut ; tant qu'elle l'est, rien de la fonctionnalité n'apparaît). Sélection de plusieurs captures depuis la bibliothèque d'images du téléphone. Reconnaissance par l'IA **du joueur** (sa clé, un appel par capture) : espèce, forme, shiny, et ce qui est lisible (PC, attaques). Écran de validation avant ajout, comme pour les photos de cartes : chaque capture propose la carte de référence de son espèce (D16), le joueur confirme, corrige ou écarte.

**Tenants — ce qu'il faut avant.** Comptes, coffre de clés IA, reconnaissance (pipeline photo), catalogue ; D16.

**Aboutissants — ce que ça ouvre.** Captures Pokémon GO jouables en deck (go-collection-jeu).

**Dépend de :**
- `v3-validation` — Écran de validation : vérifier, corriger et ajouter les cartes reconnues
- `v1-byok` — Coffre de clés IA : Claude, Gemini ou OpenAI par utilisateur

**Décision D16** (avant le 9 oct.) : Pokémon GO : à quelle carte correspond un Pokémon capturé, et ce qu'on peut en faire. Proposition : une capture devient un exemplaire « Pokémon GO » d'une carte de référence de son espèce — l'impression de la série TCG « Pokémon GO » (2022) si elle existe, sinon l'impression de base jouable la plus récente ; shiny → badge « chromatique » ; valeur de collection 0 (exclue de la valeur, des classements et des statistiques de valeur) ; utilisable en deck et en partie seulement (ni échange, ni export comme carte réelle) ; une case à cocher dans le profil, désactivée par défaut, pensée pour devenir payante. À confirmer par JF, ainsi que ce qu'on fait d'une espèce sans aucune carte jouable. — lis la décision prise dans `etat.json` (`decisions_prises`) et applique-la à la lettre.

## 3. Mission

1. Drapeau par compte `pokemon_go_enabled` (profil, case à cocher, faux par défaut), et un point d'accroche unique pour le rendre payant plus tard (sans facturation dans ce lot).
2. Envoi de plusieurs captures depuis la bibliothèque d'images ; stockage comme les photos (D7), jamais servi à un autre compte.
3. Reconnaissance par l'IA du joueur (un appel par capture, prompt et schéma de réponse versionnés) : espèce, forme, shiny ; échec ou réponse illisible → la capture reste « à vérifier », jamais un ajout deviné.
4. Correspondance espèce → carte de référence selon D16, testée sur un jeu de captures réelles (anonymisées).
5. Écran de validation : confirmer, corriger l'espèce, écarter ; test d'accès croisé ; aucun ajout sans geste du joueur.

## 4. Risques & pièges

Prendre une capture pour une carte réelle : un exemplaire Pokémon GO n'a pas de valeur et ne s'échange pas — la frontière doit être visible partout (badge, filtre, exclusion des valeurs). Et l'IA qui invente une espèce : on propose, le joueur valide, jamais d'ajout automatique.

## 5. Livrables — définition de « fini »

- case à cocher Pokémon GO
- envoi et reconnaissance des captures
- écran de validation
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Aucun secret dans le dépôt, les journaux ou les sorties.
- **Code documenté** : chaque module, fonction et classe publique ajouté ou modifié a sa docstring (Python) ou son `/** … */` (TypeScript), en français, qui dit le pourquoi — `docs/CODE.md` § « Documenter le code ».
- **Graphe à jour** : après la fusion dans `main`, `graphify update .` sur le clone qui suit `main` (un graphe en retard fait mentir les lots suivants).

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
python3 docs/roadmap/suivi.py tache go-captures <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu go-captures --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut go-captures <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "go-captures: …" && git push -u origin roadmap/go-captures
bash scripts/ouvrir-pr.sh roadmap/go-captures   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

