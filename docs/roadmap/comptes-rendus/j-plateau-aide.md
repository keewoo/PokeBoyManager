# Compte rendu — `j-plateau-aide`

**Aide en jeu : pourquoi je ne peux pas faire ça, et que puis-je faire.** Explication de chaque refus
du moteur en français d'enfant, coups proposés à qui hésite, première partie guidée, glossaire des
mots du jeu. Jalon J3, piste Interface de jeu (couloir J-UI), palier 15.

## Résumé

Le moteur refuse un coup en **citant une règle** du corpus (`pbm_game.actions.refus` l'exige, un
refus muet lève). Jusqu'ici le joueur recevait cette citation brute : « Le coût de l'attaque n'est pas
payé. (R-9.2) ». Ce lot ajoute, **entièrement côté `apps/web`**, la traduction de ces règles pour un
enfant de onze ans, et la garde côté moteur qui empêche l'aide de dériver du corpus.

- **Module pur** `apps/web/src/lib/game/aide.ts` — 26 explications (`titre`, `explication`,
  **`alternative`** : ce qu'on peut faire à la place), 28 mots de glossaire, `suggestions(vue)` qui
  ordonne les coups légaux du serveur dans un ordre pédagogique, et `expliquerRefus()` qui lit **les
  deux formes** de refus du serveur (champs séparés du grisage, chaîne `detail` fondue du 422).
- **Module pur** `apps/web/src/lib/game/guide.ts` — les 5 étapes de la première partie (poser l'Actif,
  remplir le banc, attacher une énergie, attaquer, prendre une récompense), `avancerGuide()` qui
  **constate** la progression sur la vue sans jamais reculer, et la mémoire du navigateur
  (`estPremierePartie` / `marquerGuideVu`, stockage **injecté** donc testable).
- **Tiroir** `apps/web/src/components/game/aide-panel.tsx` — `fixed`, replié, **en haut à gauche**, et
  qui **s'ouvre de lui-même sur un refus** : un enfant ne va pas chercher l'aide.
- **Câblage** : `game-board.tsx` monte le tiroir (uniquement sur un plateau jouable) et lui passe la
  vue et la raison du dernier refus — et **aucune fonction de jeu** ; `partie-view.tsx` tranche une
  fois au montage si c'est une première partie.
- **Garde de parité** `apps/game/tests/test_parite_aide_front.py` — relève par **analyse syntaxique**
  (`ast`) la règle citée par chaque refus de tout `pbm_game`, et **casse la CI** (job `game`) si l'une
  n'a pas d'explication, ou si l'aide cite un identifiant absent de `docs/jeu/REGLES.md`.

**Aucune route, aucune table, aucune migration, aucun appel réseau ajouté** : tout se déduit de la vue
que le serveur envoie déjà. Le moteur n'a pas été modifié — il reste pur.

## Critères d'acceptation

- [x] **Chaque raison de refus produite par le moteur a son explication en français simple.**
  Prouvé *mécaniquement*, pas déclaré : `test_parite_aide_front.py` extrait par `ast` les 24
  citations distinctes des refus de `pbm_game` (23 règles `R-x.y` + la section `R-5`) et exige que
  chacune ait son entrée dans `EXPLICATIONS`. Vérification que la garde **mord** — en retirant la
  seule entrée `R-9.2`, le test échoue en nommant la règle *et* le fichier moteur fautif :
  `{'R-9.2': ['apps/game/src/pbm_game/combat/cout.py']}` (2 failed, 2 passed).
- [x] **La première partie guidée se termine sans aide extérieure.** `guide.test.ts` rejoue la suite
  des états qu'un débutant produit en suivant les consignes et vérifie qu'à chaque pas le guide
  reconnaît l'étape franchie et désigne la suivante, jusqu'à `termine: true` — **jamais de
  cul-de-sac**. Deux pièges couverts : le guide **ne recule pas** quand l'Actif adverse blessé est
  remplacé (ses dégâts disparaissent de la vue), et il **retrouve sa place** après un F5 en lisant le
  seul plateau. ⚠️ Prouvé mécaniquement, **pas encore humainement** — voir « Reste à faire ».
- [x] **L'aide ne joue jamais le coup à la place du joueur.** Tenu par la **structure**, pas par une
  intention : une `Suggestion` ne porte pas les `params` du coup (test : ses seules clés sont
  `etiquette`, `pourquoi`, `type`), le composant ne reçoit **aucune** fonction de jeu en props, et les
  coups sont rendus en lignes de texte (`queryAllByRole("button")` = 0 dans la liste). Un test clique
  **tous** les boutons du tiroir deux fois de suite et vérifie qu'aucun appel réseau ne part.

## Preuves (recette locale)

Les suites front ont tourné **sur devAI** : chimera n'a ni `node` ni `pnpm` dans sa WSL (constat déjà
consigné). Atelier jetable monté par `git archive` dans `/tmp` (clonage APFS des `node_modules`, coût
disque ~nul), supprimé à la fin. **La CI GitHub Actions fait foi.**

