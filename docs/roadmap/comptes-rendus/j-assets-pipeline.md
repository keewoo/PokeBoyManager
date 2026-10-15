# `j-assets-pipeline` — Fabrique d'images : variantes, cache, pré-chargement, budget de poids

**Jalon** J3 · piste Graphisme & animations · couloir J-GFX (chimera) · palier 14
**Exécuté** le 15/10/2026, piloté depuis devAI, travaillé sur **chimera** (worktree
`~/dev/wt-j-assets-pipeline`, branche `roadmap/j-assets-pipeline` depuis `github/main` = `3c80ae8`).
**Statut** livré · garde-fou d'ordre `suivi.py verifier` → code 0.

## Résumé

Une partie affiche jusqu'à 120 cartes. `j-rendu-carte` avait posé **une** variante de photo (420 px,
45 Ko), servie aussi bien à la carte posée dans l'arène qu'au zoom : **5,2 Mo par partie**, et le jeu
mourait là sur un téléphone en 4G.

Ce lot dédouble la variante (**plateau 192 px / 12 Ko**, **zoom 420 px / 45 Ko**), pose un **plafond
de poids par variante tenu par construction**, en déduit un **budget de partie contrôlé en CI**,
ferme la fabrication d'images **pendant** une partie — qui existait encore —, donne un **cache avec
empreinte** aux deux routes d'images (l'une n'en avait aucun), et **pré-charge** les images du
plateau pendant la mise en place avec une barre de progression honnête.

## Livrables

| Livrable attendu | Où |
|---|---|
| génération par lots | `apps/api/scripts/preparer_rendus_jeu.py` **étendu** (et non dupliqué) · job `preparer_variantes_jeu_task` dans `worker.py` |
| pré-chargement | `apps/web/src/lib/game/prechargement.ts` (pur) · `apps/web/src/components/game/bandeau-prechargement.tsx` |
| budget mesuré en CI | `apps/api/src/pbm_api/jeu/budget.py` · garde `apps/api/tests/test_jeu_assets_pipeline.py` (job `api`) |
| les variantes et leurs plafonds | `apps/api/src/pbm_api/jeu/rendu_image.py` |
| cache avec empreinte | `apps/api/src/pbm_api/http_images.py` (nouveau), branché sur `routers/images.py` et `routers/jeu_rendu.py` |
| régénération d'une photo remplacée | `rendu_service.invalider_variantes` |
| doc | **`docs/jeu/ASSETS.md`** (nouvelle fiche) · entrée dans la carte des fiches de `CLAUDE.md` · `docs/jeu/RENDU-CARTES.md` mis à jour et renvoyant vers elle |

## Les trois critères d'acceptation

### 1. « Le poids total d'une partie reste sous le plafond fixé, mesuré en CI » ✅

Le budget n'est **pas un chiffre recopié** : c'est une conséquence arithmétique des plafonds de
variantes, lesquels sont garantis en sortie de `fabriquer_image_jeu`. Un chiffre relevé une fois
aurait vieilli en une semaine — il suffit qu'une variante gagne 30 % de qualité pour que le plateau
double, sans qu'aucun test ne bronche.

```
   120 ×  18.0 Kio  cartes en variante plateau        =  2160.0 Kio
     1 ×  64.0 Kio  zoom ouvert (une carte à la fois) =    64.0 Kio
  total partie        2224.0 Kio (plafond 2304 Kio, 11.1 s en 4G)
  dont mise en place   432.0 Kio (plafond 512 Kio,  2.2 s en 4G)
```

Gardes en CI (job `api`) : `test_le_budget_d_une_partie_tient_sous_son_plafond`,
`test_le_budget_est_une_consequence_des_plafonds_pas_un_chiffre_recopie`,
`test_la_mise_en_place_tient_en_quelques_secondes_de_4g`,
`test_chaque_variante_tient_son_plafond_sur_une_carte_realiste`. **Marge de 80 Kio** : relever le
plafond plateau d'un seul Kio (+120 Kio) fait rougir la CI — la garde mord.

### 2. « Aucune génération d'image n'a lieu pendant une partie » ✅

Ce n'était **pas** vrai avant ce lot : `servir_photo` rattrapait la variante manquante au premier
accès. Une partie à deux joueurs pouvait donc déclencher jusqu'à 120 décodages OpenCV **sur la
machine qui sert** (deux cœurs, et des joueurs à servir) — le risque exact nommé par la fiche.

