# Compte rendu — `j-cartes-supporters`

**Lot** : Supporters — un par tour, et les effets qui perturbent l'adversaire · piste Effets &
cartes · jalon J2 · couloir J-EFF (chimera) · P0.

**Machine** : exécuté sur **chimera** (WSL Ubuntu-24.04), piloté depuis **devAI**. Worktree
`~/dev/wt-j-cartes-supporters`, branche `roadmap/j-cartes-supporters` depuis `github/main`.

## Résumé

Les cartes **Supporter** sont jouables, scriptées dans le langage d'effets — aucune n'a de code
spécifique (D9). Quatre familles sont couvertes avec **trois cartes réelles chacune** : pioche pure,
recherche, perturbation de l'adversaire, conditionnels. Ce que le Supporter ajoute à l'Objet est tenu
**côté serveur** : **un seul par tour** (R-5.5), **aucun au premier tour du joueur qui commence**
(R-6.2), et l'**interdiction sous le verrou** `pas_de_supporter` — dont le refus **nomme la carte
responsable**. Une fois joué, la transition lève le drapeau `Tour.supporter_joue`, porté par l'état,
donc sérialisé : un second Supporter reste refusé, et le drapeau **survit à une reprise après un F5**.

Les effets qui touchent la **main adverse** (« mélanger et repiocher », « faire défausser ») la
perturbent **sans la révéler** : le joueur actif apprend le **nombre**, jamais le contenu. Deux
verbes du DSL ont été étendus pour les exprimer fidèlement — `melanger` sur la main (la remet dans
le deck puis mélange) et `piocher` ciblant l'adversaire — et une condition `moins_de_recompenses`
a été ajoutée. Aucune nouvelle **primitive** : le dépouillement des 500 textes classe déjà « mélanger
sa main dans son deck » sous `melanger`, l'échantillon gelé n'a donc **pas** bougé.

Tout le travail vit dans le **moteur pur `pbm_game`** (plus un traducteur de journal côté `apps/web`)
— aucune base, aucun service touché : couvert par le job CI `game` (et le `web` pour le traducteur).
Comme pour les Objets, le branchement HTTP des Dresseurs (catalogue de partie, route `/actions`)
n'existe pas encore et reste hors périmètre de ce lot — voir « Écarts ».

## Livrables

- **DSL — perturbation sans fuite** (`effets/dsl/primitives.py`, `jouabilite.py`, `chargement.py`,
  `schema.json`) : `melanger` avec `cible.zone = main` remet la main dans le deck puis mélange ;
  `piocher` ciblant `adversaire` fait repiocher l'adversaire. Les deux ne journalisent que le
  **nombre**, jamais les identités.
- **DSL — condition** `moins_de_recompenses` (`vocabulaire.py`, `interprete.py`, `chargement.py`,
  `schema.json`) : « seulement si vous avez moins de récompenses » (R-13.3).
- **Jouer un Supporter** : action `jouer_supporter` (`effets/supporters.py`, enregistrée au
  `REGISTRE`), avec les gardes serveur R-5.5 / R-6.2 / verrou et la levée du drapeau ;
  `FamilleJouerSupporter` + `DefinitionSupporter` + `CatalogueJeu.supporters` (`actions/familles_jeu.py`) ;
  événement `EVT_SUPPORTER_JOUE` + projecteur public + traducteur front (`apps/web/.../journal.ts`).
- **Cartes réelles scriptées** (12) : Professor's Research / Cynthia / Hop ; Pokémon Fan Club /
  Pokémon Collector / Fisherman ; Judge / N / Team Rocket's Handiwork ; Roxanne / Gambler / Looker.
- **Doc** : `docs/jeu/CARTES-SUPPORTERS.md` ; `docs/jeu/DSL.md` mis à jour (piocher/melanger étendus,
  conditions `type_cible` et `moins_de_recompenses`).
- **Tests** : `apps/game/tests/test_cartes_supporters.py` (19 cas) ; fixture `supporter_joue` ajoutée
  à `apps/web/src/lib/game/journal.test.ts`.

## Preuves

- Suite moteur **verte** : `uv run --python 3.12 pytest -q` dans `apps/game` → **988 passed** (dont
  les 19 nouveaux, la couverture DSL des 500 textes inchangée, la parité émetteurs↔projecteurs et
  émetteurs↔front).
- `uv run --python 3.12 ruff check .` dans `apps/game` → **All checks passed!**
- Critères d'acceptation :
  - *Supporter sous verrou refusé, carte nommée* : `test_supporter_refuse_sous_verrou_en_nommant_la_carte`
    (liste vide + `valider` cite « Marnie's Trick » + la transition lève `ValueError` avec ce nom).
  - *Aucun effet ne révèle la main adverse* : `test_perturbation_ne_revele_pas_la_main_adverse`
    (Judge rebat la main de bob ; aucun `ref`/`instance_id` secret dans la trace).
  - *Le drapeau survit à une reprise après F5* : `test_drapeau_supporter_survit_a_une_reprise_apres_f5`
    (aller-retour `vers_json`/`depuis_json` ; second Supporter toujours refusé).
  - *Un seul par tour* / *premier tour* : `test_second_supporter_refuse_le_meme_tour`,
    `test_supporter_refuse_au_premier_tour_du_joueur_qui_commence`.
- CI GitHub Actions : voir la PR `roadmap/j-cartes-supporters` (elle fait foi).

## Écarts au plan

- **Périmètre moteur, comme `j-cartes-objets`.** Le branchement HTTP des Dresseurs (construire le
  `CatalogueJeu.supporters` depuis `card_scripts`, exposer `jouer_supporter` sur `/games/{id}/actions`,
  publier `EJ_DEVIENT_ACTIF` côté service) **n'existe pour aucun Dresseur** aujourd'hui
  (`games/catalogue_jeu.py` ne construit que Pokémon + Énergies). Le faire pour les seuls Supporters
  serait incohérent : c'est une **intégration à part**, à mener une fois pour Objets **et** Supporters.
  Conséquence : pas de **test d'accès croisé** de route ici (il n'y a pas de nouvelle route) — la
  section 7 « route utilisateur » ne s'applique pas à ce lot purement moteur.
- **Pas de nouvelle primitive DSL.** « Mélanger et repiocher » est exprimé en étendant `melanger`
  (zone `main`) et `piocher` (proprietaire), ce qui respecte l'échantillon gelé des 500 textes (qui
  classe ces cartes sous `melanger`) et évite de régénérer la couverture. Fidélité assumée : *Marnie*
  et *Iono* mettent la main « au-dessous du deck » plutôt que de mélanger ; ces cartes **ne sont pas**
  dans le jeu scripté de ce lot (on a pris *Judge* et *N*, qui mélangent vraiment) — on ne les
  approxime pas (D9), on les laissera à un futur verbe « remettre » si besoin.

## Reste à faire (hors périmètre)

- Intégration HTTP des Dresseurs (Objets + Supporters) : `CatalogueJeu` depuis `card_scripts`,
  route `/actions`, publication du bus côté service, tests d'accès croisé.
- Un verbe « remettre (dessus/dessous) » si l'on veut *Marnie*/*Iono* à la lettre (mise au-dessous
  du deck sans mélanger le deck entier).
