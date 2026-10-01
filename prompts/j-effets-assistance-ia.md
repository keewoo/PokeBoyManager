# Lot `j-effets-assistance-ia` — Assistance IA : proposer le script d'une carte, jamais le valider seule

> Prompt GÉNÉRÉ depuis `docs/roadmap/jeu/plan/` (via `jeu.json`) par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Plan du jeu : `docs/roadmap/jeu/BACKLOG-JEU.md` · onglet « Backlog du jeu » de `docs/roadmap/ROADMAP.html`.

**P1** · piste Effets & cartes · couloir **J-EFF** (**chimera**) · jalon **J2 — Toutes les cartes du deck sont vraiment jouées** · palier 11 · taille M · complexité 4/5 · difficulté 4/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier j-effets-assistance-ia`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-j-effets-assistance-ia -b roadmap/j-effets-assistance-ia origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/j-effets-assistance-ia.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/j-effets-assistance-ia` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 8 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-j-effets-assistance-ia`, branche `roadmap/j-effets-assistance-ia` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier j-effets-assistance-ia
python3 docs/roadmap/suivi.py demarrer j-effets-assistance-ia --machine "$(hostname -s)" --branche roadmap/j-effets-assistance-ia
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut j-effets-assistance-ia attente_validation --motif "<raisons>"`, section 8, dernier message `ATTENTE VALIDATION — j-effets-assistance-ia — <raisons>`.
- Tu n'accordes **jamais** toi-même une dérogation.

## 1. Cadre — relire avant d'agir

| Document | Pourquoi |
|---|---|
| `CLAUDE.md` | règles du dépôt, carte des fiches, « où écrire quoi » |
| `docs/CODE.md` | structure du monorepo, commandes, tests, définition du « fini » |
| `docs/roadmap/jeu/BACKLOG-JEU.md` | le plan du jeu : principes, jalons, décisions `DJ*`, fiches des 67 lots |
| `docs/jeu/REGLES.md` | le corpus de règles qui fait foi (créé par `j-regles-reference`) : tout test de règle cite son identifiant `R-x.y` |
| `docs/ARCHITECTURE.md` | données, catalogue, decks — ce que le jeu consomme |
| `~/.claude/CLAUDE.md` de la machine | règles de la flotte (construire ≠ servir, Python 3.12, WSL) |

Le cadre l'emporte sur ce prompt : en cas de contradiction, passe en `attente_validation` avec la contradiction en motif.

## 2. Contexte

**Jalon J2 — Toutes les cartes du deck sont vraiment jouées.** Objets, Supporters, Stades, Outils, talents, états spéciaux, appâts, attaques à effet, énergies spéciales : ce que la carte dit, le moteur le fait. Et ce qu'il ne sait pas faire, il le refuse au deck au lieu de l'inventer.

**Principes du jeu — ils valent pour ce lot comme pour tous les autres :**

- **Le serveur fait autorité.** Le client n'est qu'un écran : il n'apprend jamais la main de l'adversaire ni l'ordre de la pioche, et toute action qu'il propose est rejouée et validée côté serveur.
- **Un effet non implémenté n'est jamais approximé** (D9). Une carte dont l'effet n'est pas scripté et testé est refusée à la construction du deck, en disant pourquoi. Le jeu préfère dire « je ne sais pas jouer cette carte » que de la jouer de travers.
- **Tout est rejouable.** Une partie est un état initial, une graine d'aléatoire et un journal d'actions numéroté. Rejouer le journal doit redonner exactement le même état — c'est ce qui fait tenir la reprise après un F5, le replay, le support et l'anti-triche.
- **Le moteur ne connaît ni HTTP ni React.** Fonctions pures, état sérialisable, aucune entrée/sortie : c'est la seule façon de le tester par milliers de cas et de le faire jouer par des bots.
- **L'interface ne décide de rien.** Elle affiche les actions que le moteur déclare légales, et affiche la raison quand un coup est refusé. Aucune règle n'est réécrite côté écran.
- **Le jeu est celui d'un enfant de onze ans.** Lisible sans connaître les règles, animé, sonore, indulgent : on peut annuler avant de valider, on comprend pourquoi un coup est interdit, et on n'attend jamais devant un écran muet.

