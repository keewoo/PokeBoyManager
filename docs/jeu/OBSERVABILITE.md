# Observabilité du jeu — voir ce qui se passe avant qu'on s'en plaigne

> Lot `j-observabilite-jeu` (jalon J5). **À ouvrir quand** : on se demande si le jeu va bien, on a
> reçu une alerte, on veut savoir d'où vient une hausse de coups refusés, ou on planifie la sonde.

Le jeu se joue à **deux ou trois**. C'est ce qui rend la supervision indispensable plutôt
qu'accessoire : trois joueurs ne signaleront pas tout, et les deux autres ne joueront peut-être
pas cette semaine. Une règle qui casse doit donc se voir **dans une métrique**, pas dans une
plainte — et un silence ne doit jamais se lire comme « tout va bien ».

## Où regarder, dans l'ordre

| Je veux… | Je fais… |
|---|---|
| l'état du jeu, tout de suite, sans SSH | `GET /jeu/metriques` dans le navigateur (compte avec accès au jeu) |
| savoir ce que la sonde dirait | `uv run python scripts/sonde_jeu.py --mode quotidien --a-blanc` |
| le détail d'un incident (quelle partie, quel compte, quel message) | la table `jeu_incidents` en SQL |
| le dernier verdict de la sonde | son fichier d'état, `~/.pbm-sonde-jeu/etat.json` |
| comprendre un motif de refus `R-x.y` | `docs/jeu/REGLES.md` à cet identifiant |

## Ce qui est mesuré, et d'où ça vient

**Rien n'est dupliqué.** La majorité des métriques se lisait déjà dans les tables du jeu ; seuls
trois faits n'existaient nulle part et ont reçu une table (`jeu_incidents`).