Désormais une variante absente rend **404**, l'écran prend `url_repli` (l'image officielle). La
preuve est un stockage qui **lève à la moindre écriture**
(`test_servir_une_photo_ne_fabrique_jamais_d_image`) : compter les appels aurait laissé passer une
écriture conditionnelle, relire le source aurait laissé passer un appel indirect.

### 3. « Le pré-chargement se termine avant la fin de la mise en place (4G simulée) » ✅

`apps/web/e2e/prechargement-4g.spec.ts` : **19** cartes porteuses d'image — mon actif + cinq de banc
+ sept en main, et en face l'actif + cinq de banc ; sa main et ses récompenses restent des dos, donc
zéro octet. C'est la composition réelle du pire cas de mise en place, dont les 24 de
`budget.CARTES_MISE_EN_PLACE` sont l'arrondi avec marge. Corps d'image au **poids réel** du plafond (18 Kio), lien 4G
**modélisé** comme un tuyau partagé à 200 Ko/s + 150 ms de latence. Le chronomètre part quand le
plateau est visible et s'arrête quand le bandeau s'efface. Budget du test : 6 s ; le modèle prédit
≈ 2,4 s.

⚠️ **Pourquoi pas un bridage CDP** : `Network.emulateNetworkConditions` ne s'applique pas aux
réponses fabriquées par `route.fulfill` (elles ne traversent pas la pile réseau). Un bridage CDP
aurait donné un test vert qui ne mesure rien. Le modèle explicite est sérialisé, donc **pessimiste**.

## Preuves

| Quoi | Résultat |
|---|---|
| `ruff check .` (apps/api) | **All checks passed** |
| pytest ciblé (8 fichiers : assets, rendu ×4, images, detections, validation) | **106 passed** |
| pytest élargi (+ uploads, collection ×2) | **156 passed** |
| tests purs du lot seuls | **17 passed** |
| `vitest run` (toute la suite front, sur devAI) | **842 passed / 94 fichiers** |
| `tsc --noEmit` (apps/web) | **0 erreur** |
| CI GitHub Actions | **verte** sur `0113b47` (4 jobs : `web`, `api`, `game`, `e2e`) — voir l'historique des quatre passages ci-dessous |

### Poids mesurés sur une **vraie** carte

`base1/4` (image officielle 600×825), rééchantillonnée en 630×880 JPEG 92 pour simuler la photo
telle que `photo_s3_key` la stocke — mesuré sur chimera le 15/10/2026 :

| Largeur | photo nette | photo bruitée | bruit pur (incompressible) |
|---|---|---|---|
| 192 (q76) | **12,2 Ko** | 12,4 Ko | 15,9 Ko |
| 420 (q80) | **45,2 Ko** | 55,7 Ko | 125,9 Ko |

C'est de ce tableau que viennent les plafonds (18 Kio / 64 Kio) : ils couvrent le cas bruité sans
dégradation, et forcent une réduction de qualité sur le bruit pur plutôt que de servir 126 Ko.

### Le script par lots, exécuté pour de vrai

