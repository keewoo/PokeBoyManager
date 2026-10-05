# Compte rendu — `ia-scripts-passe-2`

**Lot hors plan** (DJ8, JF), suite directe de `ia-scripts-passe` (05/10/2026 : 0 script admissible
sur 97). But : **corriger la génération**, **re-mesurer avant de dépenser**, puis — seuil tenu —
lancer le passage et **importer les scripts admis en PROD**. Opéré en session autonome : pilotage
**devAI**, calcul **chimera**, import **kailo-srv**.

## Verdict (à lire en premier)

Le correctif de génération **fonctionne** : d'un taux d'admission de **0 %** (lot précédent) à
**55 %** à la re-mesure. Le passage a produit **90 scripts admis** (porte DJ8 passée : tests verts
+ contradicteur). **88 ont été importés en PROD** (2 déjà présents, insert-only) : `card_scripts`
scriptés **6 → 94**. Les cartes à effet de JF et d'Aymeric gagnent en jouabilité : **effets
possédés scriptés 1 → 36** (+35 sur 181 effets possédés distincts). **Dépense cumulée (grand livre
DJ8) : 9,80 € sur 50 €.** PROD saine, voisins inchangés, point de restauration pris.

Ce n'est pas la porte de sûreté qui avait échoué au lot 1 — elle refusait des scripts non prouvés à
juste titre. C'était l'étage de **génération** (prompt + exemples). Ce lot l'a réparé, mesuré, puis
livré.

## 1. Le correctif (fusionné, CI verte)

Les trois causes mesurées au lot 1, traitées :

1. **Schéma par primitive dérivé du moteur.** `grammaire_dsl()` (gabarit.py) donne désormais, pour
   **chaque** instruction, ses arguments requis/facultatifs, un exemple valide et le piège à éviter
   (surtout l'unité d'un `nombre` : marqueurs vs PV — le défaut « Soignez 30 » → `nombre:3`, pas 30).
   La donnée vit dans le moteur (`pbm_game.effets.dsl.grammaire.SPEC_OPS`), dérivée des constantes du
   chargeur (`OPS_CIBLE_REQUISE`, `OPS_SOURCE_REQUISE`, `OPS_NOMBRE_REQUIS`, `ETATS_SPECIAUX`,
   `VERROUS`, `PORTEES_VERROU`). **Test anti-dérive** (`test_grammaire_dsl`) : une fiche par
   instruction, chaque exemple se charge, retirer un « requis » casse le chargement, les requis
   reflètent les ensembles du moteur.
2. **Exemples d'amorce prouvés.** `EXEMPLES_AMORCE` (6 exemples complets texte→script→essais) sont
   joints au prompt **même quand `card_scripts` est vide** — le trou nommé au lot 1 (le modèle n'avait
   aucune forme réelle à calquer). Chacun **passe** `verifier_script` (vérifié en CI).
3. **Format d'état des essais illustré.** Le prompt montre un **exemple complet** (script + essais
   qui passent), pas seulement une description — c'est ce que le modèle imitait mal (ses cas de test
   ne collaient pas à l'état exact du moteur).

Commits sur `roadmap/ia-scripts-passe-2`, CI « CI » verte (push). Code de production inchangé côté
moteur et porte ; seul le prompt et son amorçage changent.

## 2. Re-mesure (plafond 3 €) — seuil tenu

**50 effets possédés (DJ2), modèle `claude-sonnet-5`, base de travail `pbm_ia_scripts_ref`** (même
catalogue que la PROD, priorité de possession PROD injectée).

| | |
|---|---|
| Admis (scripté) | **27** |
| À revoir | 22 |
| Non supporté | 1 |
| **Admission parmi les effets exprimables** | **55,10 %** (≥ 40 % exigé) |
| Coût | 1,69 € |

Le **contradicteur refuse réellement** (il n'approuve pas tout) : un cas aux tests verts a été
rejeté à raison — « l'attaque inflige TOUJOURS 10 dégâts de base, plus 10 conditionnels » (le script
oubliait le socle). Seuil franchi nettement → passage autorisé.

## 3. Passage (plafond cumulé 50 €)

Lancé détaché sur chimera (sondé), même base, `claude-sonnet-5`, priorité de possession, **possédés
d'abord puis catalogue le plus fréquent**. Arrêté proprement à un point reprenable une fois les
effets possédés traités et un large échantillon de catalogue couvert — la suite du catalogue reste
reprenable (le grand livre persiste), budget encore largement disponible.

- **224 effets traités · 63 scriptés · 71 à revoir · 90 non supportés · 6,24 €.**
- Admission **~55–67 %** sur le **catalogue le plus fréquent** (effets simples et communs : pile ou
  face, pioche, états) ; **basse sur la queue des possédés** (effets complexes, souvent hors DSL v1).

