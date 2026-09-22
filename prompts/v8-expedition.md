# Lot `v8-expedition` — Envoyer, suivre, recevoir

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Échanges entre collectionneurs · couloir **DA4** — Échanges — règles, transfert & argent (**devAI**) · prévu du 1 févr. au 5 févr. · jalon **En ligne** · taille L · complexité 3/5 · difficulté 3/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v8-expedition`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v8-expedition -b roadmap/v8-expedition origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-v8-expedition && nohup claude -p --dangerously-skip-permissions < prompts/v8-expedition.md > ~/dev/logs/v8-expedition.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v8-expedition` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-v8-expedition`, branche `roadmap/v8-expedition` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v8-expedition
python3 docs/roadmap/suivi.py demarrer v8-expedition --machine "$(hostname -s)" --branche roadmap/v8-expedition
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v8-expedition attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v8-expedition — <raisons>`.
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

**Gain.** Entre l'acceptation et la réception il y a la poste : c'est là que les échanges meurent, par oubli bien plus souvent que par malveillance.

**Fonctionnalités.** Étapes obligatoires — envoyé (avec numéro de suivi), reçu, validé ; photo de l'emballage avant fermeture, horodatée ; relances automatiques à J+2 et J+5 ; délai au-delà duquel l'échange bascule en litige ; étiquette générée par PokeBoy quand le mode le prévoit, pour que l'adresse ne soit jamais affichée à personne.

**Tenants — ce qu'il faut avant.** Offre acceptée, adresses, transporteur.

**Aboutissants — ce que ça ouvre.** Litiges (le dossier se constitue ici), transfert, réputation.

**Dépend de :**
- `v8-transfert` — La carte change de mains, et l'appli le sait

**Décision D14** (avant le 22 janv.) : Expédition : transporteur, seuil de valeur au-dessus duquel le suivi est obligatoire, qui paie le port, quelle assurance. Proposition : l'adresse n'est jamais affichée — c'est l'étiquette générée qui la porte ; suivi obligatoire au-delà de 30 € de valeur figée ; port à la charge de chaque expéditeur ; aucune assurance promise tant qu'aucune n'est souscrite. — lis la décision prise dans `etat.json` (`decisions_prises`) et applique-la à la lettre.

## 3. Mission

1. Étapes et délais côté serveur, relances par e-mail et notification, bascule automatique en litige.
2. Photo d'emballage horodatée, conservée pour la durée de contestation puis purgée.
3. Adresse postale jamais exposée dans l'interface ni dans une API : seule l'étiquette la porte.
4. Tests : envoi d'un seul côté puis silence, réception sans validation, dépassement de délai, numéro de suivi invalide.

## 4. Risques & pièges

Suivi obligatoire au-delà du seuil fixé en D15 ; en-dessous, l'envoi simple reste possible mais l'utilisateur est prévenu, noir sur blanc, qu'il ne pourra rien prouver. Ne jamais afficher le mot « assuré » tant qu'aucune assurance n'est souscrite. Les relances sont l'essentiel du gain : un échange oublié est un échange perdu.

## 5. Livrables — définition de « fini »

- étapes, relances et délais testés
- aucune adresse exposée (vérifié dans les réponses API)
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
python3 docs/roadmap/suivi.py tache v8-expedition <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v8-expedition --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v8-expedition <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v8-expedition: …" && git push -u origin roadmap/v8-expedition
bash scripts/ouvrir-pr.sh roadmap/v8-expedition   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

