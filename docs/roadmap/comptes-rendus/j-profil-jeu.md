# Compte rendu — `j-profil-jeu`

**Lot** Profil de joueur : avatar, carte fétiche, badges · jalon **J4** · piste Compte & progression ·
couloir J-UI (chimera) · **P2**, taille S, décision **DJ6**.

**Session** autonome (`claude -p`), pilotée depuis **devAI**, travail sur **chimera**
(WSL Ubuntu-24.04, worktree `~/dev/wt-j-profil-jeu`, branche `roadmap/j-profil-jeu` depuis
`github/main` à `db16790`). Garde-fou d'ordre : `suivi.py verifier j-profil-jeu` → **code 0**
(« ordre tenu »).

## Résumé

Cinq badges déclarés, attribués **à la clôture d'une partie** et **une seule fois** (contrainte
d'unicité en base, pas un `if`) ; une **carte fétiche** choisie dans sa collection et montrée à
l'adversaire **au lancement**, avec le rendu que son propriétaire a réglé (DJ5) ; une **vitrine**
`/jeu/profil` qui reprend l'avatar et le pseudo du compte. Aucun achat, aucune monnaie, aucun
tirage au sort.

La réponse au risque du lot — « des badges de temps de jeu transforment un jeu en obligation
quotidienne » — est **structurelle** et non cosmétique : `FaitsBadges`, la seule chose que voit la
fonction d'attribution, **ne porte aucun champ de temps**. Une condition de badge ne *peut pas*
récompenser une durée, un jour de connexion ou une série, puisqu'elle n'en sait rien. Un test relit
les noms de champs de la classe (`champs_de_temps()` doit rester vide) : ajouter `duree_s` fera
rougir la suite, ce qui est le but — le débat doit avoir lieu avant, pas après.

Deux décisions de fond, prises et écrites plutôt que devinées :

1. **Les badges sont stockés, là où le classement ne stocke rien.** `j-classement-prive` recalcule
   tout à la lecture, et c'est juste pour lui. Impossible ici pour une raison unique : « K.O. en un
   coup » est un fait du **journal**, et le journal est **purgé à trente jours**. Un badge recalculé
   disparaîtrait un mois après avoir été mérité, sans un mot. On capte le fait pendant que la preuve
   existe.
2. **Le réglage `badges_actifs` (défaut `non`) gouverne la VITRINE, pas l'attribution.** DJ6 veut les
   badges « en option, activables par JF » : ce qui est optionnel, c'est l'écran. Si l'attribution
   s'arrêtait aussi, allumer les badges après six mois de parties donnerait une vitrine vide — et le
   badge qui dépend du journal serait perdu à jamais.

## Livrables

| Livrable attendu | Où |
|---|---|
| badges (liste + conditions, **pur**) | `apps/api/src/pbm_api/jeu/badges.py` |
| attribution idempotente | `apps/api/src/pbm_api/jeu/badges_service.py`, appelée par `games/fin_compte.py` |
| table des badges | `apps/api/src/pbm_api/models/player_badges.py` + migration `d7f2a9c3e1b6` |
| réglage de JF | `badges_actifs` dans `apps/api/src/pbm_api/jeu/reglages.py` (sans migration, comme annoncé par `j-classement-prive`) |
| le fait de jeu « K.O. en un coup » | `apps/game/src/pbm_game/journal/recapitulatif.py` (`StatsJoueur.ko_en_un_coup`, **pur**) |
| carte fétiche (choix, possession, rendu) | `apps/api/src/pbm_api/jeu/profil_service.py` + colonne `users.carte_fetiche_card_id` |
| carte fétiche **au lancement** | `apps/api/src/pbm_api/games/lancement.py` (`CampLancement.carte_fetiche`) + `routers/lancement.py` |
| photo servie dans le cadre d'un lancement | `jeu/rendu.py` (`url_photo_lancement`, `rendu_carte_fetiche`), `jeu/rendu_service.py` (`servir_photo_lancement`), route dans `routers/jeu_rendu.py` |
| routes du profil | `apps/api/src/pbm_api/routers/profil_jeu.py`, montées dans `main.py` |
| vitrine de profil | `apps/web/src/app/jeu/profil/{page,profil-view}.tsx` + lien depuis le salon |
| client API front | `apps/web/src/lib/api/profil-jeu.ts` |
| doc technique | `docs/jeu/PROFIL.md` + entrée dans la carte des fiches de `CLAUDE.md` + question des décors tranchée dans `docs/jeu/DECORS.md` |
| tests | `apps/api/tests/test_jeu_profil.py` (20) · `apps/game/tests/test_recapitulatif_ko_en_un_coup.py` (8) · `apps/web/src/app/jeu/profil/profil-view.test.tsx` (7) · entrée `/jeu/profil` dans l'audit e2e `apps/web/e2e/a11y-jeu.spec.ts` |