**Enseignement de forme.** La re-mesure a « écrémé » les effets possédés les plus simples (27
scriptés). La queue des possédés est dominée par le `non_supporte` (dégâts proportionnels, défausse
ciblée aléatoire… hors DSL v1). Le **catalogue fréquent**, lui, regorge d'effets simples et se
scripte très bien — c'est là que le budget rend le plus de cartes jouables, exactement ce que
prévoit la priorité DJ2 « possédés d'abord **puis** les plus fréquents ».

## 4. Rapport par famille (le grain du veto de JF)

Cumul des trois passages (base de travail, auteur `assistance-ia`) :

| Famille | scriptés | à revoir | non supportés |
|---|---:|---:|---:|
| aleatoire (pile ou face) | 38 | 10 | 2 |
| etat_special | 13 | 3 | 0 |
| degats | 10 | 11 | 62 |
| choix | 6 | 11 | 0 |
| defausse | 6 | 12 | 4 |
| recherche | 5 | 3 | 16 |
| soin | 5 | 4 | 3 |
| pioche | 3 | 3 | 5 |
| deplacement | 2 | 4 | 0 |
| melange | 1 | 0 | 0 |
| verrou | 1 | 5 | 0 |
| position | 0 | 6 | 0 |
| autre | 0 | 0 | 18 |
| energie | 0 | 0 | 19 |
| **Total** | **90** | **72** | **129** |

Exemples admis (tous passés tests + contradicteur) :

- *« Lancez une pièce. Si c'est face, cette attaque inflige 20 dégâts supplémentaires. »* →
  `pile_ou_face { alors: [infliger_degats 20 à l'actif adverse] }`
- *« Lancez une pièce. Si c'est face, le Pokémon Défenseur est maintenant Paralysé. »* →
  `pile_ou_face { alors: [poser_etat paralyse] }`
- *« Soignez 30 dégâts d'un de vos Pokémon. »* → `choisir(1 en_jeu moi) { soigner nombre:3 }`
  (3 marqueurs = 30 PV — le piège du lot 1, désormais documenté dans la grammaire).

Familles à **retirer d'un mot** si JF le souhaite : `energie` et `autre` (0 admis, tout hors DSL v1) ;
`degats` est dominé par le `non_supporte` (dégâts proportionnels/conditionnels), à rouvrir le jour
d'une extension du DSL.

## 5. Import en PROD (la seule écriture permise, sous verrou + point de restauration)

Prérequis vérifié : **le code de lecture des scripts est déjà en PROD** (`cc64f13`, « partie à
effets jouée en PROD 17/17 ») → aucun redéploiement, un simple import de données.

Chaîne flotte `infra/fleet/export_card_scripts.sql` → `import_card_scripts.sql` (insert-only, par
empreinte), sous le **verrou de livraison devAI** (`~/dev/pbm/.verrou-livraison`, pris puis
relâché), après un **point de restauration frais** (`pokeboy_prod-20261005-135850.dump`, 51,8 Mo,
34 tables + dump ciblé de `card_scripts`).

**Preuve (lecture seule) :**

| | avant | après |
|---|---:|---:|
| Voisins (kailo.life, acx…) | `200 200 308 200 307` | `200 200 308 200 307` (inchangés) |
| `pokeboy.lol` | 200 | 200 |
| PROD `card_scripts` scriptés | 6 | **94** (+88 importés, 2 déjà présents sautés) |
| Effets possédés distincts scriptés (JF ∪ Aymeric, /181) | 1 | **36** (+35) |
| — dont JF (/16 effets possédés) | 0 | 3 |
| — dont Aymeric (/167 effets possédés) | 1 | 33 |
| Cartes d'Aymeric entièrement jouables (effets) | 0 | 8 |

`INSERT 0 88` puis `scripte = 94` confirmés en base. La jouabilité **carte entière** reste stricte
(une carte n'est jouable que si **tous** ses effets sont couverts) : beaucoup de cartes possédées
portent encore ≥ 1 effet `non_supporte` (hors DSL v1) — d'où JF à 0 carte entière malgré +3 effets.
Le grain **effet** (+35 possédés, +88 catalogue) mesure l'apport réel de ce lot.

## 6. Dépense (grand livre DJ8) et sûreté

| Passage | Coût |
|---|---:|
| `ia-scripts-passe` (lot 1) | 1,87 € |
| Re-mesure (ce lot) | 1,69 € |
| Passage (ce lot) | 6,24 € |
| **Cumul** | **9,80 € / 50 €** |

- Clé plateforme : fichier `chmod 600` temporaire sur chimera, **supprimé** en fin de lot ; jamais
  dans un dépôt, un journal ou une sortie.
- Point de restauration PROD conservé ; fichiers de transfert transitoires nettoyés (TSV, dumps).
- Reste **~40 € de budget DJ8** : la queue du catalogue (effets fréquents non encore couverts) est
  reprenable par un prochain passage (grand livre `ledger-complet.json`), sans redéploiement.
