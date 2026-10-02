# EFFETS.md — l'architecture d'effets du moteur de jeu

> Lot `j-effets-architecture` (jalon J2). Paquet `pbm_game.effets`, **pur** (aucune E/S), comme
> tout le moteur. Ce document décrit le *cadre* qui accueille toutes les cartes — il ne script
> aucune carte (D9) : chaque effet réel est ajouté, scripté et testé, par un lot de cartes.
> Les règles citées (`R-x.y`) renvoient à `docs/jeu/REGLES.md`.

## Pourquoi un cadre, et pas du code par carte

Un moteur qui traite les effets « au fil de l'eau » se réécrit à la première carte qui dit
« votre adversaire ne peut pas ». Le cadre sépare quatre questions, chacune dans son module :

| Question | Module | Pièce maîtresse |
|---|---|---|
| **Quand** un effet se déclenche-t-il ? | `effets/evenements.py` | `EvenementJeu`, `EVENEMENTS_JEU` |
| Dans **quel ordre** plusieurs effets se résolvent-ils ? | `effets/pile.py` | `PileEffets`, `resoudre_pile` |
| Comment un effet **permanent** agit-il sans salir l'état ? | `effets/continus.py` | `EffetContinu`, `collecter_effets_continus` |
| Comment **interdire** un coup, et pour combien de temps ? | `effets/verrous.py` | `Verrou`, `JeuDeVerrous` |
| Comment tout cela **se branche** sur le moteur ? | `effets/bus.py` | `Bus`, `declencheur_fenetre` |

Une sixième question — **comment un effet attend-il la décision d'un joueur** (y compris
l'adversaire) sans bloquer un fil ? — a sa fiche propre : `docs/jeu/DEMANDES.md` (lot
`j-effets-choix`, paquet `pbm_game.demandes`). La pile y gagne une résolution **suspendable** :
elle pose la demande dans l'état et reprend à la réponse.

## Les onze moments de jeu (le bus d'événements)

Un **événement de jeu** est un *moment* : « des dégâts viennent d'être posés », « un Pokémon
entre en jeu ». Il ne faut pas le confondre avec l'`Evenement` du journal, qui est la *trace*
de ce qui a été fait. Les onze moments, dérivés d'un dépouillement de 200 cartes porteuses
d'effet du catalogue (voir « L'étude des 200 cartes » plus bas) :

`debut_tour`, `fin_tour`, `entre_tours` (le Pokémon Checkup, R-12.1), `avant_degats`,
`apres_degats`, `pose` (R-5.3), `evolution` (R-7.1), `ko` (R-13.1), `attachement_energie`
(R-5.4), `pioche` (R-5.2), `devient_actif` (R-8 — indispensable aux appâts, fiche
`j-cartes-objets`).

La liste est **fermée** (D9) : publier un moment inconnu lève une erreur. La compléter impose
de refaire l'étude de couverture (`apps/game/tools/classer_echantillon.py`) et de regeler
l'échantillon — le test `test_effets_echantillon` l'exige.

Tous les effets ne sont pas « déclenchés par un moment ». Trois **mécanismes** vivent ailleurs,
et le cadre les porte aussi, pour ne jamais forcer un effet dans un faux événement :

- **continu** — un modificateur consulté au calcul, tant que sa source est en jeu ;
- **activé** — une action du joueur à son tour (« une fois pendant votre tour… ») ;
- **attaque** — un effet porté par une attaque, résolu *pendant* l'attaque (entre
  `avant_degats` et `apres_degats`), ses sous-effets relevant du langage d'effets
  (`j-effets-dsl`).

## La pile d'effets (dernier entré, premier sorti)

Quand plusieurs effets attendent, l'ordre n'est pas « celui où le code a été écrit » : c'est
une **pile**. Le dernier effet empilé se résout en premier, et peut lui-même en empiler
d'autres qui passeront avant lui — c'est ce qui permet aux **interruptions** d'exister (un effet
« en réaction » s'empile au-dessus de celui qu'il interrompt). `resoudre_pile` :

