# `j-securite-jeu` — Revue de sécurité du jeu avant ouverture

**Statut : livré.** Exécuté le 15/10/2026, piloté depuis **devAI**, branche `roadmap/j-securite-jeu`.
Garde-fou d'ordre : `suivi.py verifier j-securite-jeu` → **code 0** (« ordre tenu »).

## Résumé

Revue écrite dans **`docs/jeu/SECURITE-JEU.md`**, et **six correctifs** livrés — chacun avec un test
qui échoue sans lui. La revue a trouvé **trois fuites d'information cachée** (toutes dans ce que les
scripts de cartes peuvent faire publier au moteur, exactement là où la fiche du lot annonçait
qu'elles viendraient), **une 500 déclenchable par un seul entier négatif**, **les refus d'accès les
plus intéressants du jeu entièrement muets**, et **la suppression de compte qui n'effaçait pas les
parties**.

Les quatre critères d'acceptation sont tenus. Deux risques résiduels sont nommés dans la revue ;
aucun ne porte sur la confidentialité, et aucun n'est bloquant pour l'ouverture.

## Les six correctifs

| # | Défaut | Correctif | Test qui mord |
|---|---|---|---|
| 1 | Un `choisir` du DSL sur une zone cachée livrait les `instance_id` au joueur qui tranche. `DemandeDecision.ensemble_cache` existait, la projection et le journal l'honoraient — **aucun appelant ne le posait jamais** (zéro `ensemble_cache=True` en production) | `ensemble_cache_pour` dans `pbm_game.effets.dsl.execution`, appelé par `strategie_demande` | `test_un_choisir_sur_la_main_adverse_ne_projette_que_le_nombre_d_options` |
| 2 | `demande_repondue` / `demande_expiree` étaient `_public` : le `choix` retenu — donc une identité potentiellement cachée — partait **aux deux** joueurs | projecteur `_demande_tranchee` + champ `destinataire` sur l'événement | `test_le_choix_retenu_d_une_decision_ne_part_pas_a_l_adversaire` |
| 3 | `chercher` sur sa **propre main** publiait ses `ref` à l'adversaire | `pbm_game.effets.dsl.audit` + refus nommé au chargeur (D9) | `test_un_script_qui_fuiterait_rend_la_carte_refusee`, `test_chercher_dans_une_zone_cachee_de_l_adversaire_est_refuse` |
| 4 | `numero_attendu: -1` → `NoResultFound` non rattrapé → **500** sur une route de jeu | `Field(ge=0)` au schéma **et** `scalar_one_or_none()` + `ConflitNumero` au service | `test_une_charge_utile_hostile_est_refusee_sans_500`, `test_un_numero_en_retard_sans_coup_est_un_conflit_nomme` |
| 5 | Accès à une partie étrangère refusé mais **non journalisé** ; `games_ws.py` déclarait un `logger` **utilisé nulle part** (origine rejetée, session invalide, partie étrangère : aucune trace) | journalisation avec partage INFO (partie inconnue) / WARNING (partie étrangère, CSWSH, session invalide) | `test_action_sur_une_partie_etrangere_est_journalisee`, `test_une_partie_inconnue_ne_crie_pas_dans_le_journal` |
| 6 | `POST /actions`, `/abandon`, `/conseil` écrivaient **sans jeton CSRF**, seules exceptions parmi toutes les mutations du jeu | `require_csrf` sur les trois | `test_les_mutations_du_jeu_exigent_le_jeton_csrf` (3 cas) |
| + | La suppression de compte laissait **toutes** les parties en base, `user_id` en clair dans `game_events.auteur` (une ligne par coup) et dans les JSONB `games.etat_initial` / `game_snapshots.etat`. `games` n'a aucune FK vers `users` : la cascade ne la touchait pas. Une partie `en_cours` n'était jamais purgée | `delete_account` relève les parties par `game_players` et les supprime (journaux et instantanés suivent par cascade) ; la place en file Redis est retirée | `test_supprimer_son_compte_efface_ses_parties_et_leurs_journaux` |

## Les critères d'acceptation, un par un

- [x] **Aucune fuite d'information cachée sur l'ensemble des scripts livrés.** Le corpus réel (94
  scripts) vit en base, **pas dans le dépôt** : une liste figée aurait été verte sur six scripts et
  muette sur quatre-vingt-huit. La garde est donc **structurelle** —
  `apps/game/tests/test_securite_scripts_fuite.py` balaie les **486 combinaisons** du langage
  (18 primitives × 9 zones × 3 propriétaires), exécute les **337** chargeables et sûres, et projette
  **chaque événement pour les deux joueurs** en interdisant toute identité (`instance_id` *et*
  `ref`) d'une zone cachée. Les 141 hors langage et les 8 refusées par l'audit sont **comptées**,
  jamais sautées en silence (le test affirme un plancher de couverture). La fuite n°3 a été trouvée
  par ce balayage, à sa première exécution.
- [x] **Toute action sur une partie étrangère est refusée et journalisée.** Elle était refusée
  (404, jamais 403), et muette. Le partage INFO/WARNING est délibéré : un journal qui crie à chaque
  signet mort est un journal que personne ne lit.
- [x] **La suppression d'un compte efface ses parties et ses journaux.** Avec son contre-test : les
  parties d'un **autre** compte survivent (`test_la_suppression_ne_touche_pas_les_parties_d_un_autre_compte`).
- [x] **La revue est écrite, datée, et ses correctifs sont livrés.** `docs/jeu/SECURITE-JEU.md`.

## Preuves

