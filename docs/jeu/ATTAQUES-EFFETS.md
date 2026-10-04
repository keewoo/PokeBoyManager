# ATTAQUES-EFFETS.md — les attaques à effet, scriptées et résolues

> Lot `j-cartes-attaques-effets` (jalon J2). Pur, sans E/S, comme tout `pbm_game`. Prolonge le
> langage d'effets (`docs/jeu/DSL.md`) et le cadre d'effets (`docs/jeu/EFFETS.md`). Règles citées
> (`R-x.y`) : `docs/jeu/REGLES.md`.

## Ce que fait le moteur

Une attaque peut porter un **script DSL** (`params["attaque"]["script"]`) et/ou des **dégâts
variables** (`params["attaque"]["degats"]` est alors une *formule*, pas un entier).
`pbm_game.combat.attaque.resoudre_attaque_declaree` :

1. paie le coût d'énergie (R-9.2, les énergies ne sont pas défaussées) ;
2. calcule la **base** des dégâts **maintenant**, sur l'état courant (une base variable est lue
   avant tout effet — le piège de la fiche : une défausse d'énergie en effet ne doit pas la
   fausser) ;
3. exécute le **script** entre `avant_degats` et `apres_degats` : états, soins, dégâts au banc,
   auto-dégâts, défausse d'énergie, blocage, et éventuellement **annulation** des dégâts ;
4. pose les **dégâts principaux** sur l'Actif adverse (faiblesse/résistance, R-10) — sauf si le
   script a levé « dégâts annulés » ;
5. résout les **K.O.** (R-13) : l'auto-K.O. et les K.O. de banc sont vus comme le reste.

Un texte d'effet **sans** script ni dégâts variables reste **refusé** (R-15.12/D9) : jamais
approximé.

## Dégâts variables — `pbm_game.combat.valeur.ValeurDynamique`

`max(0, base + par × compte)`, borné par `plafond`. `compter` ∈ {`energies`, `cartes_en_main`,
`pv_manquants`, `marqueurs`, `recompenses_restantes`, `pokemon_banc`} ; `cible` ∈ {`attaquant`,
`defenseur`, `moi`, `adversaire`} (un compteur de Pokémon exige une cible Pokémon, D9). Exemple :
`{"compter": "energies", "cible": "attaquant", "par": 20}` = « 20 dégâts × énergies attachées ».

## Ajouts au DSL (vocabulaire fermé, D9)

- `pile_ou_face` **jusqu'à échec** : `{"op": "pile_ou_face", "jusqu_a_echec": true, "alors": […]}`
  — lance jusqu'au premier pile, `alors` joué une fois par face. Exclut `nombre`. Chaque tirage est
  journalisé (`EVT_DSL_PILE`) et **rejouable depuis la graine**.
- condition **`type_cible`** : `{"type": "type_cible", "cible": {…}, "type_pokemon": "eau"}` — le
  type se lit dans les métadonnées de catalogue du contexte (`ref → type`), jamais deviné.
- **défausse d'énergie** en coût : `deplacer` d'un Pokémon (`source`) vers la zone `defausse`
  (`cible`), ex. « défaussez 1 Énergie de ce Pokémon ».

## Blocage du tour suivant — les verrous dans l'état

`EtatPartie.verrous` (`JeuDeVerrous`) porte les verrous posés (R-5.5/R-5.7/R-12.3/R-8). Un
`empecher` du script y ajoute son `Verrou`. La garde de `declarer_attaque` refuse une attaque
sous `ne_peut_attaquer` **en nommant la carte** (R-5.7). Au Pokémon Checkup (R-12.5),
`expirer_au_checkup_oriente` lève les verrous « ce tour » / « prochain tour » — un « prochain tour »
ne tombe qu'au Checkup **du propriétaire de sa cible** (les tours alternent : un auto-blocage
survit au tour adverse). Chaque levée est journalisée (`EVT_VERROU_LEVE`) ; jamais un retrait muet.

Le champ `verrous` est **rétro-compatible** : absent = aucun verrou, donc il n'incrémente pas
`SCHEMA_VERSION` et ne rend pas illisible une partie en cours (voir le compte rendu du lot).

## Où c'est testé

`apps/game/tests/test_cartes_attaques_effets.py` : une famille par groupe de tests, plus la
sérialisation des verrous (reprise après F5) et la validation D9 du modèle de carte.