1. ouvre une **fenêtre d'interruption** (optionnelle) où des effets réactifs peuvent s'empiler ;
2. **dépile le sommet** et le résout via son résolveur du `RegistreEffets` ;
3. **journalise** la résolution avec sa **source** (`EVT_EFFET_RESOLU` → « à cause de l'Outil X »)
   *avant* les événements propres de l'effet — le critère d'acceptation l'exige ;
4. récupère les effets que le résolveur empile à son tour, et continue jusqu'à l'épuisement.

Deux garde-fous : un `type_effet` absent du registre est **refusé** (D9, jamais deviné) ; un
effet sans cible valide **ne bloque pas** la partie — il le **dit** (`EVT_EFFET_SANS_CIBLE`),
jamais un repli muet. Une chaîne qui s'emballe s'arrête **bruyamment** (garde anti-boucle).

La pile est immuable et sérialisable : au lot `j-effets-choix`, un effet pourra s'y
*suspendre* en attendant la décision d'un joueur, et la pile fera alors partie de l'état repris
après un F5.

## Les effets continus (des modificateurs, jamais des mutations)

**Un effet continu n'existe nulle part dans l'état ; il se *dérive* de ce qui est en jeu.**
`collecter_effets_continus(etat, registre)` relit le Stade, puis chaque Pokémon en jeu (son
talent, son Outil), et en tire des `Modificateur` (du socle `pbm_game.combat`). Comme la
collecte **ne lit que l'état courant**, retirer une source (Outil défaussé, Stade remplacé)
la fait disparaître au calcul suivant — le calcul **revient exactement à l'état antérieur**,
sans rien avoir à défaire. C'est vrai *par construction*, pas par discipline : c'est le piège
que la fiche nomme (appliquer l'effet en mutation au lieu de le consulter au calcul).

Deux sorties : `modificateurs_degats(effets, attaquant=…, defenseur=…)` donne les deux listes à
passer telles quelles à `resoudre_degats` (R-10.1) ; `seuil_ko(pv_imprime, effets, pokemon)`
donne le seuil de K.O. (R-13.1), que des PV continus (Outil) déplacent — leur retrait l'abaisse,
et peut provoquer un K.O. immédiat.

## Les verrous nommés (interdire un coup, et pour combien de temps)

Un **verrou** est une interdiction nommée qu'une carte pose : `pas_de_supporter` (R-5.5),
`ne_peut_attaquer` (R-5.7), `talents_sans_effet` (R-12.3), `pas_de_retraite` (R-8). Chacun porte
une **portée** qui dit quand il tombe : `ce_tour`, `prochain_tour` (expirent au Checkup, R-12.5,
chaque levée journalisée), `tant_que_actif`, `tant_que_stade`, `tant_que_en_jeu` (tombent avec
leur source). `JeuDeVerrous.est_verrouille(nom, cible=…)` est ce que les gardes des lots de
cartes consulteront avant d'autoriser un coup, et `source_du_verrou(…)` **nomme la carte
responsable** dans le refus — jamais un « interdit sans raison ».

## Comment ça se branche sur le moteur, sans le modifier

Le socle ouvre déjà des **fenêtres** (`pbm_game/tour/fenetres.py` :
`FENETRE_DEBUT_TOUR`, `FENETRE_FIN_TOUR`, `FENETRE_EXPIRATION_EFFETS`) et sait exécuter les
*déclencheurs* qu'on y enregistre — son docstring l'annonce. `declencheur_fenetre(bus, moment,
registre)` fabrique exactement ce déclencheur : à l'ouverture d'une fenêtre, il publie
l'`EvenementJeu` correspondant sur le bus, résout la pile, et rend les événements — **sans
toucher une ligne du socle**. On s'enregistre dans `pbm_game.tour.fenetres.DECLENCHEURS` (ou on
injecte via le paramètre `declencheurs` de `declencher` / `resoudre_checkup`, prévu pour cela).

Pour les moments que le socle n'ouvre pas encore de lui-même (dégâts, pose, évolution, K.O.,
attachement), ce sont les **lots de résolution** qui publieront sur le bus au bon endroit. Ce
lot ne câble pas ces publications dans le socle, exprès : ce serait le modifier, et le critère
d'acceptation n°4 l'interdit. Importer `pbm_game.effets` n'a donc **aucun effet de bord** :
le comportement du socle reste strictement inchangé tant qu'aucun effet n'est câblé.

---

## Trois exemples de bout en bout

### 1. Un Outil continu — Bandeau Musclé (+20 dégâts) et PV supplémentaires

Un lot de cartes (`j-cartes-outils`) enregistre un producteur pour la `ref` de l'Outil :

```python
def producteur_bandeau(etat, ref, cible):
    src = SourceEffet(libelle="Bandeau Musclé", ref=ref, instance_id=f"outil-{cible}")
    return [EffetContinu(
        libelle="Bandeau +20", regle="R-3.7", source=src, portee=PORTEE_OUTIL, cible=cible,
        modificateur=modificateur_ajout("Bandeau", "R-3.7", 20), face=FACE_ATTAQUANT,
    )]

registre = {"bandeau-muscle": producteur_bandeau}
```

Au calcul d'une attaque de base 50, l'Outil attaché :

```python
effets = collecter_effets_continus(etat, registre)                # lit pokemon.outil
att, deff = modificateurs_degats(effets, attaquant="a-1", defenseur="b-1")
resoudre_degats(base=50, modificateurs_attaquant=att).degats       # → 70
```

