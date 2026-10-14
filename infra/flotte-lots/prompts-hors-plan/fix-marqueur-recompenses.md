# CONTEXTE D'EXÉCUTION

Tu tournes sur **devAI**, en session autonome (`claude -p`) lancée par la file de lots : **personne ne répondra à une question**. Tu tranches, tu consignes, tu conclus. Ce lot est un **correctif hors plan**, demandé par JF le 01/10/2026 (« Oui, petit lot ») ; il n'a pas d'entrée dans `roadmap.json` — ne lance pas `suivi.py verifier/demarrer`, ne touche ni à `etat.json`, ni à `ROADMAP.html`, ni à `BACKLOG.md`, ni à `prompts/`.

- **Où travailler** : sur **chimera**, jamais dans `~/dev/pokeboy` de devAI. `ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -s' < script` (dépose un script : le quoting PowerShell casse les one-liners). Dépôt `~/dev/pokeboy` de la WSL, worktree `~/dev/wt-fix-marqueur-recompenses`, branche `roadmap/fix-marqueur-recompenses` depuis `github/main` (`git fetch github` d'abord : `origin` est un relais local qui retarde). Le SSH de chimera coupe souvent : réessaie. **Tout script envoyé à chimera commence par `export PATH=$HOME/.local/bin:$PATH`** : `uv` et `claude` y vivent, et `bash -s` n'est pas un shell de connexion — sans cette ligne, `uv` paraît absent alors qu'il est là (c'est le faux « outil absent » du 22/09, `docs/LIVRAISON.md`).
- **Catalogue** : base de référence `pbm_catalogue_ref` (conteneur `pbm-shared-postgres-1`, port 55432 — `docs/infra/JOBS-LOURDS.md`), **lecture seule**. Tes tests ont leur propre base.
- **Git, CI, fusion** : commits ciblés (jamais `git add -A`, jamais `git stash`), `git push -u github roadmap/fix-marqueur-recompenses` ; la PR s'ouvre seule (`pr-auto`, son passage « pull_request » reste en `action_required` : ce n'est pas un échec). Attends la CI **verte** du passage « push » depuis devAI (boucle ci-dessous), puis fusionne sur chimera sous `flock ~/dev/pokeboy.git/pbm-merge.lock` (`git fetch github && git checkout --detach github/main && git merge --no-ff roadmap/fix-marqueur-recompenses -m "Fusion : fix-marqueur-recompenses — …" && git push github HEAD:main`), puis attends la CI sur `main`.
- **Aucun déploiement** : la PROD se livre à part, par devAI. Ta migration doit donc s'appliquer **sans intervention** à la prochaine livraison (non destructive, rejouable).

# Mission — le marqueur de règle d'une carte, normalisé une fois pour toutes

**Le défaut, en PROD.** La fiche carte, onglet « En jeu » (`apps/api/src/pbm_api/ingame/rules.py`, `prize_rule_of`, appelé aussi par `insights_batch/runner.py`), déduit le nombre de récompenses du **suffixe du nom** : une **Méga-Évolution Pokémon ex** (série Méga-Évolution, 2025 — son nom finit par « ex ») y affiche **2** au lieu de **3**, une **TAG TEAM** (nom en « GX ») **2** au lieu de **3**. Le catalogue n'aide pas : `cards.rule_marker` (`catalog/import_service.py`, `_rule_marker`) range le `suffix` brut de TCGdex, ou le `stage` — il ne distingue ni l'une ni l'autre.

**La règle qui fait foi** : `docs/jeu/REGLES.md`, R-13.3, R-13.7 (« le suffixe du nom ne suffit pas »), R-15.1 à R-15.22. **Le vocabulaire** : les clés de `MARQUEUR_RECOMPENSES` dans `apps/game/src/pbm_game/combat/fin.py` (`ordinaire`, `radiant`, `break`, `prisme_etoile`, `lv_x`, `etoile`, `ex`, `tera_ex`, `pokemon_ex`, `m_pokemon_ex`, `gx`, `v`, `vstar`, `legende`, `mega_ex`, `vmax`, `tag_team`, `v_union`). Le lot `j-cartes-pokemon`, qui part **juste après toi**, lira ce marqueur pour charger les cartes dans le moteur : il doit trouver une donnée juste.