**Gain.** Écrire des milliers de scripts à la main n'arrivera jamais au bout. L'IA du projet sait lire un texte de carte et proposer un script — à condition que rien n'entre en jeu sans être testé.

**Fonctionnalités.** Un passage par lots : pour chaque carte non scriptée, l'IA propose un script dans le langage, ET les cas de test qui le vérifient, ET son niveau de confiance. Le script n'est activé que si ses tests passent et qu'un humain a validé la famille. Budget plafonné, journalisation des coûts, reprise après interruption — comme `v4-insights-batch`.

**Vient après :**
- `j-effets-catalogue-compilation` — Du catalogue aux cartes jouables : compilation, versions et errata

**Débloque :**
- aucun lot n'en dépend

**Décision DJ8** — Jusqu'où l'IA écrit-elle les scripts de cartes, et sous quel contrôle ? Lis la décision prise dans `docs/roadmap/etat.json` (`decisions_prises.DJ8`) et applique-la à la lettre ; la proposition du pilote n'est qu'un contexte : _L'IA propose un script ET ses cas de test à partir du texte de la carte ; le script n'entre en jeu que si ses tests passent et qu'un humain a validé la famille d'effets. Budget plafonné, comme pour v4-insights-batch._

## 3. Mission

1. Écrire le gabarit de requête : texte de la carte (FR et EN), schéma du langage, exemples validés proches, contraintes de sortie strictes.
2. Exécuter les tests proposés ET une batterie de tests de cohérence maison (l'effet ne crée ni ne détruit de cartes, l'état reste valide).
3. Mettre en file de relecture humaine par famille d'effet, pas carte par carte.
4. Plafonner le budget, journaliser le coût par carte, reprendre après interruption sans reprendre les cartes déjà traitées.
5. Mesurer : part des propositions acceptées sans retouche, part rejetée, coût par carte validée.

## 4. Critères d'acceptation

Le lot n'est fini que si **chacun** est vrai, preuve à l'appui dans le compte rendu :

- [ ] Aucun script n'entre en jeu sans tests verts ET validation humaine de sa famille — vérifié par une contrainte en base, pas par une consigne.
- [ ] Le budget plafonné est respecté et le coût par carte validée est publié.
- [ ] Une interruption au milieu d'un lot ne perd rien et ne retraite rien.

## 5. Risques & pièges

Un script plausible mais faux est plus dangereux qu'une carte non supportée : il fait perdre des parties sans que personne ne comprenne. Les tests de cohérence maison sont le vrai garde-fou, pas la confiance annoncée par le modèle.

## 6. Livrables — définition de « fini »

- passage par lots IA → scripts + tests
- file de relecture par famille
- mesures de rendement
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Compte rendu `docs/roadmap/comptes-rendus/j-effets-assistance-ia.md` : résumé, livrables, preuves, écarts, reste à faire.
- Le savoir durable va dans **une** fiche (« Où écrire quoi » de `CLAUDE.md`) ; pour le jeu, `docs/jeu/`.
- Aucun secret dans le dépôt, les journaux ou les sorties.

## 7. Tests exigés

- Un test qui **échoue sans** ton changement et passe avec.
- Moteur : fonctions pures, aucune entrée/sortie — un test d'import le prouve ; chaque test de règle cite son `R-x.y`.
- Route utilisateur → test d'accès croisé (l'utilisateur B reçoit 404 sur les objets de A).
- Écran → conforme à l'onglet « Maquette du jeu » (capture jointe au compte rendu).
- Suites complètes lancées sur la flotte, jamais sur le Mac de JF.

## 8. Clôture — obligatoire

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
python3 docs/roadmap/suivi.py tache j-effets-assistance-ia <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu j-effets-assistance-ia --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut j-effets-assistance-ia <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "j-effets-assistance-ia: …" && git push -u origin roadmap/j-effets-assistance-ia
bash scripts/ouvrir-pr.sh roadmap/j-effets-assistance-ia   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