Défausser l'Outil (`replace(pokemon, outil=None)`), recalculer : `collecter_effets_continus`
ne le voit plus, `resoudre_degats(base=50)` redonne **50**. Le calcul est restauré sans qu'on
ait rien « retiré » — la source a disparu de l'état, point. (Testé :
`test_retrait_d_un_outil_restaure_exactement_le_calcul_r37`.)

### 2. Un talent déclenché — « Lorsque ce Pokémon est mis K.O. » via le bus et la pile

Un talent qui réagit au K.O. s'abonne au moment `ko` ; son réacteur **empile** son effet, qui
se résout par la pile — journalisé avec sa source :

```python
def reacteur_vengeance(etat, evenement, pile, rng):
    effet = EffetEnAttente(type_effet="pioche_2", libelle="Vengeance", regle="R-13.1",
                           source=SourceEffet("Gardevoir", ref="…", instance_id="g-1"))
    return pile.empiler(effet), []

bus = Bus().abonner(EJ_KO, reacteur_vengeance)
```

Le lot `j-ko-recompenses` publiera l'`EvenementJeu(EJ_KO, …)` au moment du K.O. ; le bus fait
réagir le talent, la pile se résout, et le journal porte un `EVT_EFFET_RESOLU` attribuant la
pioche **à Gardevoir**. Si le talent n'a pas de cible (deck vide), il le **dit**
(`EVT_EFFET_SANS_CIBLE`) sans bloquer. Le branchement sur une fenêtre réelle du socle est
démontré par `test_le_bus_se_branche_sur_la_fenetre_fin_de_tour_du_socle`.

### 3. Un verrou — « Pas de Supporter ce tour », posé, refusé en nommant la carte, expiré

Une carte pose le verrou sur l'adversaire pour le tour courant :

```python
verrou = Verrou(nom=VERROU_PAS_DE_SUPPORTER, portee=PORTEE_CE_TOUR,
                source=SourceEffet("Zone de Combat", …), regle="R-5.5",
                cible="bob", pose_au_tour=4)
verrous, evt_pose = JeuDeVerrous().poser(verrou)       # EVT_VERROU_POSE journalisé
```

La garde du Supporter (lot `j-cartes-supporters`) consultera
`verrous.est_verrouille(VERROU_PAS_DE_SUPPORTER, cible="bob")` → vrai, et refusera le coup **en
nommant Zone de Combat** (`source_du_verrou`). Au Pokémon Checkup du tour 4,
`verrous.expirer_au_checkup(4)` lève le verrou et le **journalise** (`EVT_VERROU_LEVE`) — il ne
disparaît jamais en silence. (Testé : `test_verrou_pas_de_supporter_refuse_en_nommant_la_carte_r55`,
`test_verrou_ce_tour_expire_au_checkup_et_le_dit_r125`.)

---

## L'étude des 200 cartes (d'où vient le vocabulaire)

La mission exige de définir les événements « à partir des besoins réels relevés sur 200 cartes
prises au hasard du catalogue ». `apps/game/tools/classer_echantillon.py` prend un échantillon
**déterministe** de 200 cartes porteuses d'un texte d'effet (talent ou effet d'attaque), classe
chaque effet par mécanisme et, pour les déclenchés, par moment, et gèle le résultat dans
`apps/game/tests/donnees/echantillon_200_effets.json`. Le test `test_effets_echantillon` relit
ce fichier en CI (sans la base) et **échoue** si un déclencheur ne tombe dans aucun moment connu.

**Ce que l'étude a trouvé, et ce qu'elle n'a pas pu trouver (honnêtement) :**

- Sur les 200 cartes, les mécanismes se répartissent en ~188 effets d'attaque, ~23 activés,
  ~14 continus, ~8 déclenchés. Les moments déclenchés *dans le texte des talents* observés sont
  `pose`, `evolution` et `attachement_energie` ; aucun déclencheur hors vocabulaire (0).
- Le moment `devient_actif` n'apparaît pas dans cet échantillon de talents, mais la fiche
  `j-cartes-objets` le réclame explicitement (l'appât déclenche « quand ce Pokémon devient
  actif ») : il est donc dans la liste, et l'étude a été refaite dessus — exactement ce que
  prévoit le critère d'acceptation (« ou la liste est complétée et le test refait »).
- **Le catalogue ne porte pas le texte d'effet des Dresseurs ni des Énergies** (2766 des 2873
  Dresseurs ont `abilities` et `attacks` vides). Les moments `ko`, `avant_degats`, `apres_degats`,
  `pioche`, `debut_tour`, `fin_tour`, `entre_tours` sont donc justifiés par la liste explicite de
  la fiche du lot et par le corpus de règles (R-12.3/R-13.1/R-10), non par ce texte absent. Cet
  écart est réel ; il est consigné ici plutôt que masqué, et il devra être comblé par le lot
  `j-effets-catalogue-compilation`. Voir `docs/catalogue/COMPLETUDE.md`.
