# CHARGE.md — combien de parties simultanées, et ce qu'une partie coûte

> Le jeu est servi par une machine qui sert **déjà** autre chose : `kailo.life`, son UAT et
> `acx-connect.com`, sur **2 vCPU et 3,8 Go**. Il fallait savoir avant, pas pendant.
> Mesuré le **14/10/2026** par le lot `j-charge-temps-reel`. Refaire la mesure :
> `apps/api/scripts/measure_game_load.py`.

Ce fichier porte des **chiffres datés**, pas des opinions. Le jour d'un incident, c'est lui qu'on
relit pour savoir si ce qu'on observe est normal — et c'est pour ça que les écarts entre la machine
de mesure et la cible y sont écrits noir sur blanc, plutôt que gommés.

## Le plafond, en une ligne

**24 parties simultanées** (`settings.jeu_parties_simultanees_max`, env `JEU_PARTIES_SIMULTANEES_MAX`).
La 25ᵉ est **refusée** en `503` avec `Retry-After: 30`, et les parties en cours ne ralentissent pas.
Pour mémoire, 24 parties = **48 joueurs en même temps**, sur un jeu privé qui en compte trois.

Le plafond n'est pas là pour rationner : il est là pour que la saturation arrive sous la forme d'un
refus lisible plutôt que d'un ralentissement général, où personne ne sait qui est en cause.

## Ce qu'une partie coûte

Mesuré sur chimera, borné à deux cœurs (`taskset -c 0,1`), 15 parties jouées **jusqu'à leur fin**
par les bots, `VACUUM ANALYZE` avant chaque lecture de taille (sans quoi les lignes mortes gonflent
le résultat).

| | Par partie | Par coup |
|---|---|---|
| `games` | 2,7 Kio | — (une ligne par partie) |
| `game_events` (le journal) | 146,1 Kio | **7,0 Kio** |
| `game_snapshots` (instantanés) | 29,9 Kio | — (un tous les 16 coups) |
| **total en base** | **178,7 Kio** | **8,5 Kio** |
| résidu après purge complète | 14,4 Kio | — |
| mémoire du processus API | ~0,5 Mo | — |
| processeur | — | **~20 ms** (15 ms API + ~5 ms Postgres) |

Ces parties-là font **21 coups** (médiane) : c'est court, parce que le joueur de mesure joue
simplement. Une partie entre deux bots qui jouent vraiment fait **215 coups** en médiane (campagne
du lot `j-simulation-bots`). C'est pourquoi le chiffre à retenir est **l'octet par coup** : il ne
dépend pas de la longueur. Une partie médiane réelle pèse donc **≈ 1,8 Mio**.

⚠️ **Le journal est le poste dominant, et c'est voulu** : « tout est rejouable » est un principe du
jeu, pas une option — on ne compresse pas le journal, on le purge quand la partie est morte.

## Jusqu'où ça tient

Latence d'un coup (de la demande à l'état écrit), K parties jouant en même temps, deux cœurs. Le
seuil de jouabilité est **p95 ≤ 500 ms** : au-delà, l'écran reste muet le temps d'un battement de
cœur et le jeu cesse d'être agréable — on sert un enfant de onze ans, pas un terminal.

| K | p50 | p95 | p99 | max | coups/s | RSS |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 98 ms | 181 ms | 181 ms | 181 ms | 6,1 | 83 Mo |
| 2 | 103 ms | 167 ms | 182 ms | 182 ms | 10,0 | 83 Mo |
| 4 | 93 ms | 158 ms | 183 ms | 183 ms | 19,4 | 85 Mo |
| 8 | 162 ms | 219 ms | 305 ms | 308 ms | 27,1 | 87 Mo |
| 12 | 167 ms | 289 ms | 294 ms | 325 ms | 29,9 | 87 Mo |
| 16 | 235 ms | 376 ms | 388 ms | 438 ms | 26,6 | 90 Mo |
| 24 | 223 ms | **368 ms** | 373 ms | 386 ms | 36,0 | 95 Mo |
| 32 | 265 ms | 378 ms | **1 178 ms** | 1 181 ms | 33,3 | 98 Mo |
| 48 | 225 ms | 350 ms | 506 ms | 556 ms | 47,9 | 107 Mo |

**Le point de rupture n'a pas été atteint** : même à 48 parties, la p95 reste sous le seuil. Ce
n'est donc pas la latence qui a fixé le plafond — c'est la prudence, et il faut le dire plutôt que
d'habiller 24 d'une fausse précision.

Deux choses que ce tableau dit quand on le lit bien :

- **la p99 décroche à K=32** (1,2 s pour un coup, alors que la p95 est à 378 ms) : la moyenne tient,
  mais un coup de temps en temps part très loin. C'est la première chose qui se verra côté joueur,
  avant que la p95 ne bouge ;
