# Lot `v8-offre` — Proposer, contre-proposer, accepter

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Échanges entre collectionneurs · couloir **DA4** — Échanges — règles, transfert & argent (**devAI**) · prévu du 18 janv. au 22 janv. · jalon **En ligne** · taille L · complexité 4/5 · difficulté 4/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v8-offre`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v8-offre -b roadmap/v8-offre origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-v8-offre && nohup claude -p --dangerously-skip-permissions < prompts/v8-offre.md > ~/dev/logs/v8-offre.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v8-offre` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-v8-offre`, branche `roadmap/v8-offre` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v8-offre
python3 docs/roadmap/suivi.py demarrer v8-offre --machine "$(hostname -s)" --branche roadmap/v8-offre
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v8-offre attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v8-offre — <raisons>`.
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

**Gain.** Le cœur de la vague : un échange est un engagement entre deux personnes. Il doit avoir un état, une trace et une fin — y compris quand il n'aboutit pas.

**Fonctionnalités.** Offre de N cartes contre M cartes ; balance de valeur affichée des deux côtés ; contre-offre ; expiration automatique à 7 jours ; états acceptée, refusée, expirée, annulée ; gel des exemplaires engagés ; le mode de règlement (direct, garant, dépôt) est un ATTRIBUT de l'offre, pas une branche de code.

**Tenants — ce qu'il faut avant.** Appariement, prix, exemplaires réservés.

**Aboutissants — ce que ça ouvre.** Expédition, transfert, litiges, réputation : tout pend à cette machine à états.

**Dépend de :**
- `v8-appariement` — Le moteur d'appariement : mes doublons contre tes souhaits

**Décision D12** (avant le 14 déc.) : Mécanique d'échange retenue pour la v1, parmi les trois proposées par JF : (1) en direct entre collectionneurs, PokeBoy ne fait que mettre en relation ; (2) PokeBoy intermédiaire physique — étiquettes vers PokeBoy, contrôle, réexpédition, frais fixes ; (3) PokeBoy garant — chacun verse une caution proportionnelle à la valeur, restituée à la double validation, commission retenue. Proposition : (1) d'abord, seule livrable sans argent ni stock et seule ouverte aux mineurs ; (3) ensuite, si le taux de litige mesuré le justifie ; (2) jamais sans volume — voir v8-hub-etude. — lis la décision prise dans `etat.json` (`decisions_prises`) et applique-la à la lettre.

## 3. Mission

1. Machine à états de l'offre, transitions contrôlées côté serveur, journal d'audit horodaté et immuable.
2. Valeurs figées et archivées au moment de l'acceptation, avec leur source et leur date.
3. Mode de règlement porté par l'offre, avec un seul mode actif en v1 et les autres refusés explicitement.
4. Expiration et annulation : les exemplaires engagés redeviennent disponibles, les deux parties sont prévenues.
5. Tests : contre-offres en cascade, acceptation simultanée des deux côtés, expiration pendant une contre-offre, annulation après acceptation.

## 4. Risques & pièges

Les valeurs bougent entre la proposition et l'acceptation : on les FIGE à l'acceptation et on les archive avec l'offre — sinon un litige se juge sur des prix qui n'existent plus. Une offre acceptée n'est pas un transfert : la carte ne change de mains qu'à la réception validée (v8-transfert). Le mode est enfichable dès maintenant, même si un seul est livré : c'est ce qui évitera de réécrire la machine à états le jour où JF tranche autrement.

## 5. Livrables — définition de « fini »

- machine à états complète et testée
- valeurs figées, journal d'audit consultable
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
python3 docs/roadmap/suivi.py tache v8-offre <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v8-offre --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v8-offre <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v8-offre: …" && git push -u origin roadmap/v8-offre
bash scripts/ouvrir-pr.sh roadmap/v8-offre   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