| Contrôle | Commande | Résultat |
|---|---|---|
| Moteur — parité de l'aide | `uv run pytest tests/test_parite_aide_front.py -q` | **4 passed** |
| Moteur — suite complète | `uv run pytest -q` (`apps/game`) | **1138 passed** |
| Moteur — lint | `uv run ruff check .` (`apps/game`) | All checks passed |
| Front — types | `tsc --noEmit` | aucune erreur |
| Front — lint | `eslint src` | **0 erreur** (1 avertissement préexistant dans `game-realtime.test.ts`, non touché) |
| Front — mes suites | `vitest run aide.test.ts guide.test.ts aide-panel.test.tsx` | **42 passed** (20 + 7 + 15) |
| Front — suite complète | `vitest run` | **473 passed**, 15 échecs **préexistants** |

**Les 15 échecs sont préexistants et étrangers au lot** : les trois fichiers `app-shell*.test.tsx`
tombent dans `theme-provider.tsx:12` (`window.localStorage` indisponible sous le Node 26 local, la CI
est en 24) — déjà consigné en mémoire de projet. Vérifié : aucun de ces trois fichiers n'importe,
même transitivement, un fichier que ce lot touche (leurs imports sont `AppShell`, `ThemeProvider`,
`api/decks`, `api/profile`).

### Un défaut attrapé avant la CI, qui valait le détour

Le tiroir d'aide était d'abord posé **en haut à droite** — le réflexe pour un bouton d'aide. Sur
l'écran de référence du jeu (**844 × 390**, téléphone en paysage) il recouvre `anim-sauter`
(`animation-layer.tsx`, `absolute right-2 top-2 z-30`), que `e2e/anim-fluidite.spec.ts:267` **clique**
réellement : Playwright aurait échoué sur une interception de clic — et **ni vitest ni `tsc` ne
l'auraient vu**, le mode de panne que ce dépôt connaît déjà. Trouvé en inventoriant les `.click()` des
specs e2e du plateau avant de choisir le coin.

Corrigé : tiroir **en haut à gauche** (seul coin libre — le statut de connexion est centré) et borné à
`15rem`, pour laisser tout le flanc droit de l'arène cliquable en paysage comme en portrait. Un test
de `aide-panel.test.tsx` garde les trois invariants (hors du flux, ancré à gauche, largeur bornée)
**avec le message qui explique la conséquence**, pour que le prochain lot ne les redécouvre pas par
une CI rouge. La carte des quatre coins du plateau est dans `docs/jeu/AIDE.md`.

Bénéfice secondaire : `GameBoard` montant désormais le tiroir, l'e2e `plateau-responsive` (« aucun
défilement de `/jeu/parties/{id}` ») **l'exerce gratuitement** — c'est la preuve e2e que le panneau ne
rallonge pas la page.

## Livrables

- `apps/web/src/lib/game/aide.ts` + `aide.test.ts` — explications, glossaire, suggestions, lecture des
  refus.
- `apps/web/src/lib/game/guide.ts` + `guide.test.ts` — parcours de la première partie, mémoire.
- `apps/web/src/components/game/aide-panel.tsx` + `aide-panel.test.tsx` — le tiroir.
- `apps/game/tests/test_parite_aide_front.py` — la garde corpus ↔ aide ↔ moteur.
- `apps/web/src/components/game/game-board.tsx`, `apps/web/src/app/jeu/parties/[id]/partie-view.tsx` —
  câblage (deux props ajoutées, aucune logique de règle déplacée).
- `docs/jeu/AIDE.md` (fiche neuve), `docs/UI-UX.md` (§ Aide en jeu), `CLAUDE.md` (une ligne dans la
  carte des fiches).

## Écarts au plan

1. **Mission 4 — « relire les textes avec JF » — non faite.** Le lot dit lui-même : « c'est le lot où
   le ton compte plus que le code ». Les 26 explications, 28 mots et 5 consignes sont écrits depuis le
   corpus et testés pour leur *forme* (longueur, présence d'une alternative, aucun numéro de règle
   montré au joueur), mais leur **ton** n'a pas été validé. Une session autonome ne peut pas tenir
   cette relecture : elle attend JF.