## Les cinq badges retenus

| Code | Nom | Condition | Mesure |
|---|---|---|---|
| `premiere-victoire` | Première victoire | gagner une partie qui compte | `issue` |
| `ko-en-un-coup` | K.O. en un coup | mettre K.O. un Pokémon **intact**, d'une seule attaque | `exploit` |
| `victoire-sans-recompense-cedee` | Sans rien céder | gagner sans que l'adversaire prenne une seule récompense | `exploit` |
| `dix-parties` | Dix parties | dix parties comptabilisées | `volume` |
| `deck-monotype-victorieux` | Monotype vainqueur | gagner avec un deck dont tous les Pokémon sont du même type | `construction` |

Condition commune à tous : la partie doit **compter** (`comptabilisee`) — ni l'entraînement contre
le bot (DJ7), ni une partie expirée faute d'activité.

## Les trois critères d'acceptation, mesurés

**1. « Un badge ne peut être attribué deux fois. »** ✅ Deux fois, par deux chemins différents.
`test_rejouer_la_cloture_nattribue_rien_de_plus` appelle l'attribution deux fois sur la même partie :
le premier appel rend trois codes, le second l'**ensemble vide**, et la table en compte exactement
trois. Puis `test_la_base_refuse_un_doublon_de_badge` attaque la contrainte **sans passer par le
code** (deux lignes identiques insérées à la main) et exige une `IntegrityError` : c'est la preuve
que l'idempotence ne repose pas sur un `if` — lequel perdrait la course entre deux clôtures
concurrentes, exactement comme `uq_game_results_game` pour la clôture elle-même.

**2. « Aucun mécanisme ne récompense le temps passé plutôt que le jeu lui-même. »** ✅ Trois gardes,
toutes **structurelles** (elles portent sur la déclaration, pas sur les badges du jour) :

- `test_aucun_fait_de_badge_ne_parle_de_temps` — `champs_de_temps()` doit rendre `()`. C'est la
  garde qui compte : les faits ne portent ni durée, ni date, ni série, ni jour de connexion, donc
  aucune condition **ne peut** lire le temps ;
- `test_le_vocabulaire_des_mesures_ne_contient_aucun_temps` — comparaison **exacte** des quatre
  mesures permises : une cinquième (« assiduité », « temps de jeu ») ne peut pas apparaître sans que
  quelqu'un modifie ce test en connaissance de cause ;
- `test_il_nexiste_quun_seul_palier_de_volume` — un seul badge de volume. Dix parties, pas
  10/50/100/500 : une échelle est un tapis roulant. C'est pourquoi « dix parties » est accepté bien
  qu'il mesure une quantité — un palier unique se franchit, puis s'oublie.

Vérifié aussi de l'extérieur : la sortie HTTP publie `mesures_possibles`, et le test de route
contrôle que `"temps"` n'y figure pas.