1. **Inventaire, sur le vrai catalogue** : compte les cartes Pokémon par (`rule_marker`, `stage`, et tout champ TCGdex utile déjà stocké). Établis comment se reconnaissent, **dans les données**, chaque catégorie de R-15 — en particulier Méga-Évolution ex (2025) vs M Pokémon-EX (XY), TAG TEAM, Tera ex, Prisme Étoile, ★, LÉGENDE, LV.X, BREAK, V-UNION, Radiant. Si une catégorie ne se reconnaît qu'à une donnée TCGdex non stockée, ajoute-la à l'import (un petit échantillon de requêtes TCGdex suffit pour le vérifier ; le lien de chimera plafonne à ~250 Ko/s).
2. **Une seule fonction pure** qui rend le marqueur normalisé d'une carte (ou `None` pour une carte hors Pokémon), et qui **refuse de deviner** : une carte à Rule Box qu'elle ne sait pas classer rend un marqueur explicitement inconnu, jamais `ordinaire`.
3. **Une colonne normalisée** dans `cards` (migration Alembic **non destructive**, avec **remplissage des cartes existantes** dans la migration elle-même), renseignée à l'import. Ne change pas le sens de `rule_marker` sans avoir vérifié ses lecteurs (`decks/service.py`, `decks/stats.py`).
4. **`prize_rule_of` lit le marqueur normalisé**, plus jamais le nom. Le nombre de récompenses vient d'**une seule table** : de préférence celle du moteur (`pbm_game`, paquet pur sans dépendance — dépendance de chemin uv depuis `apps/api`, si le workspace le permet proprement) ; sinon une copie gardée **égale** à celle du moteur par un test. Marqueur inconnu → la fiche dit « récompenses non déterminées » avec le marqueur, jamais un nombre deviné.
5. **Tests** (échouent sans le correctif) : Méga-Évolution ex → 3, TAG TEAM → 3, Pokémon-EX et M Pokémon-EX → 2, ex et Tera ex → 2, VMAX et V-UNION → 3, BREAK/Prisme Étoile/★/LV.X/Radiant/ordinaire → 1, carte hors Pokémon → non applicable, Rule Box inconnu → non déterminé. Au moins un cas par catégorie pris sur une **vraie carte du catalogue** (identifiant cité). Mets à jour les tests existants de `test_ingame_rules.py` qui figeaient l'ancien comportement.
6. **Preuve chiffrée** dans le compte rendu : le nombre de cartes par marqueur normalisé sur `pbm_catalogue_ref`, et la liste (ou le nombre) des cartes non classées.
7. **Documentation** : la colonne et sa règle dans `docs/ARCHITECTURE.md` (section catalogue) ; compte rendu `docs/roadmap/comptes-rendus/fix-marqueur-recompenses.md` (résumé, livrables, preuves, écarts, reste à faire — dont « à livrer en PROD avec la prochaine livraison »).

**Clôture** : compte rendu commité et fusionné dans `main`, CI verte sur `main`, puis dernier message `FAIT — fix-marqueur-recompenses` ou `BLOQUÉ — fix-marqueur-recompenses — <raison>`.



---

## ⛔ RAPPEL FINAL — lis ceci avant d'écrire ton dernier message

Tu es une session `claude -p`. **Il n'existe aucune notification** : rien ne te réveillera. Écrire « j'attends », « standing by », « je reprends à la fin de la tâche de fond » ou « le watcher me préviendra » **termine la session** et fait échouer le lot. Deux lots sont morts ainsi le 21/09.

Une attente se code **dans une seule commande bloquante**, jamais entre deux messages :

```bash
# attendre la CI GitHub sur un commit (jeton dans ~/.kailo-tokens sur devAI).
# Seul le workflow « CI » compte : « PR automatique des lots » tourne sur le même push et finit
# avant elle — le prendre pour la CI, c'est conclure sur un workflow qui ne teste rien.
source ~/.kailo-tokens
# le SHA est celui que tu as poussé DEPUIS CHIMERA (pas le dossier courant de devAI) :
SHA=$(ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- git -C /home/upgreg/dev/wt-fix-marqueur-recompenses rev-parse HEAD' | tr -d '\r')
for i in $(seq 1 60); do
  R=$(curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
      "https://api.github.com/repos/keewoo/PokeBoyManager/actions/runs?head_sha=$SHA&per_page=20" \
      | python3 -c "import json,sys;w=[r for r in json.load(sys.stdin)['workflow_runs'] if r['name']=='CI'];print('aucune' if not w else ('terminee ' + ','.join(sorted({r['conclusion'] or '?' for r in w})) if all(r['status']=='completed' for r in w) else 'en cours'))")
  case "$R" in terminee*) echo "CI : $R"; break;; esac   # « terminee success » et rien d'autre = verte
  sleep 30
done
```

Tu termines **toujours** par la clôture (compte rendu commité **et fusionné dans `main`**) puis `FAIT — fix-marqueur-recompenses` ou `BLOQUÉ — fix-marqueur-recompenses — <raison>`.
