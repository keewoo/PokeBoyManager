# `j-observabilite-jeu` — Voir ce qui se passe : métriques du jeu et alertes de règles

**Machine** : chimera (WSL Ubuntu-24.04), piloté depuis devAI · **Branche** : `roadmap/j-observabilite-jeu`
· **Date** : 2026-10-14 · **Jalon** : J5 · **Palier** 9 · couloir J-SRV

## Résumé

Trois faits du jeu n'existaient **que dans la sortie du serveur** : un coup refusé, une erreur de
moteur, et une partie refusée faute de carte scriptée (D9). Journalisés en `logger`, ils étaient
perdus au redémarrage, invisibles sans SSH et impossibles à compter — alors que ce sont
précisément les signaux du jalon J5. Ils ont désormais une table (`jeu_incidents`), des compteurs,
des seuils, une route HTTP et une sonde.

Le reste des métriques (parties en cours, créées, terminées, fins par raison — dont les
expirations d'horloge et les désertions —, durée, coups) se lisait **déjà** dans `games` et
`game_events` : rien n'a été dupliqué.

Deux décisions de conception portent tout le lot, et elles sont contre-intuitives :

1. **La trace est écrite dans une session autonome.** Un coup refusé lève une exception : la
   session de la requête se ferme **sans commit**. Une trace écrite dedans aurait été annulée
   avec le coup qu'on refusait — on aurait perdu exactement ce qu'on voulait compter. Corollaire
   du même raisonnement : `game_id`/`user_id` sont en **SET NULL**, pour que la purge des parties
   mortes n'efface pas la trace qui explique l'incident.
2. **Les seuils sont purs et partagés.** `pbm_api.observabilite.regles.evaluer` ne lit rien et
   n'envoie rien ; la route et la sonde l'appellent tous deux. Un relevé consulté à l'écran ne
   peut donc pas contredire l'e-mail du matin.

Le risque nommé du lot (« dupliquer la sonde existante par des scripts ad hoc ») est tenu :
`scripts/sonde_jeu.py` suit le motif de la **sonde honnête** des prix (pièce portable versionnée +
verdict dans un fichier d'état + e-mail vers `direction@upgreg.ai`), passe par le chemin e-mail
unique du produit (`pbm_api.email`), et s'insère dans la famille d'agents `ai.upgreg.pbm-*`
déjà documentée dans `docs/infra/JOBS-LOURDS.md`.

## Livrables

| Quoi | Où |
|---|---|
| Table des incidents + vocabulaire de genres | `apps/api/src/pbm_api/models/observabilite.py`, migration `b7d4e2f8a1c3` |
| Normalisation des motifs (**pure**) — le motif d'un refus **est la règle `R-x.y` citée** | `apps/api/src/pbm_api/observabilite/motifs.py` |
| Écriture d'un incident, hors transaction de l'appelant | `…/observabilite/consignation.py` |
| Forme du relevé (**pure**) et sa lecture en base (4 requêtes agrégées) | `…/observabilite/releve.py`, `…/metriques.py` |
| Seuils d'alerte et verdict (**purs**) | `…/observabilite/regles.py` |
| Corps d'e-mail : alerte et récapitulatif (**purs**) | `…/observabilite/rapport.py` |
| Route `GET /jeu/metriques` (accès au jeu requis, 404 sinon, agrégée) | `…/routers/observabilite.py` |
| Câblage : refus, erreur de moteur, partie refusée D9 | `…/games/service.py` (`_journaliser_refus`, garde de `appliquer_action`, `creer_partie`) |
| La sonde (quotidien / hebdomadaire / à blanc) | `apps/api/scripts/sonde_jeu.py` |
| 31 tests, dont le **test d'injection** d'erreur de moteur | `apps/api/tests/test_observabilite.py` |
| Fiche durable (métriques, seuils, runbook, ce qui n'est **pas** mesuré) | `docs/jeu/OBSERVABILITE.md` |
| Table + route + choix de conception | `docs/ARCHITECTURE.md` § « Supervision du jeu » |
| Planification et runbook d'exploitation | `docs/infra/JOBS-LOURDS.md` |
| Variable `SUPERVISION_EMAIL` (facultative) | `.env.example`, `apps/api/src/pbm_api/config.py` |

## Critères d'acceptation — preuves

### 1. « Une erreur de moteur en production déclenche une alerte, vérifié par un test d'injection »

`test_injection_erreur_moteur_consigne_un_incident_et_alerte` force le moteur
(`pbm_game.journal.appliquer`, vu par le service) à lever un `KeyError` — profil d'un vrai bug,
et non un `ValueError` déjà traité comme coup illégal — dans une partie réelle, puis vérifie les
**trois maillons** : l'incident est écrit (`motif == "KeyError"`, et le motif ne trahit aucune
donnée de la partie), le relevé le compte (`erreurs_moteur == 1`), et la règle d'alerte rend
`PANNE` avec la gravité `critique`.

`test_erreur_moteur_sans_le_garde_ne_laisserait_aucune_trace` complète : la partie n'a **pas**
avancé (`current_numero == 0` — le serveur fait autorité) **et** l'incident existe.

**Preuve que les tests mordent** : en neutralisant la consignation (`return` en tête de
`consigner_incident`) et la règle `erreurs_moteur > 0`, **10 des 31 tests échouent** — dont les
deux ci-dessus, le refus consigné, la partie refusée D9, la purge, et la route. Sabotage retiré,
`31 passed`, et `grep -c SABOTAGE` à 0 sur tout le paquet.

```
10 failed, 21 passed    (sabotage en place)
31 passed               (sabotage retiré)
```

### 2. « Les métriques sont visibles sans se connecter en SSH »

`GET /jeu/metriques` sert le relevé, les alertes et le verdict à un compte connecté ayant l'accès
au jeu (D11) ; un simple navigateur suffit (cookie de session).

- `test_metriques_visibles_sans_ssh_avec_le_meme_verdict_que_la_sonde` : `200`, `verdict == "PANNE"`,
  `releve.erreurs_moteur == 1`, et **aucune ventilation par compte** dans la réponse ;
- `test_metriques_404_pour_un_compte_sans_acces_au_jeu` : **404**, pas 403 — pour un compte non
  invité le jeu n'existe pas (test d'accès croisé) ;
- `test_metriques_401_sans_session` : la supervision n'est pas publique ;
- `test_metriques_refuse_une_fenetre_hors_bornes` : `422` sur `fenetre_heures` 0 et 100000.

### 3. « Le récapitulatif hebdomadaire arrive, et son absence est elle-même un signal »

Vérifié **réellement** contre Mailpit de chimera (SMTP 51025), pas seulement en test :

```
=== mailpit : ce qui est arrivé ===
total: 2
- direction@upgreg.ai | [PokeBoy jeu] Récapitulatif hebdo — 0 partie(s) créée(s), 0 terminée(s)
- direction@upgreg.ai | [PokeBoy jeu] PANNE — erreur_moteur
```

L'absence est **mécanisée**, pas seulement documentée : `--mode hebdo` inscrit la date d'envoi
dans son fichier d'état, `--mode quotidien` la relit, et au-delà de 8 jours l'alerte
`recap_hebdo_manquant` part — y compris quand le jeu va bien. Observé en conditions réelles au
premier passage (état absent) :

```
[AVERTISSEMENT] recap_hebdo_jamais_envoye — Aucun récapitulatif hebdomadaire n'a jamais été envoyé…
```

Codes de sortie de la sonde, vérifiés un par un : `0` base saine, `2` avec alertes, `1` quand la
sonde elle-même échoue — et dans ce dernier cas elle **le dit** au lieu de conclure :

```
SONDE EN ÉCHEC : ConnectionRefusedError — [Errno 111] Connect call failed ('127.0.0.1', 1)
```

## Autres preuves

| Contrôle | Résultat |
|---|---|
| `ruff check .` (`apps/api`) | `All checks passed!` |
| `pytest tests/test_observabilite.py` | **31 passed** |
| Suite API complète | **1181 passed**, 2 échecs **environnementaux** `test_catalogue_seed.py` (`pg_dump: command not found` dans la WSL de chimera — sans rapport avec le lot, la CI a le client Postgres) |
| `alembic upgrade head` sur base neuve | passe ; `alembic heads` → **une seule tête** `b7d4e2f8a1c3` |
| **CI GitHub Actions** (elle fait foi) | **verte** sur `a991f7f` — `CI` / event `push` → `success`. Le passage `CI` / event `pull_request` du même SHA reste en `action_required` (le dépôt exige une approbation pour les PR du bot) : ce n'est pas un échec, et ce n'est pas lui qui fait foi |
| Base de test | `pbm_jobsv_test`, créée pour ce lot ; `pbm_catalogue_ref` **jamais touchée** |
| Isolation / secrets | aucun secret dans le code ni les sorties ; le `motif` est borné par expression régulière et ne peut pas transporter de donnée d'utilisateur (`test_motif_d_erreur_est_la_classe_jamais_le_message`) ; `jeu_incidents.user_id` existe pour le SQL d'administration et n'est **jamais** servi par l'API |

## Écarts au plan — assumés, pas comblés au doigt (D9)

1. **« tours moyens » → coups moyens.** Le nombre de tours n'est stocké nulle part ; l'obtenir
   demanderait de rejouer chaque partie. On publie les **coups** journalisés, nommés comme tels.
2. **Les déconnexions passagères ne sont pas comptées.** La présence vit dans Redis
   (`j-temps-reel`) et un joueur revenu dans sa pause de grâce n'a rien cassé. Ce qui est compté
   est la déconnexion qui a **coûté la partie** (`raison_fin = desertion`).
3. **« Scripts de cartes en échec » n'a pas son propre compteur.** Un script qui plante à
   l'exécution remonte en `erreur_moteur`, déjà critique ; un compteur distinct serait toujours à
   zéro et rassurerait à tort. Ce qui a un compteur, c'est la carte **absente** du registre, qui
   fait refuser la partie (`partie_refusee`).
4. **Aucun écran.** Les métriques sont servies en JSON sur une route authentifiée, ce qui remplit
   le critère (« sans SSH ») sans ajouter d'écran au périmètre d'un lot de taille S. La tâche
   `maquette` est donc **sans objet** : aucun composant d'`apps/web` n'a été touché.
5. **Les agents launchd ne sont pas installés.** Ils vivent sur devAI, **hors dépôt** (comme toute
   l'orchestration de `JOBS-LOURDS.md`), et ce lot n'a le droit de déployer ni de livrer. Les deux
   lignes sont écrites dans `docs/infra/JOBS-LOURDS.md` pour la livraison qui les posera.
6. **Un refus déjà exprimé par un `ValueError` du moteur reste classé « refus ».** C'est le
   comportement d'avant le lot, inchangé : un `ValueError` levé par le moteur pour une raison qui
   n'est pas une règle serait compté comme refus avec le motif `sans-regle`. Ce motif non nul est
   lui-même signalé comme un défaut à corriger (`docs/jeu/OBSERVABILITE.md`).
7. **`/Volumes/Data` refuse l'écriture sur devAI.** Le volume est monté avec 122 Gio libres et les
   droits POSIX corrects, mais toute écriture rend `Operation not permitted` (TCC) depuis cette
   session — y compris sans bac à sable. Conséquence : aucun fichier de transit n'a été déposé sur
   devAI (les sources ont été écrites directement dans le worktree de chimera, et les scripts
   d'acheminement, quelques kilo-octets, supprimés après usage). **C'est un réglage
   *Confidentialité et sécurité* à refaire par JF** — le constat est signalé plutôt que contourné
   en silence.

## Reste à faire

- **Poser les deux agents launchd sur devAI** (`ai.upgreg.pbm-jeu-probe` 08:30,
  `ai.upgreg.pbm-jeu-hebdo` lundi 07:00) au moment de la prochaine livraison : tant qu'ils
  n'existent pas, les métriques sont consultables mais **personne n'est réveillé**.
- **Livrer en PROD** (hors périmètre de ce lot, la PROD se livre à part par devAI) : la migration
  `b7d4e2f8a1c3` est à jouer, et `SUPERVISION_EMAIL` est facultative.
- Re-régler l'accès disque TCC de `/Volumes/Data` sur devAI (JF).

## Grille

| Tâche | État | Preuve |
|---|---|---|
| `dev` | fait | paquet `pbm_api.observabilite`, table `jeu_incidents`, route `/jeu/metriques`, sonde, câblage dans `games/service.py` |
| `tests` | fait | 31 tests ; test d'injection d'erreur de moteur ; sabotage ⇒ 10 échecs ; suite API 1181 passed |
| `securite` | fait | 404 pour un compte sans accès au jeu, 401 sans session, relevé agrégé sans ventilation par compte, motif borné sans donnée utilisateur, aucun secret |
| `maquette` | sans objet | aucun écran dans le périmètre (écart 4) |
| `doc_tech` | fait | `docs/jeu/OBSERVABILITE.md`, `docs/ARCHITECTURE.md`, `docs/infra/JOBS-LOURDS.md`, `CLAUDE.md`, `.env.example` |
| `release_uat` | fait | recette locale sur chimera : migration, suite, sonde de bout en bout vers Mailpit, codes de sortie |
| `release_prod` | non fait | ce lot n'a pas le droit de déployer ; voir « Reste à faire » |
| `backlog` | n/a | l'état du lot est tenu par la file (consigne d'exécution) |
| `compte_rendu` | fait | ce document |