Sur une base de test **dédiée** de chimera (`pbm_assets_pipeline_test` — la base de référence
partagée `pbm_catalogue_ref` n'a **pas** été touchée), 40 exemplaires photographiés semés avec des
photos synthétiques variées :

| Passage | Résultat |
|---|---|
| `--a-blanc` | `40 a_preparer`, rien écrit |
| passage réel | `40 variante_produite` · plateau n=40 médiane **3,3 Kio** p95 3,7 · zoom n=40 médiane **23,7 Kio** p95 34,6 |
| second passage | « Rien à préparer » — **idempotent** |
| **rattrapage** : les 40 remis dans l'état d'avant le dédoublement (zoom seul, pas de liste de variantes), puis repassés | `40 a_preparer` → `40 variante_produite` — le parc existant est bien repris |

⚠️ Ces 3,3 / 23,7 Kio sont ceux de **photos synthétiques**, qui compressent mieux qu'une photo
d'appareil : les chiffres à retenir sont ceux de la carte réelle ci-dessus (12,2 / 45,2 Ko). Les deux
sont très en dessous des plafonds.

### Les quatre passages de CI

C'est la CI qui fait foi, et il a fallu quatre passages. Le détail, parce qu'il n'est pas flatteur
mais qu'il est instructif :

| Commit | `web` | `api` | `game` | `e2e` | Ce qui n'allait pas |
|---|---|---|---|---|---|
| `b90af65` | ✅ | ✅ | ✅ | ❌ | **défaut réel du code** : la barre de pré-chargement se figeait quand la vue changeait (voir ci-dessous) |
| `ed3431b` | ✅ | ✅ | ✅ | ❌ | mon assertion : dédoublonnage sur `?v=plateau`, une seule valeur distincte pour 32 requêtes |
| `0970f18` | ✅ | ✅ | ✅ | ❌ | mon assertion : seuil de couverture **deviné** à 20 pour un décor de 19 cartes |
| **`0113b47`** | ✅ | ✅ | ✅ | ✅ | — |

Le chronomètre du critère « avant la fin de la mise en place » est passé au vert dès le deuxième
passage et n'a plus bougé : les deux derniers échecs étaient des tests mal écrits, pas un défaut du
produit. Les trois autres jobs (`web` lint/types/tests/build, `api`, `game`) ont été verts **dès le
premier passage**.

## Un défaut réel trouvé par la CI, et corrigé dans la foulée

Le premier passage de CI a été **rouge** sur la seule nouvelle spec e2e : le bandeau de
pré-chargement restait visible au-delà de 6 s. Ce n'était pas le test qui était trop strict, c'était
un **vrai blocage** :

> La vue d'une partie est un objet neuf à chaque sondage et à chaque resynchronisation. L'effet du
> composant se relançait donc, **interrompait** le lot en cours — et le lot suivant, vide puisque
> toutes les URL étaient déjà vues, rendait la main sans rien signaler. La barre restait figée à
> 50 % pour l'éternité, soit exactement ce que ce composant promet de ne jamais faire.

Correctif : `interrompu` ne regarde plus que le **démontage**, et l'avancée est **cumulée sur la
partie** (`AvanceeGlobale`) au lieu d'être celle du dernier lot — sinon un lot suivant ferait
reculer la barre. Deux tests l'encadrent, et le premier a été **vérifié rouge** en recassant
volontairement le correctif (règle du dépôt) :

- `une vue qui change ne FIGE pas la barre` ;
- `une carte qui apparaît en cours de partie s'ajoute sans faire reculer la barre`.

⚠️ Aucun test unitaire ne l'aurait trouvé — il fallait un navigateur et un vrai enchaînement de
resynchronisations. C'est le deuxième enseignement du lot : la spec e2e a payé son coût du premier
coup.

Le même passage a révélé un second effet mesurable : les images étaient demandées **deux fois** (une
par le pré-chargeur, une par la balise `<img>` du plateau). La spec sert donc désormais les images
**avec leur en-tête de cache**, comme en production — le pré-chargement remplit le cache, le plateau
peint depuis le cache.

⚠️ Et le recouvrement n'est pas tombé à zéro : **32 requêtes pour 24 images** en CI, soit un tiers
de doublons. Le pré-chargeur (`new Image()`) et la balise `<img>` demandent la même URL presque en
même temps, avant que le cache ne soit rempli, et le navigateur ne fusionne pas toujours deux
requêtes en vol venant de ces deux chemins. La spec le **dit** et borne à 2 × le nombre d'images
distinctes plutôt que de prétendre à une requête par image — ce qui compte pour le joueur est le
temps, vérifié séparément. Deux passages de CI supplémentaires ont été nécessaires, et **les deux fois c'était mon assertion
qui était fausse, pas le code** : d'abord un dédoublonnage sur `?v=plateau` (une seule valeur
distincte pour 32 requêtes !) au lieu de l'URL complète, puis un seuil de couverture **deviné** à 20
alors que le décor de test porte 19 cartes. La leçon est écrite dans la spec : le nombre attendu est
désormais **compté sur le décor lui-même** (`cartesAvecImage`), pas recopié — une constante écrite à
la main se désynchronise à la première carte ajoutée.

## Décisions prises dans le lot

1. **Pas de migration.** La liste des variantes produites vit dans
   `collection_items.jeu_qualite["variantes"]` plutôt que dans une colonne neuve : les deux
   informations sont écrites par le même appel dans le même flush et ne peuvent pas diverger, et une
   migration aurait ajouté une **tête Alembic** à fusionner avec celle d'un lot voisin (piège connu
   du dépôt). Son absence sur une ligne ancienne est exactement l'information dont le rattrapage a
   besoin.
