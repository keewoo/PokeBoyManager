# Actions légales — `pbm_game.actions`

> Livré par le lot `j-actions-legales` (jalon J1). Le code vit dans
> `apps/game/src/pbm_game/actions/`. Cette fiche documente **le contrat et le périmètre** :
> ce que le moteur déclare jouable, comment un refus se motive, et comment les lots suivants
> y branchent leurs familles d'actions sans jamais rien approximer.

## Pourquoi

L'interface ne doit **pas** connaître les règles du jeu. Elle affiche la liste des coups que
le moteur lui donne, et, quand un coup est refusé, elle montre **la raison** — pas un bug.
Les bots se servent de la même liste. D'où deux fonctions, et elles seules portent la
légalité :

| Fonction | Rend |
|---|---|
| `actions_legales(etat, joueur)` | la liste **exhaustive** des coups jouables par `joueur`, chacun avec son **étiquette lisible** et ses **cibles valides** (`tuple[ActionLegale, ...]`) |
| `valider(etat, action)` | un `Verdict` : soit l'accord, soit un **refus motivé** par une règle citée (`R-14.6 : la partie est terminée`) |

**Toute action passe par `valider`, y compris celles venues du serveur** (principe « le
serveur fait autorité » du jalon J1).

## Une seule source de vérité : la liste

Le piège de ce lot est de **dédoubler la logique** entre « je liste ce qui est jouable » et
« je valide ce qu'on me propose » : les deux divergent inévitablement. On l'évite ainsi :

- `valider(etat, action)` recalcule `actions_legales` **depuis l'état qui fait autorité** et
  vérifie l'**appartenance** de `action` à cette liste. L'égalité se fait sur l'`Action`
  entière (type, auteur, params) ;
- si l'action appartient à la liste → **accord** ;
- sinon, la famille qui gouverne ce type d'action **explique** le refus en citant la règle
  qui bloque. Expliquer n'est pas re-décider : la légalité reste décidée au seul endroit où
  la liste est produite.

Un test de cohérence (`test_actions_legales.py`) garde l'équivalence
`valider(etat, a).accepte ⇔ (a ∈ actions_legales(etat, a.auteur))` pour toujours.

## Les objets

- **`Cible`** — une cible valide d'une action, **calculée depuis l'état**, jamais depuis
  l'écran : `genre` (`joueur`, `pokemon_en_jeu`, `carte_main`…), `reference` (identifiant
  stable : `instance_id` ou id de joueur), `etiquette` lisible.
- **`ActionLegale`** — un coup jouable : l'`Action` exacte à journaliser, son `etiquette`, et
  ses `cibles` (vide quand le coup n'en a pas, comme « abandonner »).
- **`Verdict`** — `accepte` ; sinon `regle` (un `R-x.y` du corpus `REGLES.md`) + `message`
  lisible. Un refus **sans** règle citée est interdit : le constructeur `refus()` lève si la
  règle ou le message manque (pas de refus muet — interdiction du repli silencieux).

## Périmètre au palier 4 — ce qui est jouable aujourd'hui, et ce qui attend son lot

Le moteur ne connaît **pas encore** les données de carte (type, coût, attaques, évolutions,
coût de retraite) : elles arrivent avec `j-cartes-pokemon` et les lots de résolution. Ce lot
livre donc le **cadre** complet (liste, validation, cibles, registre de familles) et les
seules familles qui ne demandent **aucune** donnée de carte :

| Famille | Qui | Règle | Cibles |
|---|---|---|---|
| **avancer la phase / terminer le tour** | le joueur **actif** | R-5.1 | aucune |
| **abandonner** | **tout** joueur, à tout moment | R-14.3 | aucune |

Une partie **terminée** est figée (R-14.6) : `actions_legales` rend `()` et `valider` refuse
tout.

**Ce qui n'est PAS généré, et pourquoi** (D9 — un effet non implémenté n'est jamais
approximé) : poser un Pokémon de base, faire évoluer, attacher une énergie, jouer un
Objet/Supporter/Stade/Outil, utiliser un talent, battre en retraite, déclarer une attaque,
répondre à une demande de décision. Chacune a besoin de données de carte ou d'un mécanisme
(décisions) qui n'existent pas encore. Le jeu préfère dire « je ne sais pas encore proposer
ce coup » que de le proposer de travers.

Les types d'action **mécaniques mais non libres** sont refusés en nommant leur règle :
`piocher` et `debut_tour` (R-5.2 : la pioche de début de tour est automatique, action
système), `melanger_pioche` (R-4.1 : mise en place). Un type inconnu, ou pas encore scripté
comme coup jouable, est refusé par **D9 / R-15.12** — c'est le cas de `declarer_attaque`, dont
le coup complet (coût, dégâts) attend `j-degats-resolution`.

> ℹ️ Depuis `j-machine-tour`, `avancer_phase` est proposé à chaque phase d'une partie vivante
> **sauf pendant la pioche** : on ne quitte pas la phase de pioche manuellement, c'est la
> pioche obligatoire de début de tour (action système `debut_tour`, R-5.2) qui s'en charge.
> Le reste du déroulé d'un tour (pioche obligatoire, défaite sur pioche impossible, attaque qui
> termine le tour, règle du premier tour, drapeaux « une fois par tour ») est documenté dans
> `docs/jeu/MACHINE-TOUR.md`.

## Le point d'extension — comment un lot de résolution branche sa famille

Comme `journal.transitions.REGISTRE` pour les transitions, la source unique des coups est le
tuple `FAMILLES_DEFAUT`. Un lot qui dispose du catalogue ajoute une sous-classe de `Famille` :