**3. « La carte fétiche s'affiche au lancement, avec le rendu choisi (photo ou officielle). »** ✅
`test_la_carte_fetiche_saffiche_des_deux_cotes_au_lancement` fabrique deux comptes invités, leur fait
choisir une carte fétiche (A avec une photo exploitable, B sans), **ouvre le lancement par sa route
réelle** (`GET /lancements/{invitation_id}`) et vérifie dans le corps HTTP :
`inviter.carte_fetiche.nom == "Pikachu"` avec `rendu.origine == "photo"` et son `url_repli`
officiel ; `invitee.carte_fetiche.nom == "Bulbizarre"` avec `rendu.origine == "officielle"` **et sa
raison**. Puis l'autre camp relit la vue et obtient **exactement** le même objet (la vue d'un
lancement est symétrique par construction).

## Ce qu'il a fallu créer pour y arriver, et pourquoi

**Un cadre d'autorisation pour la photo d'une carte fétiche.** Une URL de photo n'existe pas sans
cadre dans ce dépôt : `url_photo` est bornée à une **partie**, et la route revérifie la
participation. Or au lancement, **la partie n'existe pas encore** — elle naît du pile ou face. Sans
nouveau cadre, la carte fétiche serait *toujours* servie en image officielle et le critère
d'acceptation serait faux dans les faits. D'où une route jumelle bornée au **lancement** :
`GET /jeu/rendu/lancements/{launch_id}/photos/{item_id}`, qui **rejoue** toute la décision DJ5
(participation, propriété, préférence, veto) et rend le **même** 404 pour tous les refus.

**Le regard est toujours celui de l'adversaire**, y compris quand c'est le propriétaire qui lit la
vue. Ce n'est pas une approximation : la vue d'un lancement est symétrique (c'est ce qui rend le pile
ou face vérifiable par les deux joueurs), la carte fétiche est « ce que je montre », et il n'existe
ainsi **aucun chemin asymétrique** par lequel une URL de photo pourrait être émise sous veto.

**La variante de jeu est préparée au moment du choix** de la carte fétiche. `j-assets-pipeline`
interdit de fabriquer une image pendant une partie et nomme les moments légitimes ; le choix d'une
carte fétiche en est un : geste délibéré, **une** image, hors de toute partie. Sans cela, la photo
du joueur se replierait presque toujours sur l'officielle — critère « vrai », produit faux.

## Une stricture assumée sur « K.O. en un coup »

Le badge demande un Pokémon mis K.O. **intact**, pas un coup de grâce. Le journal ne porte pas les
dégâts *antérieurs* d'un Pokémon, mais `EVT_KO` porte ses `compteurs` au moment du K.O. : leur
égalité avec les dégâts de l'attaque signe une cible intacte. La condition exige donc, **dans le
même coup** : une seule `EVT_ATTAQUE_DECLAREE` (dégâts > 0), un seul `EVT_KO` dont le bénéficiaire
est l'attaquant, et `compteurs == degats`.

Hors de cette forme, **on n'attribue rien** — y compris sur un double K.O. (R-13.5) ou une attaque
qui étale ses dégâts sur le banc. La raison est nommée dans le code : `EVT_DEGATS` identifie sa cible
par la carte **active** (qui change à chaque évolution) et `EVT_KO` par la carte **de base** ; au
delà d'un K.O. par coup, l'appariement n'est plus sûr. Devant ce doute, on préfère un badge manqué à
un badge inventé (D9). Les six tests de refus le vérifient autant que les deux d'attribution.

**Une alternative écartée** : rendre l'appariement exact en ajoutant un champ à `EVT_DEGATS` ou
`EVT_KO`. Ce serait toucher la charge utile d'un événement du moteur, qui a **deux parités** (le
projecteur serveur et le traducteur du journal côté front) : c'est un lot de moteur, pas un lot
d'interface.

## Les décors : question tranchée, et c'est non

`j-arene-decors` avait laissé ouverte la possibilité de verrouiller des décors derrière des badges
(« si DJ6 le retient »). Ce lot a eu les badges en main et **ne verrouille rien** : verrouiller
aujourd'hui **retirerait aux joueurs un choix qu'ils ont déjà**, et DJ6 dit « sans saison ni perte de
points ». Les six décors restent disponibles ; la vitrine les montre avec celui du joueur mis en
avant. `docs/jeu/DECORS.md` passe donc de « ce qui n'est pas fait » à une décision datée.