2. **La clé de la variante de zoom n'a pas changé** (`jeu/rendu/{user}/{item}.webp`) : des milliers
   de `jeu_image_key` la portent déjà, la renommer aurait orphelinné autant d'objets pour rien. La
   variante de plateau se **dérive** par suffixe.
3. **`?v=` sans paramètre vaut `zoom`**, pas `plateau` : c'est ce que rendaient les URL émises avant
   ce lot, et un onglet resté ouvert doit continuer de rendre ce qu'il rendait.
4. **Une photo hors plafond est refusée, pas servie** (D9) : `VarianteTropLourde` → photo déclarée
   inexploitable, repli sur l'officielle, raison écrite en base. Servir 126 Ko en silence aurait fait
   sauter le budget sans bruit.
5. **Le script existant a été étendu, pas doublé.** Une première version de ce lot avait créé un
   second script (`fabriquer_variantes_jeu.py`) avant de s'apercevoir que `preparer_rendus_jeu.py`
   faisait déjà le travail — il a été supprimé et ses trois apports repliés dans l'existant
   (sélection des variantes incomplètes, distribution des poids, code de sortie non nul sur
   dépassement de budget). ⚠️ Au passage, un **défaut réel** du script existant : sa sélection
   `jeu_qualite IS NULL` aurait déclaré complet tout le parc préparé par `j-rendu-carte`, qui n'a
   qu'une variante.

## Écarts au plan

- **« Génération ... au moment de l'ajout à la collection »** : fait, mais **par un job arq**
  (`preparer_variantes_jeu_task`) enfilé par les deux routes d'ajout, pas en ligne dans la requête.
  Le faire en ligne aurait fait attendre le joueur pour un décodage OpenCV et deux encodages WebP
  par carte — et « Tout ajouter » peut porter 143 détections (cas réel du dépôt).
- **AVIF non produit.** La fiche mentionnait « WebP/AVIF ». Seul WebP est produit : Pillow ne fournit
  pas AVIF sans dépendance supplémentaire, le gain face au WebP à ces tailles est marginal (quelques
  pourcents à 192 px), et le proxy d'images officielles sert déjà du WebP — aucun client du produit
  n'a besoin d'autre chose. Ajouter un format, c'est doubler le stockage et la fabrication : ça se
  décide sur une mesure, pas par principe.
- **Une seule variante légère, pas quatre.** La fiche parlait de « plateau, main, zoom, vignette de
  journal ». Mesure faite : le journal n'affiche **aucune** image (`JournalPanel` est du texte), la
  main et le plateau partagent la même taille à l'écran, et la vignette d'une fenêtre de décision
  fait 40 px — la variante plateau la couvre. Quatre variantes auraient doublé le stockage et le
  temps de fabrication pour un gain nul.
- **`url_vignette` non ajoutée** au contrat `rendu` : `url` / `url_zoom` existaient déjà et
  correspondent exactement aux deux variantes, donc **aucun changement du contrat front**.

## Reste à faire

- **Le parc de PROD n'est pas rattrapé** : `preparer_rendus_jeu.py` doit être lancé **sur la flotte**
  contre la base de production après la livraison (il est reprenable, borné par `--lot`/`--plafond`,
  et sort en erreur si un plafond est violé). D'ici là, les exemplaires photographiés avant ce lot
  se replient sur l'image officielle en jeu — comportement correct et **dit**, mais ce n'est pas ce
  que le joueur attend.
- **Aucun déploiement fait** (hors périmètre du lot) : la PROD se livre à part, par devAI. Le lot
  n'ajoute **aucune migration**, donc la livraison est un simple déploiement de code + un
  redémarrage du worker (le job `preparer_variantes_jeu_task` doit être enregistré côté worker,
  sinon les mises en file finiraient en « function not found »).
- **Trou connu, assumé** : un joueur qui photographie une carte déjà dans son deck et va jouer
  **avant** que le job ne soit passé verra l'image officielle pour cette carte. Le job est enfilé à
  l'ajout, donc la fenêtre est de quelques secondes.
- **Lint front non rejoué localement** (le job `web` de la CI, lint compris, est passé vert) : `next lint` ne peut pas résoudre ses plugins ESLint depuis
  un atelier `/tmp` à `node_modules` lié (artefact pnpm, pas le code). `tsc` et les 842 tests vitest
  sont verts ; c'est la CI qui tranche le lint.
