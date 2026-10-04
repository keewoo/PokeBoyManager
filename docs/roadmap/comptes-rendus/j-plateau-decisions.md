# Compte rendu — `j-plateau-decisions`

**Fenêtres de décision : choisir des cartes, ordonner, répondre pendant le tour adverse.**
Piste Interface de jeu · jalon J2 · couloir J-UI (exécuté sur chimera, piloté depuis devAI).

## Résumé

L'interface des cartes à effet, enfin posée : **un seul composant générique** (`FenetreDecision`)
rend les **six catégories** de demande du moteur (`carte`, `cartes`, `ordre`, `oui_non`, `type`,
`nombre`) à partir de la seule `VueDemande` projetée par le serveur — **aucun écran par carte**. La
fenêtre montre le **temps restant**, **ce qui se jouera à l'expiration** (réponse par défaut, miroir
exact du moteur), laisse **annuler avant de valider**, et traite le cas « c'est à l'adversaire de
décider » par une **bannière d'attente** explicite des deux côtés. Les grands ensembles (pioche de
soixante cartes) sont **fouillables** par recherche (nom/référence, tolérante aux accents et à la
casse) et **filtres par type**.

Pour que l'écran puisse rendre et chercher de vraies cartes, les **options** d'une demande — de
simples `instance_id` nus dans la projection — sont **enrichies** côté serveur en `{id, ref, nom,
type}` (`pbm_game.sortie.enrichir_demande`, alimenté par le catalogue via l'adaptateur API), y
compris pour une **zone cachée qu'on fait fouiller** (la pioche), que `refs_en_jeu` ne relevait pas.
L'anti-fuite reste tenue par la projection : un **ensemble caché** (`ensemble_cache`) ne porte pas
d'options → rien n'est enrichi, aucune identité ne sort.

## Livrables

- **Moteur (pur)** `apps/game/src/pbm_game/sortie/demande.py` : `refs_demande(etat)` (refs des cartes
  d'une demande, même en zone cachée) et `enrichir_demande(vue, etat, *, noms, types)` (options →
  cartes affichables, en place, sans fuite). Exporté par `sortie/__init__.py`.
- **API** : `CatalogueAffichage` gagne un champ `noms` (ref → nom) ; `catalogue_affichage` le remplit ;
  `catalogue_pour_etat`/`catalogue_pour_resultat` chargent aussi `refs_demande(etat)` ;
  `vue_autoritaire`/`projeter_resultat` appellent `enrichir_demande` après les indicateurs.
- **Web (pur)** `apps/web/src/lib/game/decision.ts` : `choixParDefaut` et `reponseValide` (miroirs de
  `reponse_par_defaut`/`valider_reponse`), `filtrerOptions`/`typesPresents` (recherche + filtres),
  `deplacer` (réordonnancement), constantes `ACTION_REPONDRE_DEMANDE`/`OUI`/`NON`.
- **Web (composant)** `apps/web/src/components/game/fenetre-decision.tsx` : `FenetreDecision`,
  modale (si c'est à moi) ou bannière d'attente (si c'est à l'adversaire), hors flux de page
  (`fixed`) pour ne pas introduire de défilement sur le plateau.
- **Web (intégration)** `partie-view.tsx` : `onRepondre` soumet `repondre_demande` par la même route
  que tout coup (`POST /games/{id}/actions`, idempotence par numéro), et monte la fenêtre.
- **Types** `plateau.ts` : `VueDemande` et `VueOptionCarte` (la demande n'était que `unknown`).

## Preuves

- **Moteur** : `apps/game` ruff clean, **943 tests** passés, dont les 6 nouveaux de
  `tests/test_demandes_enrichissement.py` (résolution, repli sur la ref si nom inconnu, non-fuite sur
  la vue de l'autre joueur, ensemble caché → rien d'enrichi, options non-cartes laissées telles
  quelles, `refs_demande` relève une zone cachée).
- **Web** : `type-check` 0 erreur, `lint` 0 erreur, **vitest 55 fichiers / 298 tests** passés — dont
  `decision.test.ts` (21) et `fenetre-decision.test.tsx` (18) : rendu des six catégories, recherche
  d'une carte précise dans une **pioche de 60**, bannière d'attente des deux côtés, réponse par
  défaut visible, reprise du **temps restant** après F5 (pas le délai remis à neuf), soumission +
  refus serveur affiché, **annuler avant valider**, **demande imbriquée** (sélection remise à neuf).
- **API** : ruff clean sur les fichiers touchés ; smoke d'import OK (`CatalogueAffichage.noms`
  présent). Suite API complète : laissée à la CI (Postgres + S3).
- CI GitHub Actions : voir la PR (elle fait foi).

## Critères d'acceptation

- [x] **Toute demande du moteur s'affiche sans code spécifique à la carte** — un composant piloté par
  `categorie`, testé sur les six catégories.
- [x] **Chercher une carte dans la pioche prend moins de cinq secondes** — recherche (nom/ref,
  insensible aux accents) + filtres par type ; test sur 60 cartes.
- [x] **L'attente d'une décision adverse est explicite des deux côtés** — le décideur voit la modale,
  l'autre voit la bannière « ⏳ L'adversaire réfléchit » avec le motif et le compte à rebours.

## Écarts / décisions

- **Ensemble caché (`ensemble_cache`) non répondable** : un choix « à l'aveugle » (ex. choisir dans
  la main adverse) n'a, dans le moteur actuel, **aucun protocole de réponse par position** (les
  options ne sont pas exposées, et il n'y a pas de jetons de demande comme pour les récompenses).
  **Aucune carte scriptée au jalon J2 ne produit `ensemble_cache`** (vérifié : usage test-only). La
  fenêtre l'affiche donc comme un état informatif explicite — « désignation à l'aveugle pas encore
  disponible » — plutôt que d'inventer un protocole (D9). À reprendre quand une carte l'exigera.
- **Catégories `ordre`/`oui_non`/`type`/`nombre` non encore produites par une carte** : seules
  `carte`/`cartes` le sont aujourd'hui (via `strategie_demande`). Le composant les gère toutes les
  six (testées sur des demandes construites) pour être prêt sans retouche quand ces effets arriveront.

## Reste à faire (hors périmètre de ce lot)

- Protocole de réponse pour un **ensemble caché** (désignation par position ou jetons de demande),
  le jour où une carte le réclame.
- Image réelle de la carte dans les sélecteurs : dépend du lot `j-rendu-carte` (aval) ; ici on
  affiche nom + pastille de type (lisible sans couleur, daltonisme).

## Où le savoir durable a été rangé

Comportement serveur (enrichissement de la demande, champ `noms`) → à consigner dans
`docs/ARCHITECTURE.md` ; composant et sélecteurs → `docs/UI-UX.md`. Ce lot touche au jeu : le détail
des règles reste dans `docs/jeu/REGLES.md` (R-9.3 cité par les tests de demande).