| Suite | Résultat |
|---|---|
| `apps/game` (moteur, pur) — `uv run pytest -q` | **1 159 passés** (dont 12 neufs), `ruff check` propre |
| `apps/api` — `uv run pytest -q` | **1 413 passés** (dont 13 neufs), `ruff check` propre |
| Les tests **mordent** | sur le code d'avant, **6 des 12** tests moteur échouent, dont le balayage et les deux fuites de projection |
| Balayage du langage | 486 combinaisons · 337 exécutées · 141 hors langage · 8 refusées par l'audit |
| CI GitHub Actions | verte sur le dernier commit poussé — **elle fait foi** |

`tests/test_catalogue_seed.py` est **désélectionné localement** sur devAI : il exige `pg_dump`, qui
n'y est pas installé (`pg_dump: command not found`). Il n'a aucun rapport avec ce lot et la CI
l'exécute normalement.

## Écarts au plan, et pourquoi

1. **La mission disait « rejouer le test de non-fuite sur l'ensemble des scripts livrés ».** C'est
   impossible littéralement, et le dire valait mieux que faire semblant : les scripts livrés sont en
   base, pas dans le dépôt, et une CI ne les lit pas. Le lot livre donc une garde **structurelle**
   (sur le langage, qui couvre tout script présent ou futur) **plus** un outil de lecture seule,
   `apps/api/scripts/auditer_scripts_effets.py`, à passer sur une base réelle. Un test sur six
   scripts énumérés aurait été une CI verte sur rien.
2. **La fuite n°3 n'est pas corrigée, elle est refusée.** Distinguer « déplacer » de « montrer » sur
   la primitive `chercher` est une évolution du **langage** d'effets — une décision de règles, qui
   appartient au lot des effets. Une revue de sécurité qui réécrit la sémantique d'une primitive
   pour fermer une fuite fait exactement ce que D9 interdit. Le script est donc refusé **avant** la
   partie, en nommant la raison.
3. **Deux risques résiduels assumés**, détaillés au § 5 de la revue : aucune limitation de débit sur
   les routes du jeu (le plus coûteux étant le `resync` du WebSocket, puis l'invitation par pseudo
   qui **envoie un e-mail** par appel), et aucun plafond de taille sur `ActionIn.params`, journalisé
   tel quel. Les deux demandent de **choisir un chiffre**, ce qui relève du lot de charge, pas d'une
   revue. Ni l'un ni l'autre ne touche à la confidentialité.
4. **Le blocage d'un joueur n'existe pas** et n'est pas livré : c'est une fonctionnalité, pas un
   correctif. La protection du mineur tient par ailleurs (catalogue d'emotes fermé, **aucun texte
   libre**, aucune route HTTP d'emote, invitation révocable, débit plafonné) — mais « refuser
   toujours » est un geste que l'invitation révocable ne remplace pas. À inscrire au backlog du jeu.
5. **Tâche `release_prod` : sans objet.** Le prompt interdit tout déploiement ; la PROD se livre à
   part, par devAI. Aucun déploiement n'a été fait.
6. **Tâche `maquette` : sans objet.** Le lot ne touche aucun écran — aucune capture n'est due.

## ⚠️ Ce qui attend avant `j-mise-en-ligne-jeu`

**Passer l'auditeur sur le corpus réel**, sur dev, UAT et PROD. Lecture seule, rend `1` s'il reste
un script fautif :

```bash
cd apps/api && UV_PYTHON=3.12 uv run python scripts/auditer_scripts_effets.py
```

Les 94 scripts de la base **n'ont pas été audités** (ils n'existent pas dans le dépôt, et la base de
PROD ne se lit pas depuis un lot). Un script du corpus qui tomberait sous le refus rendrait sa carte
injouable — en le disant, mais sans que personne l'ait vu venir. C'est le seul point de ce lot qui
demande une action hors CI.

## Fichiers

**Moteur (`apps/game`)** — `effets/dsl/audit.py` (neuf), `effets/dsl/execution.py`,
`effets/dsl/primitives.py`, `demandes/moteur.py`, `sortie/evenements.py`,
`tests/test_securite_scripts_fuite.py` (neuf).

**API (`apps/api`)** — `games/service.py`, `games/schemas.py`, `routers/games.py`,
`routers/games_ws.py`, `routers/profile.py`, `profile/service.py`, `jeu/scripts/chargeur.py`,
`scripts/auditer_scripts_effets.py` (neuf), `tests/test_securite_jeu.py` (neuf), et six fichiers de
tests existants mis à jour pour le jeton CSRF.

**Documentation** — `docs/jeu/SECURITE-JEU.md` (neuf), `docs/jeu/AUTORITE-VUES.md` (sa section
« système d'effets différé » décrivait un report levé depuis le câblage des effets : elle dit
maintenant l'état réel), `CLAUDE.md` (carte des fiches).

## Une note sur le `melanger`

Le balayage a aussi trouvé un `AttributeError` non rattrapé : `{"op": "melanger", "cible":
{"zone": "stade"}}` se charge sans broncher (le schéma autorise n'importe quelle zone sur
n'importe quelle primitive) puis tombait sur `getattr(joueur, "stade")` — un 500 en pleine partie,
déclenchable par un script mal écrit en base. `prim_melanger` refuse désormais **en nommant** la
zone (`_ZONES_MELANGEABLES`), comme le fait déjà `selection.candidats`. Ce n'est pas une fuite,
c'est la même famille que les sept événements sans projecteur de `fix-projection-evenements` : le
langage accepte plus de combinaisons que les primitives n'en savent exécuter.