2. **Quatre refus du moteur citent une SECTION, pas une règle.** `pbm_game/actions/familles_jeu.py`
   (famille « talent », autour de la ligne 1263) appelle `refus("R-5", …)` alors que le docstring de
   `Verdict` annonce un identifiant `R-x.y`. Leurs propres messages, eux, nomment la règle précise
   (« … (R-5.1). »). **Je n'ai pas corrigé le moteur** : choisir entre `R-5.1`, `R-5.3` et R-12.3 pour
   ces quatre sites est un jugement sur une famille que ce lot ne porte pas, et le changement n'est
   pas couvert par un test existant. L'aide explique donc le niveau cité tel qu'il est (entrée `R-5`,
   « Chaque chose à son moment du tour »), et le détail précis reste porté par le message du moteur
   affiché juste au-dessus. **Décision attendue de JF** : resserrer les quatre citations, ou acter que
   `regle` peut porter une section.
3. **Aucun nouveau test e2e.** Playwright est injouable en local (constat du dépôt : la CI fait foi) ;
   ajouter une spec que je ne peux pas exécuter, c'est risquer une CI rouge sans savoir pourquoi. La
   propriété e2e qui compte — « le panneau n'allonge pas la page » — est couverte gratuitement par
   `plateau-responsive`, qui rend maintenant le tiroir. La capture d'écran demandée au § 7 du prompt
   n'a donc pas été produite.
4. **`/Volumes/Data` refusé en écriture** depuis cette session (`Operation not permitted`, TCC), alors
   que le volume est monté avec 125 Gio libres. Conformément à la règle de flotte, je le **dis** au
   lieu de replier en silence : l'atelier jetable est passé par `/tmp` (628 Mio en clone APFS, donc
   quasi aucun octet réellement écrit), et il a été supprimé. À régler par JF dans *Confidentialité et
   sécurité*.

## Reste à faire

- **Relecture des textes avec JF** (écart 1) — et, idéalement, un enfant de onze ans qui fait la
  partie guidée sans aide : c'est le seul moyen de prouver *humainement* le 2ᵉ critère.
- **Trancher les quatre citations `R-5`** (écart 2).
- **Relier une explication à son glossaire.** `motsDuTexte()` sait repérer les mots du jeu dans un
  texte (sur le mot entier : « Objet » ne se déclenche pas sur « objectif ») et chaque explication
  déclare ses `mots`, mais le tiroir ne rend pas encore ces mots cliquables depuis l'explication.
- **Le délai d'hésitation (12 s) n'est pas réglable par le joueur.** Suffisant pour un premier
  passage ; à revoir si JF trouve l'aide bavarde ou trop lente.

## Tâches du lot

| Tâche | État | Preuve |
|---|---|---|
| `dev` | fait | `aide.ts`, `guide.ts`, `aide-panel.tsx` + câblage `game-board.tsx` / `partie-view.tsx` |
| `tests` | fait | 42 tests front + 4 de parité moteur ; garde vérifiée **mordante** (entrée retirée → échec nommant la règle et le fichier) |
| `securite` | fait | **aucune route, aucune table, aucun secret** : rien à filtrer par `user_id`, donc aucun test d'accès croisé à ajouter. Tout dérive de la vue déjà projetée pour `vue.pour`, dont l'isolation est garantie en amont (`_game_pour_participant`, 404 pour un non-participant). Aucun identifiant ni message serveur journalisé côté client |
| `maquette` | partiel | jetons et idiomes du dépôt réutilisés (`pbm-surface`, `text-gold`, tiroir `fixed` replié sur le motif de `journal-panel`) ; **pas de capture** (e2e injouable en local) |
| `doc_tech` | fait | `docs/jeu/AIDE.md`, `docs/UI-UX.md` § Aide en jeu, `CLAUDE.md` (carte des fiches) |
| `release_uat` | partiel | recette locale complète (tableau ci-dessus) mais **sur devAI**, pas sur chimera : sa WSL n'a ni `node` ni `pnpm` |
| `release_prod` | non fait | **aucun déploiement** — hors périmètre du lot, la PROD se livre à part par devAI |
| `backlog` | n/a | l'état est tenu par la file de lots ; ce compte rendu remplace les commandes `suivi.py` |
| `compte_rendu` | fait | ce fichier |
