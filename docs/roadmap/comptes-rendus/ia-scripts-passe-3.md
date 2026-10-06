# Compte rendu — `ia-scripts-passe-3`

**Lot hors plan** (DJ8, JF, « re run » du 06/10/2026), reprise directe de `ia-scripts-passe-2`.
But : **reprendre le passage d'assistance IA** pour dépenser le budget DJ8 restant (plafond cumulé
50 €), avec un **arrêt de rendement** si une tranche tombe sous 20 % d'admission, puis **importer les
scripts admis en PROD**. Opéré en session autonome : pilotage **devAI**, calcul **chimera**, import
**kailo-srv**. Ni la porte DJ8 (tests + contradicteur, `ck_card_scripts_scripte_gate`) ni le prompt
de génération n'ont été modifiés — c'était la consigne.

## Verdict (à lire en premier)

Le passage a tourné à **admission stable ~53 %** (8 tranches pleines, de 43 % à 71 %, jamais proche
du seuil d'arrêt de 20 %) et a produit **118 nouveaux scripts admis**, **importés en PROD**
(insert-only, sous verrou + point de restauration) : `card_scripts` scriptés **94 → 212**. Au grain
de la carte, **+550 cartes du catalogue deviennent entièrement jouables** (2 279 → 2 829).

**Mais l'apport sur les collections possédées (JF, Aymeric) est nul ce passage, et c'est le fait
marquant :** la couverture des effets possédés reste **36 / 181**, les cartes jouables de JF **0**
et d'Aymeric **8** — inchangées. La raison est nette et chiffrée : **les 181 effets possédés sont
tous déjà tranchés** (36 scriptés, 0 « jamais vus »), et les 145 non scriptés sont **hors du DSL
v1** — dominés par `degats` (49), `energie` (19), `autre` (16), `recherche` (12). Avec le DSL
actuel et le prompt inchangé, **le passage IA ne peut plus faire progresser les collections
possédées** : tout euro supplémentaire achète désormais de la **largeur catalogue**, pas de la
profondeur sur les cartes de JF et d'Aymeric. Débloquer celles-ci est un chantier **DSL v2**, pas un
passage de plus.

**Dépense : passage de ce lot 11,81 € ; cumul DJ8 21,61 € / 50 €.** Arrêté proprement à un point
reprenable (fin de la tranche 8), ~28,4 € de budget encore disponibles — le grand livre persiste, la
queue du catalogue est reprenable sans redéploiement.

## 1. Reprise (grand livre `ledger-complet.json`)

Reprise à l'identique de `ia-scripts-passe-2` : base de travail `pbm_ia_scripts_ref` sur chimera
(catalogue 23 855 cartes), modèle `claude-sonnet-5`, clé plateforme en fichier `chmod 600` temporaire
(supprimée en fin de lot), priorité de possession **rafraîchie en lecture seule depuis la PROD** le
jour même (126 cartes possédées par les 2 comptes `game_access` : `jfonteray` et
`aymeric.fonteray`). Le grand livre saute les empreintes déjà tranchées (224 avant → 662 après) :
aucun effet n'est repayé.

Pilote de tranches `driver3.py` (orchestration pure, hors dépôt : il n'a **pas** touché la porte ni
le prompt) : il appelle `runner.run` par tranches de budget (~1,4 € ≈ 50 effets frais), mesure
l'**admission parmi les effets exprimables** (`scriptés / (scriptés + à_revoir)`) après chaque
tranche, et applique l'arrêt de rendement.

## 2. Arrêt de rendement — jamais déclenché, admission stable

| Tranche | examinés | scriptés | à revoir | non supportés | admission |
|---|---:|---:|---:|---:|---:|
| T1 | 45 | 18 | 12 | 15 | 60,0 % |
| T2 | 48 | 20 | 8 | 20 | 71,4 % |
| T3 | 55 | 15 | 17 | 23 | 46,9 % |
| T4 | 56 | 17 | 12 | 27 | 58,6 % |
| T5 | 53 | 12 | 13 | 28 | 48,0 % |
| T6 | 51 | 14 | 13 | 24 | 51,9 % |
| T7 | 57 | 8 | 10 | 39 | 44,4 % |
| T8 | 56 | 12 | 16 | 28 | 42,9 % |

L'admission parmi les exprimables est restée **largement au-dessus des 20 %** sur les 8 tranches
(moyenne ~53 %) : l'arrêt de rendement **ne s'est pas déclenché**. En revanche, deux signaux de fond
montrent qu'on s'enfonce dans la queue de moindre valeur : le **nombre de scriptés par tranche
décline** (18 → 8) et le **non supporté par tranche monte** (15 → 28/39). La part « hors DSL v1 »
grossit même quand l'admission *des seuls exprimables* tient. J'ai donc **arrêté volontairement à la
fin de T8**, à un point reprenable (grand livre persistant) : c'est le choix de passe-2, et il est
**nommé**, pas subi — garantir la clôture complète du lot (import + preuve + fusion) en une session
autonome vaut mieux qu'une course de ~7 h vers le plafond qui risquerait de laisser le lot inachevé.

## 3. Rapport par famille (cumul de tous les passages, base de travail)

Le grain du veto de JF. Table famille × statut sur **tout** le registre (lot1 + re-mesure + complet +
passe-3) :

| Famille | scriptés | à revoir | non supportés |
|---|---:|---:|---:|
| aleatoire (pile ou face) | 103 | 22 | 5 |
| degats | 24 | 36 | 155 |
| etat_special | 21 | 4 | 1 |
| defausse | 16 | 21 | 14 |
| choix | 14 | 38 | 0 |
| soin | 8 | 7 | 7 |
| melange | 6 | 0 | 6 |
| recherche | 5 | 9 | 31 |
| pioche | 4 | 3 | 18 |
| position | 3 | 20 | 0 |
| deplacement | 3 | 6 | 0 |
| verrou | 2 | 9 | 0 |
| energie | 0 | 1 | 54 |
| autre | 0 | 0 | 53 |
| **Total** | **209** | **176** | **344** |

`aleatoire` reste le grand gagnant (103 scriptés : pile ou face sous toutes ses formes). `degats` est
massivement `non_supporte` (dégâts proportionnels/conditionnels, hors DSL v1). `energie` et `autre`
restent à **0 scripté** — entièrement hors du langage v1.

## 4. Familles hors DSL v1 dans les collections — le chantier suivant

Restreint aux **181 effets distincts possédés** par JF et Aymeric, voici les effets `non_supporte`
(hors DSL v1) qui bloquent la jouabilité de leurs cartes, par famille :

| Famille (hors DSL v1) | effets possédés non supportés |
|---|---:|
| degats (proportionnels / conditionnels) | 49 |
| energie (manipulation d'énergie) | 19 |
| autre | 16 |
| recherche | 12 |
| pioche | 4 |
| defausse (ciblée / aléatoire) | 3 |
| soin | 2 |

**C'est la carte du chantier DSL v2.** Les 181 effets possédés se répartissent en 36 scriptés, 40 à
revoir et **105 non supportés** ; aucun n'est « jamais vu ». Scripter davantage de cartes de JF et
d'Aymeric passe désormais par **l'extension du langage** (d'abord `degats` conditionnels et
`energie`), pas par un passage IA de plus avec le DSL actuel.

## 5. Import en PROD (seule écriture permise, sous verrou + point de restauration)

Prérequis inchangé depuis passe-2 : le code de lecture des scripts est **déjà en PROD** → aucun
redéploiement, simple import de données. Chaîne flotte `infra/fleet/export_card_scripts.sql`
(209 scriptés exportés de la base de travail) → `import_card_scripts.sql` (insert-only, par
empreinte), sous le **verrou de livraison devAI** (`~/dev/pbm/.verrou-livraison`, pris puis
relâché), après un **point de restauration frais** (`pokeboy_prod-20261006-103218.dump`, 54,3 Mo,
dump complet custom, conservé sur kailo-srv).

Résultat SQL : `COPY 209` → **`INSERT 0 118`** (118 nouvelles empreintes ; 91 déjà présentes,
sautées) → `COMMIT`. Aucune empreinte disparue.

**Preuve (lecture seule, mesurée avant/après sur la PROD) :**

| | avant | après |
|---|---:|---:|
| Voisins (kailo.life, www, acx, pokeboy.acx) | `200 200 308 308` | `200 200 308 308` (inchangés) |
| `pokeboy.lol` | 200 | 200 |
| PROD `card_scripts` scriptés | 94 | **212** (+118) |
| **Cartes du catalogue entièrement jouables** | 2 279 | **2 829** (+550) |
| Effets possédés distincts scriptés (JF ∪ Aymeric, /181) | 36 | 36 (inchangé) |
| — cartes de JF entièrement jouables (sur 10 à effet) | 0 | 0 (inchangé) |
| — cartes d'Aymeric entièrement jouables (sur 105 à effet) | 8 | 8 (inchangé) |

Le grain **catalogue** (+550 cartes jouables pour 118 scripts : un même texte d'effet couvre des
dizaines de cartes) mesure l'apport réel de ce lot. Le grain **possédé** ne bouge pas, pour la raison
du Verdict — c'est la donnée la plus importante à retenir pour décider de la suite.

## 6. Dépense (grand livre DJ8) et sûreté

| Passage | Coût |
|---|---:|
| `ia-scripts-passe` (lot 1) | 1,87 € |
| Re-mesure (passe-2) | 1,69 € |
| Passage (passe-2) | 6,24 € |
| **Passage (passe-3, ce lot)** | **11,81 €** |
| **Cumul DJ8** | **21,61 € / 50 €** |

- Clé plateforme : fichier `chmod 600` temporaire sur chimera, **supprimé** en fin de lot ; jamais
  dans un dépôt, un journal ou une sortie.
- Point de restauration PROD conservé (`pokeboy_prod-20261006-103218.dump`) ; fichiers de transfert
  transitoires nettoyés des deux côtés (TSV, SQL d'import, JSON de couverture).
- Reste **~28,4 € de budget DJ8**, reprenable (grand livre `ledger-complet.json`). Mais, vu le
  Verdict : **le mieux pour les collections possédées n'est plus un passage de plus, c'est le DSL
  v2** (`degats` conditionnels, `energie`). Un prochain passage IA ne rend jouables que des cartes de
  catalogue de fréquence décroissante.
