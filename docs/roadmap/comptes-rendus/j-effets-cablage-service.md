# Compte rendu — `j-effets-cablage-service`

**Brancher les effets dans le service de parties : Objets, Supporters, talents, Outils, Stades, en partie réelle.**

Jalon J2. Exécuté sur **chimera** (WSL), piloté depuis **devAI**. CI GitHub Actions fait foi.

## Résumé

La livraison bloquée du 04/10 (« livraison-effets-cartes ») l'avait constaté : les lots d'effets
avaient écrit le **moteur** et renvoyé le **branchement côté service** « à un lot ultérieur » qui
n'existait pas. `CatalogueJeu.registre_continus` restait vide, `card_scripts` n'était jamais lue
pour fabriquer des définitions jouables, deux familles de coups manquaient, et aucune fenêtre de
décision n'était jamais répondue par l'API. **Une carte à effet ne pouvait donc pas être jouée en
partie réelle, même avec son script.**

Ce lot ferme le trou, de bout en bout, et le **prouve par une partie réelle jouée à travers les
routes HTTP et le WebSocket** : une attaque à effet, un Objet, un Supporter, un talent activé, un
Outil et un Stade s'y résolvent, avec une **fenêtre de décision ouverte et répondue**, sans jamais
fuiter une carte cachée.

## Livrables

### Moteur (`apps/game`, pur)

- `CatalogueJeu` étendu (`actions/familles_jeu.py`) : champs `outils` (+ `DefinitionOutil`),
  `talents` (fiches `RegistreTalents`) et `talents_programmes` (DSL des talents activés), en plus
  des `objets`/`supporters`/`stades`/`registre_continus` déjà présents mais jamais alimentés.
- Deux familles de coups manquantes, enfin surfacées comme coups légaux :
  - `FamilleAttacherOutil` (R-3.7 : au plus un Outil par Pokémon) ;
  - `FamilleActiverTalent` (R-5 : talent activé, une fois par tour par Pokémon, portillon
    `talent_actif` + jouabilité du script comme un Objet).
- Modificateurs **continus** (Outils, Stades, talents) câblés dans le calcul des dégâts :
  `FamilleAttaquer` embarque les modificateurs et les seuils de K.O. continus dans les `params`
  (R-10.1 étapes 2/5, R-13.1) ; `resoudre_attaque_declaree` les relit et les passe à
  `resoudre_degats`. Le Checkup utilise aussi les seuils continus (`service.py`).
- **Fenêtre de décision injectée dans `jouer_objet`** (`effets/objets.py`) : en mode décision, un
  `choisir` du script ouvre une vraie demande (`demarrer_resolution`) au lieu d'être tranché
  d'office ; la partie se met en pause (`etat.resolution`) et reprend à `repondre_demande`. Les
  résolveurs DSL de pile appliquent désormais les **verrous** (`empecher`) à l'état — ils les
  perdaient (`effets/dsl/interprete.py`).
