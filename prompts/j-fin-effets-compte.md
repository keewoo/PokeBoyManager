# Lot `j-fin-effets-compte` — Ce qu'une partie laisse sur le compte : écriture unique et exacte

> Prompt GÉNÉRÉ depuis `docs/roadmap/jeu/plan/` (via `jeu.json`) par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Plan du jeu : `docs/roadmap/jeu/BACKLOG-JEU.md` · onglet « Backlog du jeu » de `docs/roadmap/ROADMAP.html`.

**P0** · piste Compte & progression · couloir **J-SRV** (**chimera**) · jalon **J4 — La partie laisse une trace** · palier 13 · taille M · complexité 3/5 · difficulté 4/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier j-fin-effets-compte`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-j-fin-effets-compte -b roadmap/j-fin-effets-compte origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/j-fin-effets-compte.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/j-fin-effets-compte` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 8 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-j-fin-effets-compte`, branche `roadmap/j-fin-effets-compte` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier j-fin-effets-compte
python3 docs/roadmap/suivi.py demarrer j-fin-effets-compte --machine "$(hostname -s)" --branche roadmap/j-fin-effets-compte
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut j-fin-effets-compte attente_validation --motif "<raisons>"`, section 8, dernier message `ATTENTE VALIDATION — j-fin-effets-compte — <raisons>`.
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

**Jalon J4 — La partie laisse une trace.** La fin de partie écrit sur le compte : historique, statistiques par deck, classement privé entre comptes invités, badges. On revient parce qu'il y a quelque chose à suivre.

**Principes du jeu — ils valent pour ce lot comme pour tous les autres :**

- **Le serveur fait autorité.** Le client n'est qu'un écran : il n'apprend jamais la main de l'adversaire ni l'ordre de la pioche, et toute action qu'il propose est rejouée et validée côté serveur.
- **Un effet non implémenté n'est jamais approximé** (D9). Une carte dont l'effet n'est pas scripté et testé est refusée à la construction du deck, en disant pourquoi. Le jeu préfère dire « je ne sais pas jouer cette carte » que de la jouer de travers.
- **Tout est rejouable.** Une partie est un état initial, une graine d'aléatoire et un journal d'actions numéroté. Rejouer le journal doit redonner exactement le même état — c'est ce qui fait tenir la reprise après un F5, le replay, le support et l'anti-triche.
- **Le moteur ne connaît ni HTTP ni React.** Fonctions pures, état sérialisable, aucune entrée/sortie : c'est la seule façon de le tester par milliers de cas et de le faire jouer par des bots.
- **L'interface ne décide de rien.** Elle affiche les actions que le moteur déclare légales, et affiche la raison quand un coup est refusé. Aucune règle n'est réécrite côté écran.
- **Le jeu est celui d'un enfant de onze ans.** Lisible sans connaître les règles, animé, sonore, indulgent : on peut annuler avant de valider, on comprend pourquoi un coup est interdit, et on n'attend jamais devant un écran muet.

**Gain.** C'est la demande de JF (« la fin de jeu, avec ses effets sur le compte joueur »). Le piège est technique : une partie peut se terminer deux fois — reprise, rejeu, double événement — et doubler les victoires.

**Fonctionnalités.** À la clôture d'une partie : écriture de son résultat (vainqueur, raison, durée, tours), mise à jour des compteurs du joueur (parties, victoires, défaites, série en cours et meilleure série, temps de jeu), statistiques par deck et par adversaire, attribution des badges, mise à jour du classement privé si activé. Le tout en une transaction idempotente, déclenchée par un événement de fin unique.

**Vient après :**
- `j-ko-recompenses` — Mises K.O., récompenses et conditions de victoire
- `j-deconnexion-abandon` — Déconnexion, abandon, désertion : une partie ne reste jamais suspendue

**Débloque :**
- `j-classement-prive` — Classement privé entre comptes invités
- `j-mise-en-ligne-jeu` — Mettre le jeu en ligne sur le serveur partagé
- `j-stats-joueur` — Mes parties : historique, statistiques et ce que ça dit de mes decks

**Décision DJ6** — Que laisse une partie sur le compte : un simple historique, ou une progression (points, saisons, badges) ? Lis la décision prise dans `docs/roadmap/etat.json` (`decisions_prises.DJ6`) et applique-la à la lettre ; la proposition du pilote n'est qu'un contexte : _Historique et statistiques d'office ; classement privé et badges en option, activables par JF, sans saison ni perte de points._

## 3. Mission

1. Poser une clé d'idempotence sur la partie : deux clôtures ne produisent qu'une écriture (contrainte en base, pas un `if`).
2. Recalculer les statistiques de fin depuis le journal, jamais depuis des compteurs tenus pendant la partie.
3. Traiter les fins anormales (abandon, désertion, temps) avec le même chemin d'écriture.
4. Prévoir la reprise après panne : une partie close dont l'écriture a échoué est reprise par un balayage, et le signale.
5. Tests : clôture rejouée deux fois, clôture pendant une reprise, clôture d'une partie d'entraînement (aucun effet de classement).

## 4. Critères d'acceptation

Le lot n'est fini que si **chacun** est vrai, preuve à l'appui dans le compte rendu :

- [ ] Rejouer la clôture d'une partie ne modifie rien la deuxième fois (test explicite).
- [ ] Les statistiques recalculées depuis le journal correspondent à la partie jouée.
- [ ] Une partie d'entraînement contre le bot n'affecte ni classement ni série.

## 5. Risques & pièges

Compter les victoires au fil de l'eau : c'est la panne muette classique — personne ne remarque un compteur faux avant que quelqu'un ne compte.

## 6. Livrables — définition de « fini »

- clôture idempotente
- statistiques recalculées depuis le journal
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Compte rendu `docs/roadmap/comptes-rendus/j-fin-effets-compte.md` : résumé, livrables, preuves, écarts, reste à faire.
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
python3 docs/roadmap/suivi.py tache j-fin-effets-compte <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu j-fin-effets-compte --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut j-fin-effets-compte <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "j-fin-effets-compte: …" && git push -u origin roadmap/j-fin-effets-compte
bash scripts/ouvrir-pr.sh roadmap/j-fin-effets-compte   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