## Preuves d'exécution

Tout sur la flotte, rien sur le Mac de JF.

| Suite | Où | Résultat |
|---|---|---|
| moteur `pbm_game` (ruff + pytest) | chimera, WSL | **1167 passés**, ruff « All checks passed! » |
| le test du fait de jeu, **sans** le changement | devAI (copie jetable) | **8 échecs** — puis 26 passés avec, dont les 18 tests existants du récapitulatif |
| API (ruff) | chimera, WSL | « All checks passed! » |
| API `test_jeu_profil.py` | chimera, WSL | **20 passés** |
| API suite complète | chimera, WSL | **1561 passés**, 2 échecs d'environnement (voir ci-dessous), 5 min 01 |
| `alembic upgrade head` sur base neuve | chimera, WSL | migration `d7f2a9c3e1b6` appliquée, **une seule tête** |
| front `vitest` (suite complète) | devAI | **963 passés** (102 fichiers), 3 passages consécutifs verts |
| front `tsc --noEmit` | devAI | **0 erreur** |
| front `next build` | devAI | build complet, route `/jeu/profil` présente (6,03 kB) |

⚠️ **Les deux échecs de l'API sont environnementaux, pas des régressions** :
`test_catalogue_seed.py` échoue sur `pg_dump: command not found` — le client PostgreSQL n'est pas
installé dans la WSL de chimera. La CI, elle, en dispose. Rien dans ce lot ne touche au catalogue.

⚠️ **Un flottement observé une fois sur quatre** sur la suite front : au premier passage complet,
`partie-view.test.tsx` (« affiche l'écran de fin ») a échoué sur un `expect(spy).toHaveBeenCalledWith`
— puis trois passages complets consécutifs sont verts, et le test passe isolément. Ce lot ne touche
ni `partie-view` ni `lib/api/games.ts` ; l'ajout de sept tests change seulement l'ordonnancement.
C'est donc un test sensible au temps, pas une régression — mais il est signalé ici plutôt que passé sous silence.

## Écarts au plan

- **La liste des badges n'a pas été arrêtée « avec JF et Aymeric »** : la session est autonome,
  personne ne répond. La liste livrée est **celle de la fiche du lot**, sans ajout ni retrait, et
  elle attend un mot de JF. Retirer un badge = retirer une entrée de `BADGES` (aucune migration,
  aucune ligne détruite — la vitrine n'affiche que les badges déclarés).
- **Aucun rattrapage rétroactif.** Les badges mérités avant ce lot ne sont pas reconstruits : quatre
  sur cinq se rattrapent tout seuls à la prochaine partie (leurs conditions relisent l'historique
  complet), le cinquième dépend d'un journal peut-être déjà purgé. Un script qui inventerait des
  dates aurait été pire ; c'est écrit dans `docs/jeu/PROFIL.md`.
- **Pas de recette `release_prod`** : ce lot ne déploie rien (la PROD se livre à part, par devAI).

## Reste à faire

- **Un mot de JF sur deux points** : la liste des cinq badges (confirmer ou retirer), et s'il
  souhaite allumer la vitrine — `python -m pbm_api.admin set-reglage-jeu badges_actifs oui` sur le
  serveur, sans redéployer.
- **Livraison en PROD** avec la migration `d7f2a9c3e1b6` (table `player_badges` + colonne
  `users.carte_fetiche_card_id`), à faire par devAI selon `docs/LIVRAISON.md`.
- **Un parcours e2e à deux navigateurs** montrant les deux cartes fétiches à l'écran du lancement :
  il n'existe pas d'écran de lancement côté front (les routes `/lancements/*` n'ont aucune page), le
  critère est donc tenu par le test HTTP de bout en bout. Le jour où cet écran existera, le lot qui
  le fera aura la donnée déjà dans la vue — et c'est là que le parcours e2e aura un sens.