- Projection par destinataire des événements du **système d'effets** (`sortie/evenements.py`) :
  `dsl_primitive`, `dsl_choix`, `demande_emise` (options cachées à qui n'est pas le destinataire),
  `demande_repondue`, `demande_expiree`. Ils étaient jusqu'ici *différés* (refusés à la diffusion) :
  c'est ce lot qui les fait traverser réellement la projection — anti-fuite vérifié.

### Service (`apps/api`)

- `jeu/catalogue.py` : adaptateurs `definition_{objet,supporter,stade,outil}_depuis_card`,
  classement `genre_dresseur` (Objet/Supporter/Stade/Outil, FR et EN), et **branchement des scripts
  d'attaque à effet** dans `DefinitionCarte` (par empreinte du texte).
- `jeu/scripts/programmes.py` : charge, pour une liste d'empreintes, les scripts DSL `scripte`
  validés — la moitié *positive* du pont (le chargeur ne rendait que des refus).
- `jeu/couverture_jeu.py` : la **couverture hors-DSL** — Outils/Stades scriptés dans le moteur
  (producteurs), et les fiches de **talents activés écrits à la main** (point d'extension). La porte
  D9 du deck (`jeu/scripts/chargeur.py`) n'exige plus de ligne `card_scripts` pour ces effets.
- `games/catalogue_jeu.py` : `construire_catalogue_jeu` assemble désormais **tout** le
  `CatalogueJeu` d'une partie — Pokémon, Énergies, Objets, Supporters, Stades, Outils, talents,
  `registre_continus` (via `registre_outils`/`registre_stades`) — en une requête.
- `games/construction.py` : un deck à cartes Dresseur n'est plus refusé « ce n'est pas un Pokémon » ;
  les Dresseurs entrent dans la pioche, leur jouabilité relevant de la porte scripts (D9).
- `games/service.py` : `appliquer_action` accepte `repondre_demande` (validé par la transition, pas
  par l'appartenance à la liste) et injecte le mode décision pour `jouer_objet` **après** `valider`
  (le drapeau n'appartient pas au coup légal ; le rejeu reste cohérent, le client ne peut pas le
  forger).

### Données & écran

- `apps/api/scripts/seed_effets.json` : les scripts d'effet **écrits à la main** (appât, pioche,
  recherche, soin, changement d'Actif), importables par la commande prévue
  (`scripts_effets.py importer`) — chacun au statut `scripte` (contrainte
  `ck_card_scripts_scripte_gate` satisfaite). Import vérifié.
- Zone **Stade** sur le plateau : **déjà rendue** par `apps/web/.../game-board.tsx` (ligne centrale
  partagée, « Stade » / « Stade (aucun) ») ; ce lot alimente la donnée (`registre_continus`) pour
  qu'un Stade joué apparaisse réellement. Journal front : traducteurs ajoutés pour les 5 événements
  du système d'effets (`journal.ts`), parité `journal.test.ts` tenue.

## Preuves

- **Partie réelle HTTP + WebSocket** — `apps/api/tests/test_games_effets_cablage.py::test_partie_a_effets_par_http_et_ws` :
  une partie jouée par `POST /games/{id}/actions` et diffusée sur le `HUB` résout une attaque à
  effet, un Objet, un Supporter, un talent, un Outil **et** un Stade, ouvre **et** répond une fenêtre
  de décision (appât), le tout sans qu'un `instance_id` caché n'apparaisse dans la vue d'un joueur.
- **Porte D9 du deck** — `…::test_deck_a_effets_passe_ou_refuse_selon_les_scripts` : un deck à effets
  passe la construction dès que les scripts sont au registre (Objet/attaque) ou couverts par le
  moteur (Outil/Stade/talent), et est **refusé** sinon, en nommant la carte.
- **Moteur** — `apps/game/tests/test_familles_effets_cablage.py` (5 tests, chacun cite son `R-x.y`) :
  attacher un Outil (R-3.7), Metal Core Barrier réduit les dégâts (R-10.1), activer un talent et la
  règle une-fois-par-tour (R-5), talent sans script non proposé (D9).
- **Parités tenues** : `test_parite_evenements_projecteurs` (plus aucun événement différé) et
  `test_parite_journal_front` (chaque type projetable a sa traduction front).
- Suites locales : **1053** tests moteur verts ; **191** tests API des zones touchées verts
  (les 2 échecs de `test_catalogue_seed` sont environnementaux — `pg_dump`/`pg_restore` absents de
  la machine de dev, sans rapport avec ce lot).

## Écarts au plan

- **Mode décision limité à `jouer_objet`** (ce que nomme le reste-à-faire de `j-cartes-objets`,
  « injecter la demande de décision dans jouer_objet »). Supporters et talents activés se résolvent
  d'office (stratégie canonique) : correct pour les cartes seedées, qui n'ont pas de choix humain.
  Même chose pour les attaques à effet. Le mécanisme est en place et réutilisable à l'identique.
- **Talents : nature « activé » seulement.** Le câblage couvre les talents **activés** (fiche écrite
  à la main + script DSL). Les talents **continus** et **déclenchés** réels n'ont pas encore de
  producteur/réacteur dans le moteur (seuls des jouets de test existent) ; leur `registre_continus`
  et leur bus `EJ_*` se brancheront quand ces producteurs seront écrits — c'est du **moteur**
  (données de carte), hors du câblage service/écran de ce lot.
- **`devient_actif` de `objet_joue`** est vide en mode décision (le changement d'Actif est porté par
  l'événement `echange_force` de la résolution) ; aucune perte d'information pour le joueur.

## Reste à faire

1. **Peupler `card_scripts` à l'échelle du catalogue** (les 15 Objets, 12 Supporters, attaques à
   effet) sur les **textes réels** des cartes : c'est le passage IA **DJ8** (déjà prévu, ~50 €,
   voir `docs/PLUGINS.md` et la mémoire projet). Le câblage livré ici rend **immédiatement jouable**
   tout script correctement seedé — prouvé. `seed_effets.json` amorce la graine à la main.
2. **Producteurs réels des talents continus/déclenchés** et matérialisation du verrou
   `talents_sans_effet` (type *Garbodor*) : chantier **moteur** (lot de cartes talents), pas service.
3. **Routage décision pour Supporters/attaques** si une carte réelle réclame un choix humain : même
   mécanisme que `jouer_objet`, à étendre quand le besoin se présente.

Aucune ligne de reste-à-faire **relevant du service ou de l'écran** des lots d'effets n'est laissée
sans être faite : alimentation du `CatalogueJeu` depuis `card_scripts`, familles manquantes
surfacées, modificateurs continus consultés, demande de décision injectée, zone Stade rendue — tout
est branché et prouvé par la partie réelle. Ce qui reste est soit des **données** (DJ8), soit du
**moteur** (producteurs de talents).

## Où le savoir durable est écrit

- Comportement serveur (assemblage du catalogue, porte D9, mode décision) : `docs/ARCHITECTURE.md`.
- Mécanisme d'effets du jeu (couverture DSL vs moteur, talents activés) : `docs/jeu/`.