```python
class Famille(ABC):
    nom: str
    def gouverne(self, action) -> bool: ...      # ce type d'action m'appartient-il ?
    def generer(self, etat, joueur) -> list[ActionLegale]: ...   # les coups légaux
    def refuser(self, etat, action) -> Verdict: ...             # pourquoi CE coup est refusé
```

Règles pour une famille saine :

1. **`generer` est le seul juge de la légalité.** `refuser` ne fait que citer la règle qui
   bloque un coup que `generer` n'a pas produit — il ne re-décide rien.
2. **Les cibles se calculent depuis l'`etat`**, jamais depuis un paramètre venu de l'écran.
3. **Aucune approximation (D9).** Une carte dont l'effet n'est pas scripté et testé ne doit
   produire aucun coup — elle est refusée au deck en amont, pas jouée de travers ici.
4. Les lots qui ont besoin des données de carte recevront l'accès au catalogue par le
   paramètre de `generer` (à introduire par le premier lot qui en a besoin — pas avant, pour
   ne pas livrer d'abstraction non exercée).

`actions_legales(etat, joueur, familles=…)` et `valider(etat, action, familles=…)` acceptent
une liste de familles **uniquement** pour composer un sous-ensemble ou injecter une famille
de test ; par défaut c'est `FAMILLES_DEFAUT`, la vérité.

## Ce que ce lot débloque

- `j-machine-tour` — déroulé d'un tour : phases, contraintes du tour, fin de tour ;
- `j-plateau-interactions` — l'interface qui affiche la liste, les cibles, l'annulation et
  la confirmation, et montre la raison d'un refus.

## Servir les actions au client (lot `j-plateau-interactions`)

La vue autoritaire (`GET /games/{id}/state` et le canal temps réel) porte, pour son destinataire,
deux listes issues du moteur — l'adaptateur `pbm_api.games.actions.actions_pour` les sérialise, **sans
réécrire aucune règle** :

- `vue.actions_legales` :
  `[{type, params, etiquette, cibles: [{genre, reference, etiquette}], irreversible}]` — les coups
  jouables (source : `pbm_game.actions.actions_legales`). L'écran illumine `cibles` et soumet
  `type`/`params` tels quels.
- `vue.actions_refusees` : `[{type, params, etiquette, regle, message, irreversible}]` — les commandes
  de la palette d'interface non jouables dans l'état courant, avec le motif du moteur
  (`pbm_game.actions.valider`). L'écran les grise en montrant `regle` + `message` ; jamais un refus muet.

`irreversible` est une **politique d'affichage** dérivée de l'état côté serveur (jamais une règle
rejouée par le client) : l'écran demande confirmation d'un coup qui ne s'annule pas — abandonner
(R-14.3), terminer le tour (R-5.1 / R-5.7), et plus tard attaquer / défausser.

L'enveloppe de réponse (`/state` et un coup joué) porte aussi `numero` : le prochain numéro d'action
attendu, clé d'**idempotence** quand le client soumet un coup (`POST /games/{id}/actions`, champ
`numero_attendu`) — renvoyer deux fois le même coup au même numéro ne le joue qu'une fois.

## Mise à jour `j-coups-joueur` — les familles du jeu sont livrées

Le périmètre ci-dessus décrivait le **cadre** (palier 4) : seules `avancer_phase` et `abandonner`
étaient générées, et poser / évoluer / attacher / attaquer / retraite / promotion attendaient leur
lot. **`j-coups-joueur` les livre**, dans un module séparé — `pbm_game.actions.familles_jeu` — qui
ne touche pas `FAMILLES_DEFAUT` (le générateur garde son comportement sans catalogue, celui que
testent les milliers d'états de `test_actions_legales`).

| Famille | Action | Règle | Cibles |
|---|---|---|---|
| `FamillePlacer` | `placer_mise_en_place` | R-4.2 | — (choix de l'Actif ; banc auto, J1) |
| `FamillePoser` | `poser` | R-5.3 | — (carte de main) |
| `FamilleEvoluer` | `evoluer` | R-7.1 | le Pokémon à faire évoluer |
| `FamilleAttacherEnergie` | `attacher_energie` | R-5.4 | le Pokémon qui reçoit l'énergie |
| `FamilleAttaquer` | `declarer_attaque` | R-9/R-10/R-13 | l'Actif adverse |
| `FamilleRetraite` | `retraite` | R-8.2 | le Pokémon du banc qui monte |
| `FamillePromouvoir` | `promouvoir` | R-8.7 | le Pokémon du banc à promouvoir |

Ces familles **ont besoin du catalogue** : un `CatalogueJeu` (`ref → DefinitionCarte` /
`DefinitionEnergie`) construit à la création de la partie et passé par le service — le moteur reste
pur. Une carte dont la définition manque **ne produit aucun coup** (D9). Le service les assemble par
`familles_jeu(catalogue)` et les passe à `actions_legales` / `valider` : `actions_pour` sert alors la
liste **complète** dans la vue (`GET /state` et temps réel).

**Côté serveur (autorité).** Une partie *jouable* (mise en place entamée ou commencée) valide tout
coup soumis par **appartenance** à `actions_legales` recalculée depuis l'état : un coup hors liste —
ou aux paramètres falsifiés — est refusé (anti-triche). L'enchaînement entre les tours (pioche de
début de tour, Pokémon Checkup, passage au tour suivant) est joué **par le serveur**, tout par le
journal. Détail : `docs/roadmap/comptes-rendus/j-coups-joueur.md`.
