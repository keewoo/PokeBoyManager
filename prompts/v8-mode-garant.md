# Lot `v8-mode-garant` — Mode garant : caution restituée et commission (conditionnel)

> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.
> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.

**P2** · piste Échanges entre collectionneurs · couloir **DA4** — Échanges — règles, transfert & argent (**devAI**) · prévu du 15 févr. au 26 févr. · jalon **En ligne** · taille XL · complexité 5/5 · difficulté 5/5

## A. Où tourne cette session ? — à trancher AVANT tout le reste

Ce lot **s'exécute sur devAI**. Lance `hostname -s` :

- **Mac-mini-de-keewoo (hostname -s)** → **mode EXÉCUTANT** : passe à la section 0.
- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.

## P. Mode PILOTE

1. Garde-fou : `python3 docs/roadmap/suivi.py verifier v8-mode-garant`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.
2. Prépare le worktree sur devAI :

```bash
ssh devai 'cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-v8-mode-garant -b roadmap/v8-mode-garant origin/main && mkdir -p ~/dev/logs'
```

3. Lance le lot autonome : `ssh devai 'cd ~/dev/wt-v8-mode-garant && nohup claude -p --dangerously-skip-permissions < prompts/v8-mode-garant.md > ~/dev/logs/v8-mode-garant.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).
4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.
5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/v8-mode-garant` ; résume à JF : statut, grille, preuves, décisions attendues.

---

> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.

## 0. Garde-fou d'ordre — avant toute ligne de code

Dépôt : `~/dev/pokeboy`. Travaille dans ton **worktree** `../wt-v8-mode-garant`, branche `roadmap/v8-mode-garant` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.

```bash
python3 docs/roadmap/suivi.py verifier v8-mode-garant
python3 docs/roadmap/suivi.py demarrer v8-mode-garant --machine "$(hostname -s)" --branche roadmap/v8-mode-garant
```

- **Code 0** → continuer.
- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut v8-mode-garant attente_validation --motif "<raisons>"`, section 7, dernier message `ATTENTE VALIDATION — v8-mode-garant — <raisons>`.
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

**Gain.** La protection sans la logistique : PokeBoy ne touche jamais une carte, mais retient de quoi rendre l'arnaque non rentable.

**Fonctionnalités.** Caution proportionnelle à la valeur figée de l'offre, versée par chacune des deux parties ; libération automatique à la double validation ; commission retenue par PokeBoy ; en cas de litige, la caution suit la décision d'arbitrage ; reçus, facturation et TVA.

**Tenants — ce qu'il faut avant.** Litiges, offre figée, identité vérifiée.

**Aboutissants — ce que ça ouvre.** Un second mode de règlement, sans réécrire la machine à états.

**Dépend de :**
- `v8-litiges` — Quand ça se passe mal

**Décision D15** (avant le 5 févr.) : Circulation de l'argent, si le mode garant est retenu. PokeBoy n'encaisse jamais pour le compte d'un tiers sur son propre compte : retenir les fonds d'autrui est un service de paiement. Proposition : séquestre porté par un prestataire agréé (Stripe Connect ou Mangopay), vérification d'identité des deux parties, commission facturée par PokeBoy avec TVA. À faire confirmer par un conseil avant toute ligne de code. — lis la décision prise dans `etat.json` (`decisions_prises`) et applique-la à la lettre.

## 3. Mission

1. AVANT d'écrire une ligne : chiffrer sur les données réelles produites par v8-litiges — taux de litige constaté, valeur moyenne d'un échange, part des comptes majeurs. Si l'un des trois ne tient pas, le lot S'ARRÊTE et l'écrit dans son compte rendu : c'est une conclusion valable, pas un échec.
2. Séquestre porté par le prestataire agréé retenu en D14 ; aucun flux ne transite par un compte PokeBoy.
3. Libération automatique à la double validation, ou selon la décision d'arbitrage ; aucun cas où l'argent reste bloqué sans qu'un humain en soit averti.
4. Commission, reçus, TVA, et écran « où en est mon argent » lisible par un adolescent et par son parent.

## 4. Risques & pièges

Trois obstacles, dans cet ordre. (1) Une caution inférieure à la valeur de la carte NE DISSUADE PAS : garder une carte à 200 € en perdant 20 € reste rentable — une caution réellement protectrice immobilise l'équivalent de la carte sur une carte bancaire. (2) Retenir les fonds d'un tiers est un service de paiement : PokeBoy n'encaisse jamais sur son propre compte, le séquestre passe par un prestataire agréé, avec vérification d'identité des deux parties. (3) Aucun compte de moins de 18 ans n'y a accès (D13) — ce qui exclut, au démarrage, la majorité des utilisateurs. Ce lot ne démarre que si D12 et D14 le disent.

## 5. Livrables — définition de « fini »

- note de chiffrage préalable (poursuivre ou arrêter, avec les chiffres)
- si poursuite : séquestre de bout en bout, testé, litige compris
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
python3 docs/roadmap/suivi.py tache v8-mode-garant <tache> fait "<preuve : commit, test, URL, capture>"
python3 docs/roadmap/suivi.py compte-rendu v8-mode-garant --resume "…" --livrable "…" --preuve "…" --ecart "…" --reste "…"
python3 docs/roadmap/suivi.py statut v8-mode-garant <livre_uat|attente_go_prod|livre|bloque>
python3 docs/roadmap/suivi.py build
git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A
git commit -m "v8-mode-garant: …" && git push -u origin roadmap/v8-mode-garant
bash scripts/ouvrir-pr.sh roadmap/v8-mode-garant   # ouvre la PR, ou echoue en disant pourquoi
```

**La PR n'est pas optionnelle** : sans elle, la CI ne tourne pas sur ton travail, et c'est la CI qui fait foi. Si `ouvrir-pr.sh` sort en erreur, tu NE conclus PAS que c'est sans importance : tu nommes le manque dans ton compte rendu et dans ton dernier message.

Puis republie la page : lis l'artefact https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.

Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.

