# Compte rendu — `ia-scripts-passe`

**Lot hors plan** décidé par JF (DJ8, 04/10/2026), ouvert le 05/10. But : lancer le **passage réel**
de l'assistance IA qui écrit les `card_scripts`, puis importer les scripts admis en PROD — ce qui
avait bloqué la livraison des cartes à effet le 04/10 (`card_scripts` vide en PROD). Opéré en session
autonome : pilotage **devAI**, calcul **chimera**.

## Verdict

**Le passage n'a produit AUCUN script admissible : 0 sur 97 effets traités.** Rien n'a été importé en
PROD (il n'y avait rien à importer). **La PROD n'a pas été touchée** ; `card_scripts` y reste à 0 et
les cartes à effet de JF et d'Aymeric **restent injouables**, comme avant ce lot. Dépense réelle :
**1,87 € sur les 50 €** autorisés (arrêt volontaire, voir plus bas).

Ce n'est pas la porte de sûreté qui a échoué — elle a parfaitement refusé 97 scripts non prouvés
(D9/DJ8). C'est l'étage de **génération** (modèle + prompt) qui ne produit pas de scripts conformes
et prouvés sur les effets réels. Diagnostic complet et recommandation : **rapport par famille**
(`docs/roadmap/comptes-rendus/` ci-dessous + `~/dev/logs/pbm-ia-scripts-rapport.md` sur devAI).

## Ce qui a été livré (fusionné dans `main`, CI verte)

Le passage ne pouvait pas tourner tel quel contre le catalogue de référence (`pbm_catalogue_ref`),
qui porte les cartes mais **pas** les collections des joueurs, et il manquait de robustesse. Trois
apports, tous testés :

1. **Sélection DJ2 jusqu'au catalogue** (`runner.selectionner_effets`) : nouvel univers = catalogue
   entier de la base, avec une **priorité de possession injectée** (`--priorite-possession`,
   extraite en lecture seule de la PROD : empreinte des comptes `game_access`). Tri DJ2 à la lettre :
   possédées d'abord, puis les plus fréquentes du catalogue. Le chemin historique (univers possédé
   local) est inchangé. **La porte DJ8 n'est pas touchée.**
2. **Robustesse du passage** : une réponse d'IA inexploitable (JSON tronqué au plafond de jetons,
   ou noyé dans de la prose) devient `a_revoir` nommé au lieu de **tuer tout le passage** (vécu avec
   sonnet-5 au 13ᵉ effet) ; les erreurs fournisseur (HTTP/réseau) sont attrapées de même.
   `max_tokens` porté de 4096 à 8192 (les réponses des modèles verbeux étaient tronquées).
3. **Chaîne fleet** : `infra/fleet/export_card_scripts.sql` (export des scriptés par empreinte) et
   `import_card_scripts.sql` (import PROD insert-only, par empreinte), sur le modèle de
   `export_cards.sql` / `import_weekly.sql`. Prête pour le jour où un passage produira des scriptés.

Commits : `b2e8352` (sélection + fleet), `7431d79` (robustesse). CI « CI » verte sur les deux
(push). Deux tests mordants ajoutés (ordre DJ2 ; réponse illisible → `a_revoir` sans crash).

## Ce qui a réellement été exécuté

```text
# base de travail : pbm_ia_scripts_ref sur chimera = catalogue de pbm_catalogue_ref (23 855 cartes)
#   importé via la chaîne fleet, migré à la tête (card_scripts + colonnes DJ8 + contrainte), taux
#   USD→EUR semé (1,1225, source PROD).
# priorité DJ2 : 128 tcgdex possédés (JF+Aymeric), 181 effets distincts possédés, extraits en
#   LECTURE SEULE de pokeboy_prod (devAI). Univers total : 13 138 effets scriptables du catalogue.
# passage détaché (setsid) sur chimera, clé plateforme en fichier chmod 600 (~/.pbm-pass/key),
#   SUPPRIMÉ en fin (voir nettoyage). Sondé en commandes bornées. Reprise par grand livre.
# modèle haiku-4-5 d'abord (défaut DJ8) : 0 scripté sur ~23 effets (clés inventées) → reset.
# modèle sonnet-5 ensuite (modèle plus capable, même budget, même porte) : 0 scripté sur 97 effets.
```

Résultat : **97 traités · 0 scriptés · 59 à revoir · 38 non supportés · 1,87 €.**

## Pourquoi 0 % (mesuré)

- **36/59 « à revoir » = schéma** : le prompt `grammaire_dsl()` liste les *noms* d'op mais pas leurs
  **arguments requis** ; le modèle invente des clés (`destination`, `categorie`…) ou en oublie
  (`piocher` sans `nombre`) → refus strict du chargeur, à raison. Preuve directe : forcé sur
  « Piochez 2 cartes. », sonnet rend un `piocher` sans `nombre` → `a_revoir`, alors que le moteur
  exécute parfaitement `{"op":"piocher","nombre":2}` (cas de test unitaire vert).
- **22/59 « à revoir » = sémantique** : le script est valide mais le **cas de test écrit par le
  modèle** ne colle pas à l'état exact que produit le moteur (ex. « Soignez 30 » : script valide,
  essai faux).
- **38 « non supportés »** : effets réellement hors DSL v1 (dégâts proportionnels, défausse ciblée
  aléatoire…), souvent à juste titre.

## Décision d'arrêt (mission point 6)

0/97 sur **deux modèles**, y compris sur des effets triviaux, est un **taux d'admission anormal**
au sens de la mission : « tu t'arrêtes, tu n'importes pas, et tu l'écris ». Poursuivre jusqu'à 50 €
aurait brûlé le budget pour le même résultat. J'ai donc arrêté à 1,87 €, **sans importer**. La
chaîne d'import PROD, le point de restauration et la preuve avant/après n'ont pas été exécutés :
il n'y avait **rien à importer**, et importer 0 ligne ne change rien à la couverture (restée 0 %).

## Recommandation

Le correctif est côté **génération** (lot `j-effets-assistance-ia`), pas côté moteur ni porte :
(1) enrichir `grammaire_dsl()` du schéma par primitive, dérivé des constantes du moteur (test de
cohérence anti-dérive) ; (2) amorcer quelques exemples validés à la main (un par famille courante) —
`_exemples_proches` ne joint rien tant que `card_scripts` est vide ; (3) clarifier le format d'état
des essais ; (4) **re-mesurer sur ~50 effets avant d'ouvrir les 50 €**. Détail dans le rapport.

## Nettoyage / sûreté

- Clé plateforme : jamais dans le dépôt, un journal ou une sortie. Fichier temporaire chmod 600 sur
  chimera **supprimé** en fin de lot (preuve dans le journal du lot).
- Base de travail `pbm_ia_scripts_ref` : jetable, sur chimera.
- Aucun verrou de livraison posé (pas d'écriture PROD) ; PROD intacte.
