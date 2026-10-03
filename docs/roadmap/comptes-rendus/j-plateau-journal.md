# Compte rendu — `j-plateau-journal`

**Journal de partie : ce qui vient de se passer, en français.** Fil des coups traduit, relié au
plateau, avec filtres et détail du calcul des dégâts. Jalon J1, piste Interface de jeu (couloir
J-UI), exécuté sur **chimera**.

## Résumé

Le moteur `pbm_game` produit, pour chaque coup, une suite d'événements `{type, donnees}` que le
serveur projette par destinataire (`pbm_game.sortie`) et diffuse au client (`Coup = {numero,
evenements}`). Ce lot ajoute, **côté `apps/web`**, la traduction de ce flux en un **fil lisible** et
son panneau, sans toucher au moteur (qui reste pur) ni au serveur.

- **Module pur** `apps/web/src/lib/game/journal.ts` : un registre `TRADUCTEURS` (un traducteur par
  type d'événement) → `construireJournal(coups, pour)` aplatit les coups diffusés en lignes
  françaises, chacune portant sa catégorie (moi / adversaire / effet automatique), le détail du
  calcul des dégâts le cas échéant, et l'`instance_id` du Pokémon à mettre en évidence.
- **Panneau** `apps/web/src/components/game/journal-panel.tsx` : fil escamotable (téléphone), dernier
  coup en tête et mis en évidence, trois filtres indépendants, détail des dégâts consultable à la
  demande, et **reliure journal ↔ plateau** par le survol.
- **Câblage** `partie-view.tsx` : accumulation des coups diffusés (dédupliqués par numéro, reconstruits
  au F5), état `surligne` relié à `GameBoard` (nouvelle prop `surligne`, réutilise le halo).
- **Garde de parité** `apps/game/tests/test_parite_journal_front.py` : tout événement projetable
  (`PROJECTEURS`) doit avoir sa traduction TS — sinon la CI (job `game`) **casse**. C'est le « test
  qui échoue sur un événement non traduit » exigé par le lot, tenu au point de vérité.

## Critères d'acceptation

- [x] **Chaque événement du moteur a sa formulation française — aucun `event_type` brut affiché.**
  Les 17 types de `PROJECTEURS` ont leur traducteur (`journal.test.ts` le vérifie type par type) ;
  un type inconnu produit une ligne `traduit:false` montrée en rouge (jamais masquée), et le test de
  parité garantit la couverture en CI.
- [x] **Le détail du calcul des dégâts est consultable pour chaque attaque.** `EVT_DEGATS` porte le
  `detail` (R-10.9) ; le panneau l'affiche sous un bouton « détail » (`detail-degats`).
- [x] **Les effets automatiques apparaissent au journal.** Poison/brûlure/sommeil/paralysie au
  Checkup (`etat_checkup`), expiration d'un effet (`effet_expire`), K.O. (`ko`), changement de phase
  et fin de partie sont traduits et isolables par le filtre « Effets auto ».

## Preuves (recette locale sur chimera)

- Web : `pnpm --filter @pbm/web lint` (0 erreur), `type-check` (vert), `test` → **259 tests passés**
  (dont `journal.test.ts` et `journal-panel.test.tsx`), `build` (vert).
- Game : `uv run ruff check .` (vert), `uv run pytest tests/test_parite_journal_front.py` → **1 passé**.
- La CI GitHub Actions fait foi : voir le passage « CI » sur le push de la branche
  `roadmap/j-plateau-journal` (le job `web` rejoue lint/type-check/test/build, le job `game` la parité).

## Tests ajoutés

- `journal.test.ts` : une phrase française pour chaque type connu (et aucun identifiant brut dans la
  phrase) ; couverture = clés du registre ; repli `traduit:false` visible ; catégories moi/adversaire/
  auto ; détail + cible à surligner ; non-fuite de la pioche adverse ; déduction du camp des dégâts
  depuis l'auteur du coup. **Échoue sans le module** (il n'existait pas).
- `journal-panel.test.tsx` : ordre anti-chronologique + dernier coup, filtres, détail consultable,
  survol → `onSurvol`, ligne non traduite toujours visible, escamotage.
- `test_parite_journal_front.py` (job `game`) : échoue si un événement projetable n'a pas sa
  traduction front.

## Écarts au plan

- **Pas d'image réelle en vignette.** Le moteur ne transmet que des `instance_id`/`ref` (pas les noms
  ni les images de carte) ; le plateau lui-même n'affiche encore que la `ref` (texte). Le fil nomme
  donc ce que l'événement porte (une `ref`, un nom d'évolution) et **relie** chaque ligne à la carte
  du plateau par la surbrillance au survol. L'image réelle en vignette reste le lot aval
  `j-rendu-carte` (D9 : on ne fabrique pas d'image qu'on n'a pas). Le modèle de ligne porte déjà les
  `refs` concernés, prêts pour ce lot.
- **`EVT_EFFET_EXPIRE` est vide au jalon J1** (aucun effet temporaire) : sa traduction existe et est
  testée, mais il n'apparaîtra qu'avec les effets temporaires des lots de cartes.

## Reste à faire (aval)

- `j-rendu-carte` : vignette d'image réelle dans le fil (le modèle expose déjà `refs`).
- `j-partie-fin-ui` et `j-plateau-aide` (débloqués par ce lot) consommeront les mêmes lignes/traductions.

## Documentation

`docs/UI-UX.md` § « Journal de partie — le fil des coups en français (lot `j-plateau-journal`) ».