| Métrique | Source |
|---|---|
| parties en cours, parties qui n'aboutissent pas | `games.status`, `games.last_action_at` |
| parties créées, terminées, durée moyenne, coups moyens | `games.created_at`/`last_action_at`/`current_numero` |
| fins par raison — dont **expirations d'horloge** (`temps_ecoule`), **déconnexions fatales** (`desertion`), parties fantômes (`inactivite`) | `games.raison_fin` |
| coups joués | `game_events` (le journal est *append-only* : son volume **est** l'activité) |
| **coups refusés, par motif** | `jeu_incidents` (genre `action_refusee`) — le motif est la **règle citée** |
| **erreurs de moteur** | `jeu_incidents` (genre `erreur_moteur`) |
| **parties refusées faute de carte scriptée (D9)** | `jeu_incidents` (genre `partie_refusee`) |

### Le motif d'un refus est la règle — et c'est tout l'intérêt

Un compteur « refus par motif » calculé sur un message libre produit autant de motifs que de
refus, et ne signale jamais rien. Or le moteur **cite toujours sa règle** quand il refuse
(`pbm_game.actions.modele.refus` l'exige) : `pbm_api.observabilite.motifs.motif_de_refus` en
extrait l'identifiant `R-x.y`, et c'est lui qui devient la clé. Une hausse sur `R-6.2` **nomme
la règle qui casse**.

Deux conséquences à garder en tête :

- un motif `sans-regle` **non nul est un défaut en soi** : il désigne un chemin de refus qui ne
  cite pas sa règle, donc un joueur qui lit un message sans raison ;
- un motif ne transporte **jamais** de donnée d'utilisateur (sa forme est bornée par une
  expression régulière). Le message d'origine va dans `detail`, tronqué, et n'est jamais servi
  par l'API.

### Ce qui n'est délibérément PAS mesuré

Un compteur qui ne peut pas être juste est pire qu'un compteur absent : il rassure. Donc (D9, on
n'approxime pas) :

- **les tours** — on publie les **coups** (`coups_moyens`). Le nombre de tours n'est stocké nulle
  part ; l'obtenir demanderait de rejouer chaque partie. L'écart est assumé, pas comblé au doigt ;
- **les déconnexions passagères** — la présence vit dans Redis (`j-temps-reel`) et un joueur
  revenu dans sa pause de grâce n'a rien cassé. On compte la déconnexion qui a **coûté la
  partie** (`raison_fin = desertion`) ;
- **un script de carte qui plante à l'exécution** n'a pas son propre compteur : il remonte en
  `erreur_moteur`, qui est déjà une alerte critique. Ce qui a un compteur, c'est la carte
  **absente** du registre, qui fait refuser la partie (`partie_refusee`) ;
- **la ventilation par compte** — `jeu_incidents.user_id` existe pour le diagnostic en SQL, mais
  l'API ne le sert pas : ce serait une fuite entre joueurs.

## Les alertes : qui crie, et à partir de quand

Les seuils vivent dans `pbm_api.observabilite.regles` — **pur**, sans base ni réseau, donc
éprouvable seul. La route HTTP et la sonde appellent tous deux `evaluer()` : **un relevé consulté
à l'écran ne peut pas contredire l'e-mail du matin.**

| Code | Gravité | Déclenchement | Ce que ça veut dire |
|---|---|---|---|
| `erreur_moteur` | **critique** | ≥ 1 | Le moteur fait autorité : s'il plante, il a pu produire un état faux. **Jamais** un seuil, jamais une ligne de journal |
| `rafale_refus` | avertissement | ≥ 30 refus **et** > 25 % des coups soumis | Soit l'écran propose un coup illégal, soit un client a été modifié |
| `motif_dominant` | avertissement | ≥ 10 refus, dont ≥ 60 % sur un même `R-x.y` | Une règle précise est en cause — l'alerte la nomme |
| `parties_bloquees` | avertissement | ≥ 1 partie en cours, sans coup depuis 48 h | Des parties n'aboutissent pas ; vérifier `expirer_parties` |
| `capacite_frolee` | avertissement | ≥ 80 % du plafond de parties simultanées | Il reste peu de places : parler de la taille du serveur **avant** le premier 503 — `docs/jeu/CHARGE.md` |
| `capacite_atteinte` | **critique** | plafond atteint | Des joueurs sont effectivement refusés en 503 — `docs/jeu/CHARGE.md` |
| `recap_hebdo_manquant` | avertissement | pas de récapitulatif depuis 8 jours | **La sonde elle-même ne tourne plus** |

Verdict : `PANNE` (au moins une critique), `A_SURVEILLER` (au moins une alerte), `OK` (aucune).
On ne conclut jamais « tout va bien » par défaut — on le conclut parce que la liste est vide.

**Les parties refusées en D9 ne sont pas une alerte.** Refuser plutôt qu'approximer est le
comportement voulu. Elles sont **comptées** et figurent au récapitulatif : c'est la mesure de la
couverture des cartes, pas une panne.

## La sonde

`apps/api/scripts/sonde_jeu.py`, sur le motif de la **sonde honnête** des prix
(`docs/infra/JOBS-LOURDS.md`) : une pièce portable, versionnée, lancée depuis la release
déployée, qui écrit son verdict dans un fichier d'état et envoie un e-mail.

```bash
# depuis apps/api, DATABASE_URL pointant la base à observer
uv run python scripts/sonde_jeu.py --mode quotidien            # n'envoie QUE s'il y a à dire
uv run python scripts/sonde_jeu.py --mode hebdo                # envoie TOUJOURS le récapitulatif
uv run python scripts/sonde_jeu.py --mode quotidien --a-blanc  # affiche, n'envoie rien, n'écrit rien
```

Codes de sortie : `0` rien à signaler · `2` alerte(s) émise(s) · `1` **la sonde a échoué** (elle ne
conclut alors rien, et le dit sur la sortie d'erreur). Une sonde muette n'est jamais un succès.

Destinataire : `SUPERVISION_EMAIL` (défaut `direction@upgreg.ai` — la même boîte que la sonde
d'infrastructure de la flotte, pour qu'une panne du jeu arrive **là où on regarde déjà**). Envoi
par le chemin e-mail unique du produit (`pbm_api.email`) : `SMTP_HOST` vide = envois désactivés
proprement, et l'absence d'envoi reste visible en `WARNING`.

### Le récapitulatif hebdomadaire est l'homme mort

Il part **même quand tout va bien**. C'est ce qui le rend utile : si personne ne vérifie qu'il
*part*, son silence se confond avec « rien à signaler ». La mécanique est donc fermée —
`--mode hebdo` inscrit la date de l'envoi dans le fichier d'état, et `--mode quotidien` la relit :
plus de récapitulatif depuis **8 jours** ⇒ alerte `recap_hebdo_manquant`, y compris quand le jeu,
lui, va parfaitement bien.

8 jours et pas 7 : un envoi décalé d'une heure ne doit pas réveiller quelqu'un.

## Pourquoi la trace est écrite hors de la transaction du jeu

C'est le point qui fait tenir tout le reste, et il est contre-intuitif.

Un coup refusé **lève une exception** : la requête se termine en erreur et sa session est fermée
**sans commit**. Une trace écrite dans cette session serait donc annulée avec le coup qu'on
refusait — on perdrait exactement ce qu'on voulait compter. Même chose pour une partie refusée en
D9 (le lancement est annulé) et pour une erreur de moteur (on abandonne le coup).

`pbm_api.observabilite.consignation` ouvre donc une **session autonome**. Deux conséquences
voulues : la supervision ne peut pas faire échouer le jeu (une écriture de trace qui casse est
journalisée, pas propagée), et le jeu ne peut pas effacer sa supervision.

Dans la suite de tests, la fabrique de session est injectée (`definir_fabrique`) vers la connexion
du test, pour que les lignes disparaissent avec son rollback — **sans jamais changer le code de
production**.

Corollaire du même raisonnement : `jeu_incidents.game_id` et `user_id` sont en **SET NULL**, pas
en CASCADE. La purge des parties mortes (`pbm_api.games.service.purger`) efface la partie ; elle
ne doit pas effacer la trace qui sert à expliquer l'incident. On perd le lien, **jamais le fait**.

## Quand ça crie — runbook

| Alerte reçue | Première chose à regarder |
|---|---|
| `erreur_moteur` | `select motif, type_action, detail, created_at from jeu_incidents where genre='erreur_moteur' order by created_at desc limit 20;` → le `motif` est la classe d'exception, le `detail` le message. Reproduire par un test du moteur **avant** de corriger |
| `rafale_refus` | ventiler par compte : `select user_id, count(*) from jeu_incidents where genre='action_refusee' and created_at > now() - interval '24 hours' group by 1;` — un seul compte = client modifié ou joueur bloqué par l'écran ; tous = bug d'interface |
| `motif_dominant` | lire la règle citée dans `docs/jeu/REGLES.md`, puis vérifier que l'écran ne propose pas ce coup (le client n'affiche que les coups que le moteur déclare légaux) |
| `parties_bloquees` | `select id, status, last_action_at from games where status='en_cours' order by last_action_at;` puis vérifier que l'expiration tourne |
| `capacite_frolee` / `capacite_atteinte` | `select count(*) from games where status='en_cours' and expires_at > now();` — comparer à `JEU_PARTIES_SIMULTANEES_MAX`. Un compte élevé avec peu de joueurs connus = des parties fantômes : vérifier `expirer_parties`. Sinon, **mesurer avant de relever le plafond** (`docs/jeu/CHARGE.md` § Refaire la mesure) |
| `recap_hebdo_manquant` | la sonde, pas le jeu : son agent de planification tourne-t-il ? son fichier d'état est-il écrivable ? |
| **aucun e-mail depuis des jours** | c'est le cas le plus grave et le plus discret : la sonde est morte. Lancer `--a-blanc` à la main |

## Les pièces

| Fichier | Rôle |
|---|---|
| `apps/api/src/pbm_api/models/observabilite.py` | la table `jeu_incidents` et son vocabulaire de genres |
| `apps/api/src/pbm_api/observabilite/motifs.py` | **pur** — normalisation des motifs (la règle citée) |
| `apps/api/src/pbm_api/observabilite/consignation.py` | écriture d'un incident, en session autonome |
| `apps/api/src/pbm_api/observabilite/releve.py` | **pur** — la forme d'un relevé |
| `apps/api/src/pbm_api/observabilite/metriques.py` | lecture des métriques en base (4 requêtes agrégées) |
| `apps/api/src/pbm_api/observabilite/regles.py` | **pur** — les seuils et le verdict |
| `apps/api/src/pbm_api/observabilite/rapport.py` | **pur** — les corps d'e-mail |
| `apps/api/src/pbm_api/routers/observabilite.py` | `GET /jeu/metriques` |
| `apps/api/scripts/sonde_jeu.py` | la sonde (quotidien / hebdomadaire) |
| `apps/api/tests/test_observabilite.py` | les trois critères, dont le **test d'injection** d'erreur de moteur |
| `apps/api/src/pbm_api/games/capacite.py` | le plafond de parties simultanées, dont les compteurs `parties_actives` / `capacite_plafond` du relevé — mesures et dimensionnement : `docs/jeu/CHARGE.md` |
