# CARTES-SUPPORTERS.md — les cartes Supporter du jeu

> Lot `j-cartes-supporters` (jalon J2). Les Supporters sont scriptés dans le **langage d'effets**
> (`docs/jeu/DSL.md`), comme les Objets (`CARTES-OBJETS.md`) — aucune n'a de code spécifique (D9).
> Ce qui les distingue, c'est la **règle du tour** et le **verrou**, tenus côté serveur.

## Ce qu'un Supporter a de plus qu'un Objet

- **Un seul par tour** (R-5.5) et **aucun au premier tour du joueur qui commence** (R-6.2). Vérifié
  par `pbm_game.tour.contraintes.peut_jouer_supporter` **avant** de rien résoudre, côté famille
  (liste) *et* côté transition (le serveur fait autorité). Le refus **cite la règle**.
- **Interdit sous le verrou** `pas_de_supporter` (type *Marnie* inversé, un talent adverse) : le
  refus **nomme la carte responsable**, jamais muet — même garde que l'attaque sous verrou.
- Une fois joué, la transition `jouer_supporter` **lève le drapeau** `Tour.supporter_joue`. Ce
  drapeau est porté par l'état, donc sérialisé : un second Supporter reste refusé, et le drapeau
  **survit à une reprise après un F5** (prouvé par aller-retour `vers_json`/`depuis_json`).

Pour le reste, un Supporter est un Objet : il quitte la main pour la défausse **avant** résolution
(« mélangez votre main dans votre deck » ne se remet pas elle-même), son coût est payé de façon
atomique, et son script peut forcer un changement d'Actif (reporté par `devient_actif`).

## Les familles scriptées (≥ 3 cartes réelles chacune)

| Famille | Mécanique | Cartes |
|---|---|---|
| **pioche pure** | refaire sa main | *Professor's Research* (défausse sa main, pioche 7), *Cynthia* (remet sa main dans le deck, pioche 6), *Hop* (pioche 3) |
| **recherche** | chercher une carte dans une zone | *Pokémon Fan Club* (2 bases du deck), *Pokémon Collector* (3 bases), *Fisherman* (3 énergies de la défausse) |
| **perturbation** | agir sur les ressources de l'adversaire | *Judge* (chaque joueur remet sa main et pioche 4), *N* (… pioche par récompense restante), *Team Rocket's Handiwork* (pile ou face ×2 : défausse le dessus du deck adverse) |
| **conditionnels** | le `si` décide | *Roxanne* (moins de récompenses que l'adversaire → 6, sinon 2), *Gambler* (remet sa main ; pile → 8, sinon 1), *Looker* (si l'adversaire a une main → 3, sinon 1) |

## Perturbation de la main adverse, sans la révéler (confidentialité, R-5.5)

« Mélanger et repiocher » et « faire défausser » touchent la main / le deck de l'adversaire. Deux
verbes du DSL ont été étendus pour les exprimer, **sans fuite** (le joueur actif apprend le
**nombre**, jamais le contenu) :

- `melanger` avec `cible.zone = main` : la main rejoint la pioche, puis la pioche entière est
  mélangée (« mélangez votre main dans votre deck »). L'événement ne porte que le nombre de cartes.
- `piocher` avec `cible.proprietaire = adversaire` : l'adversaire pioche N (« votre adversaire
  pioche… »). L'événement ne porte que le nombre, jamais les identités.

Ces événements de primitive (`dsl_primitive`) ne sont de toute façon **pas** diffusés au client
(différés, `DIFFERES_SYSTEME_EFFETS`) tant que leur projection par destinataire n'existe pas : le
seul événement public est `EVT_SUPPORTER_JOUE` (nom + Actifs changés). Le test de **non-fuite**
(`test_cartes_supporters.py::test_perturbation_ne_revele_pas_la_main_adverse`) le vérifie.

## Condition « moins de récompenses »

`moins_de_recompenses` : le joueur qui joue l'effet a **strictement moins** de cartes récompense
restantes que son adversaire — il mène aux récompenses (R-13.3). Comptée sur l'état, jamais devinée.
Détail : `docs/jeu/DSL.md` § « Les conditions ».