- **le débit plafonne autour de 30-48 coups/s** sur deux cœurs. À un coup toutes les trois secondes
  par partie (un jeu au tour par tour, où l'on réfléchit), 24 parties demandent **8 coups/s** : on
  est à un sixième de la capacité mesurée.

## Pourquoi 24, et pas 48

| | chimera (mesure) | kailo-srv (cible) |
|---|---|---|
| cœurs | 2 prêtés au script, sur 16 | **2, partagés avec tout** |
| vitesse par cœur (banc JSON représentatif) | 19 180 cycles/s | **32 200 cycles/s — 1,68× plus rapide** |
| Postgres | libre sur les 14 autres cœurs | **sur les deux mêmes cœurs** |
| voisins | gha-runners (charge 3,5/16) | `kailo.life`, son UAT, ACX (charge observée **0,1**) |
| RAM disponible | 13 Go | 2 473 Mo |
| disque libre | — | **12 Go sur 30** |

Les deux écarts jouent en sens inverse et c'est ce qui rend la transposition honnête plutôt que
rassurante : la cible a des cœurs **plus rapides** (un résultat contre-intuitif, vérifié par trois
essais de chaque côté — chimera est un i7-10700K de 2020 sous WSL2), mais elle doit y faire tenir
**aussi sa base de données**. En reportant les deux facteurs, la p95 à 24 parties se projette autour
de **290 ms** sur la cible, soit 58 % du seuil.

⚠️ **Mesure sur un premier banc à ne pas refaire** : un micro-banc `sha256` donnait la cible
**2,8×** plus rapide. C'était faux pour notre usage — les processeurs récents accélèrent SHA-256 en
matériel (SHA-NI), ce qui exagère leur avance sur du bytecode Python ordinaire. Le banc retenu
(sérialisation JSON d'un état + parcours de structures) ramène l'écart à 1,68×, et c'est celui-là
qui ressemble au travail d'un coup.

**24 est donc la moitié du plus grand palier mesuré tenable**, avec la marge pour la contention de
la base et les voisins. Il se relève par l'environnement, sans redéployer — et il ne se relève
qu'avec une mesure à l'appui, pas parce qu'un joueur a reçu un 503.

### Ce que cette mesure ne prouve pas

- **Rien n'a été mesuré sur la cible en charge**, et ce n'est pas un oubli : on ne construit pas, et
  on ne mesure pas, sur la machine qui sert (règle d'or de la flotte). La vérification in situ
  appartient au lot `j-mise-en-ligne-jeu` — procédure ci-dessous.
- La part « Postgres » (≈5 ms par coup) est **mesurée mais pas contrainte** : sur chimera, la base
  avait quatorze cœurs à elle.
- Le canal temps réel n'est pas dans ces chiffres : les coups ont été joués par le service, pas par
  HTTP + WebSocket. La diffusion ajoute un envoi par abonné et par coup, sur une file bornée à 256
  messages (`TAILLE_FILE_ABONNE`) — à 24 parties, 48 abonnés.

## Comment le plafond est appliqué

`pbm_api.games.capacite` + la garde dans `creer_partie` — **le seul endroit du dépôt qui insère une
ligne `games`**, donc aucun chemin ne la contourne.

| Porte | Comportement à plafond atteint |
|---|---|
| `POST /matchmaking/entrainement` | **503** + `Retry-After: 30` |
| `POST /games/{id}/revanche` | **503** + `Retry-After: 30` |
| `POST /lancements/{id}/choisir` | **503** + `Retry-After: 30`, le lancement reste en tirage |
| `POST /matchmaking/queue` | **rien de spécial : le joueur reste dans la file, à son rang** |

La file d'attente est la bonne réponse à une saturation : un joueur qui a demandé « trouve-moi un
adversaire » a déjà accepté d'attendre ; lui renvoyer un 503 serait du bruit. Les trois autres
portes sont des actes immédiats — là, le joueur doit savoir tout de suite.

Deux détails qui comptent :

- **une partie échue ne compte pas** (`expires_at` dans le passé). Sans ce filtre, quelques dizaines
  de parties abandonnées fermeraient le jeu jusqu'au prochain balayage — au pire pendant
  `jeu_inactivite_plafond_h` heures, pour protéger un processeur que personne ne sollicite ;
- **une partie d'entraînement compte**. Elle ne compte pas au classement, mais le bot (et plus
  encore l'IA) consomme *plus* de serveur qu'un humain qui réfléchit entre deux coups.

Le comptage est fait deux fois : une fois à l'entrée sans verrou (pour ne pas payer la résolution de
deux decks quand on va refuser), une fois sous `pg_advisory_xact_lock` juste avant l'insertion (pour
que le plafond soit **exact** sous concurrence, et non indicatif). Le verrou ne gêne que les
créations : **jouer un coup ne le prend jamais**, et un test le garde
(`test_un_coup_ne_prend_jamais_le_verrou_de_capacite`).

## La purge, et à partir de quand elle ne suffit plus

Ce qui existe déjà : `games_maintenance_task` (`apps/api/src/pbm_api/worker.py`), **toutes les
10 minutes**, qui enchaîne `expirer_parties` puis `purger` —

- les **instantanés intermédiaires** de *toutes* les parties, y compris en cours : seul le dernier
  de chaque partie survit. C'est le gros du ménage : 138 instantanés effacés pour 15 parties ;
- les **parties mortes** (terminées ou expirées) de plus de `jeu_purge_anciennete_j` = **30 jours**,
  en cascade sur leur journal et leurs instantanés.

Dimensionnement, à partir des 1,8 Mio d'une partie médiane :

| Rythme de jeu | Volume au plateau (30 jours) | Part des 12 Go libres |
|---|---|---|
| 3 parties/jour (usage réel : trois joueurs) | **160 Mio** | 1,3 % |
| 10 parties/jour | 540 Mio | 4,4 % |
| **18 parties/jour** | **1 Gio** | **8 %** |
| 50 parties/jour | 2,7 Gio | 23 % |

**La purge à 30 jours est donc correctement dimensionnée** pour l'usage prévu, avec une marge de
plus d'un ordre de grandeur. Le seuil à retenir : **au-delà de ~18 parties par jour en moyenne**,
descendre `jeu_purge_anciennete_j` (à 10 jours, le plateau redevient 350 Mio à 50 parties/jour)
plutôt que de regarder le disque se remplir.

⚠️ `jeu_incidents` n'est **pas** purgée avec les parties (`ON DELETE SET NULL` délibéré) : le jeu ne
peut pas effacer sa propre supervision. Son volume est celui des pannes, pas celui du jeu.

⚠️ **Effet de bord de la purge des instantanés, à connaître avant d'être surpris** : une reprise ou
un replay qui demande un état ancien a moins d'instantanés où s'appuyer, donc rejoue plus de coups.
Le résultat est identique (c'est l'invariant de rejouabilité), le temps ne l'est pas.

## Ce qu'on regarde pour savoir si on approche du mur

`GET /jeu/metriques` publie désormais, en plus du reste (`docs/jeu/OBSERVABILITE.md`) :

| Champ | Ce qu'il dit |
|---|---|
| `parties_actives` | celles qui **occupent une place** : en cours *et* non échues |
| `capacite_plafond` | le plafond au moment du relevé (dans le relevé, pour qu'un relevé archivé reste lisible) |
| `capacite_taux` | la part occupée, entre 0 et 1 |

Deux alertes, dans le même relevé que les autres :

- **`capacite_frolee`** (avertissement) à partir de **80 %** du plafond — à 0,8 il reste cinq places,
  donc le moment de parler de la taille du serveur ;
- **`capacite_atteinte`** (critique) à 100 % : des joueurs reçoivent effectivement des 503.

Le seuil est à 0,8 et pas à 1,0 pour une raison simple : une alerte qui arrive en même temps que le
premier joueur refusé n'est pas une alerte, c'est un constat. Et chaque refus laisse un incident
`partie_refusee` / `capacite_atteinte`, donc visible dans `parties_refusees` — distinct du refus
pour carte non scriptée (D9), parce que l'un se corrige en écrivant un script et l'autre en
agrandissant la machine.

## Refaire la mesure

```bash
# sur chimera, JAMAIS sur la machine qui sert, et borné à deux cœurs pour ressembler à la cible
export DATABASE_URL="postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_charge_test"   # base DÉDIÉE
cd apps/api && taskset -c 0,1 uv run python scripts/measure_game_load.py \
    --parties-completes 15 --paliers 1,2,4,8,12,16,24,32,48 --json /tmp/charge.json
```

Le script **refuse** d'écrire dans `pbm_catalogue_ref`, `pokeboy_prod` et `pokeboy_uat` : il crée
des joueurs, des cartes et des parties, il lui faut sa propre base. Il lève le plafond pendant la
mesure — c'est le seul endroit du dépôt où c'est légitime, puisque c'est lui qui le calibre.

### Vérification sur la cible, pour `j-mise-en-ligne-jeu`

Ce qui reste à faire, et qui n'a pas pu l'être ici faute de pouvoir charger la machine qui sert :

1. relever l'état **avant** : `uptime`, `free -m`, `df -h /`, et la santé des trois sites voisins ;
2. jouer **une** partie de bout en bout par l'interface réelle, et relever la latence vue du client
   (l'onglet réseau suffit) — on compare aux 98 ms de p50 mesurés ici ;
3. relever l'état **après**, et vérifier que `kailo.life`, son UAT et `acx-connect.com` répondent
   comme avant (c'est la contrainte absolue de `docs/infra/SERVEUR-POKEBOY.md`) ;
4. lire `GET /jeu/metriques` : `capacite_taux` doit être lisible et cohérent avec ce qui a été joué.

Si la p50 observée dépasse **300 ms** par coup sur une partie seule, ne pas relever le plafond :
chercher d'abord pourquoi, parce que la mesure dit 98 ms et la cible a des cœurs plus rapides.
