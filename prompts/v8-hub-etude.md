# Lot `v8-hub-etude` — Centre de tri PokeBoy : l'étude avant la moindre ligne de code (conditionnel)

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P3** · piste Échanges entre collectionneurs · couloir **CH6** — Échanges — écrans, appariement & messagerie (**chimera**) · prévu du 1 mars au 5 mars · jalon **En ligne** · taille S · complexité 1/5 · difficulté 2/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v8-hub-etude`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v8-hub-etude -b roadmap/v8-hub-etude origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/v8-hub-etude.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v8-hub-etude` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-v8-hub-etude`, branche `roadmap/v8-hub-etude` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v8-hub-etude
python3 docs/roadmap/suivi.py demarrer v8-hub-etude --machine "$(hostname -s)" --branche roadmap/v8-hub-etude
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v8-hub-etude attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v8-hub-etude — <raisons>`.
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

**Gain.** La mécanique la plus protectrice — PokeBoy reçoit les deux cartes puis les redistribue — est aussi la seule qui soit un métier et non une fonctionnalité. On la chiffre avant de s'y engager.

**Fonctionnalités.** Étude chiffrée : coût réel d'un aller-retour suivi et assuré, seuil de valeur au-dessous duquel les frais dépassent la carte, volume mensuel nécessaire pour couvrir local, assurance et manutention, délai ajouté par le double trajet, traitement du cas « la carte reçue n'est pas celle annoncée », responsabilité en cas de perte ou d'incendie, et ce que rapporterait le contrôle d'authenticité et d'état — la seule partie qui soit déjà à nous (v6-contrefacon, v3-etat).

**Tenants — ce qu'il faut avant.** Litiges, expédition, contrôle d'authenticité.

**Aboutissants — ce que ça ouvre.** Entrée de la décision D12 pour la suite.

**Dépend de :**
- `v8-litiges` — Quand ça se passe mal

**Décision D12** (avant le 14 déc.) : Mécanique d'échange retenue pour la v1, parmi les trois proposées par JF : (1) en direct entre collectionneurs, PokeBoy ne fait que mettre en relation ; (2) PokeBoy intermédiaire physique — étiquettes vers PokeBoy, contrôle, réexpédition, frais fixes ; (3) PokeBoy garant — chacun verse une caution proportionnelle à la valeur, restituée à la double validation, commission retenue. Proposition : (1) d'abord, seule livrable sans argent ni stock et seule ouverte aux mineurs ; (3) ensuite, si le taux de litige mesuré le justifie ; (2) jamais sans volume — voir v8-hub-etude. — lis la décision prise dans `etat.json` (`decisions_prises`) et applique-la à la lettre.

## 3. Mission

1. Chiffrer les trois postes : port aller-retour suivi, assurance des biens détenus, manutention.
2. Déterminer le seuil de valeur de carte et le volume mensuel à partir desquels le modèle tient.
3. Décrire le parcours complet côté utilisateur et côté opérateur, délais compris, sans le coder.
4. Conclure par une recommandation chiffrée : ouvrir, différer, abandonner.

## 4. Risques & pièges

Le piège est de coder d'abord : l'étiquette prépayée et le tableau de réception se font en trois jours, le reste est de la logistique. La conclusion attendue est un CHIFFRE et une recommandation — ouvrir, différer ou abandonner — pas une opinion. Une étude qui conclut « ne pas ouvrir » est un succès du lot.

## 5. Livrables — définition de « fini »

- note chiffrée avec seuil de volume et grille de frais
- recommandation explicite, même négative
- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).
- Aucun secret dans le dépôt, les journaux ou les sorties.

## 6. Tests exigés

- Un test qui **échoue sans** ton changement et passe avec.
- Route utilisateur → test d'accès croisé (l'utilisateur B reçoit 404 sur les objets de A).
- Front → conformité à l'écran de la maquette (capture jointe au compte rendu).
- Suites complètes lancées sur la flotte (`fleet-run` depuis le Mac, ou directement sur la machine), jamais sur le Mac de JF.

## 7. Clôture — obligatoire

Grille de tâches du lot :
- `dev` — Développement (sans objet : étude, aucun code produit)
- `tests` — Tests (unitaires, API, e2e) (sans objet : étude, aucun code produit)
- `securite` — Contrôle sécurité (isolation, secrets) (sans objet : étude, aucun code produit)
- `maquette` — Conforme à la maquette (sans objet : étude, aucun écran produit)
- `doc_tech` — Doc technique (CLAUDE.md, docs/)
- `release_uat` — Recette locale sur chimera
- `release_prod` — Livré en PROD (preuve)
- `backlog` — BACKLOG.md et état à jour
- `compte_rendu` — Compte rendu dans le suivi

```bash
python3 docs/roadmap/suivi.py tache v8-hub-etude <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v8-hub-etude --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v8-hub-etude <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v8-hub-etude: …" && git push -u origin roadmap/v8-hub-etude
bash scripts/ouvrir-pr.sh roadmap/v8-hub-etude   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

