# Lot `v2-catalogue-complet` — Base de référence complète : toutes les cartes, toutes leurs infos, tous les prix — avant la première photo

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P0** · piste Catalogue & prix · couloir **CH3** — Catalogue, prix & e2e (**chimera**) · prévu du 12 oct. au 14 oct. · jalon **MVP en UAT** · taille M · complexité 3/5 · difficulté 3/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur chimera**. Lance `hostname -s` :

- **Chimaera (dans la WSL)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v2-catalogue-complet`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur chimera :

```bash
ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc "cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v2-catalogue-complet -b roadmap/v2-catalogue-complet origin/main && mkdir -p ~/dev/logs"'
```

3. Lance le lot autonome : par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/v2-catalogue-complet.log`.
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v2-catalogue-complet` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)`. Travaille dans ton **worktree** `../wt-v2-catalogue-complet`, branche `roadmap/v2-catalogue-complet` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v2-catalogue-complet
python3 docs/roadmap/suivi.py demarrer v2-catalogue-complet --machine "$(hostname -s)" --branche roadmap/v2-catalogue-complet
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v2-catalogue-complet attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v2-catalogue-complet — <raisons>`.
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

**Gain.** Principe posé par JF le 19/09 : tout ce qui est connu d'une carte vit dans NOTRE base, dès le départ. L'IA ne sert plus qu'à identifier la carte et estimer son état ; une carte déjà connue ne recoûte rien.

**Fonctionnalités.** Import complet FR + EN de toutes les extensions (extension, numéro, rareté, type, PV, illustrateur, attaques, talents, faiblesses, résistances, retraite, légalités, dates de sortie, URL d'images officielles, correspondance Pokémon TCG API) ; premier relevé de prix de TOUTES les cartes, puis relevé quotidien de toutes ; rapport de complétude ; « graine » du catalogue réutilisable pour chaque base (dev, UAT, PROD).

**Tenants — ce qu'il faut avant.** Import du catalogue (échantillon), relevé des prix, recherche.

**Aboutissants — ce que ça ouvre.** Identification (rapprochement sur une base complète), fiche carte instantanée, déploiement (la PROD démarre avec toutes les cartes et leurs prix).

**Dépend de :**
- `v2-prix` — Relevé quotidien des prix et historique de valeur
- `v2-recherche` — Recherche dans le catalogue (nom, numéro, extension)

## 3. Mission

1. Compléter l'import pour qu'une carte porte TOUT ce que la fiche affiche sans IA : faiblesses, résistances, coût de retraite, règles (ex/V/VMAX…), date de sortie de l'extension, logo et symbole d'extension, variantes existantes (normale, reverse, holo…) — migrations additives si besoin.
2. Lancer l'import COMPLET FR + EN dans une base de référence `pbm_catalogue_ref` (infra partagée) ; mesurer la durée ; reprendre les extensions en échec jusqu'à zéro échec ou échecs expliqués.
3. Lancer le relevé de prix sur TOUTES les cartes de cette base ; mesurer durée et nombre d'appels ; ajuster le parallélisme pour tenir largement dans la nuit en PROD.
4. Rapport de complétude `docs/catalogue/COMPLETUDE.md` : nombre d'extensions et de cartes par langue, % avec image, % avec `ptcg_id`, % avec au moins un prix, extensions non rapprochées, et la liste des trous restants.
5. Graine réutilisable : script `apps/api/scripts/catalogue_seed.sh export|import <DATABASE_URL>` (dump/restauration des seules tables du catalogue et des prix, idempotent) ; archive produite et rangée hors dépôt (`~/dev/pbm-artefacts/catalogue-<date>.dump` sur chimera) ; le déploiement l'utilisera pour peupler l'UAT et la PROD.
6. Tests : complétude minimale (seuils) sur un échantillon, idempotence de l'import complet, restauration de la graine dans une base vide.

## 4. Risques & pièges

Volume (~20 000 cartes × 2 langues) sur le lien lent de chimera : import par extension, reprise, et mesure de la durée ; APIs tierces instables (500/502 déjà vus) : reprise sans perte ; ne jamais annoncer « complet » sans le rapport de complétude.

## 5. Livrables — définition de « fini »

- rapport de complétude chiffré
- graine du catalogue + script d'import/export
- durées mesurées de l'import complet et du relevé de prix complet
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
- `securite` — Contrôle sécurité (isolation, secrets) (sans objet : données publiques)
- `maquette` — Conforme à la maquette (sans objet : back-end)
- `doc_tech` — Doc technique (CLAUDE.md, docs/)
- `release_uat` — Livré en UAT (preuve) (sans objet : appliqué par le déploiement)
- `release_prod` — Livré en PROD (preuve) (sans objet : appliqué par le déploiement)
- `backlog` — BACKLOG.md et état à jour
- `compte_rendu` — Compte rendu dans le suivi

```bash
python3 docs/roadmap/suivi.py tache v2-catalogue-complet <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v2-catalogue-complet --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v2-catalogue-complet <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v2-catalogue-complet: …" && git push -u origin roadmap/v2-catalogue-complet && gh pr create --fill
```

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

