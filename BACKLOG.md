# BACKLOG — PokeBoyManager

> GÉNÉRÉ par `docs/roadmap/suivi.py build` depuis `docs/roadmap/roadmap.json` et `etat.json`. Ne pas éditer à la main.
> Vue complète (calendrier, fiches, prompts, maquette) : `docs/roadmap/ROADMAP.html`.

**Objectif.** Un espace **privé** où chaque collectionneur photographie ses cartes Pokémon, laisse **sa propre IA** (Claude, Gemini ou OpenAI) les reconnaître, puis gère sa collection et suit la **valeur de chaque carte dans le temps**. MVP complet en UAT le **6 novembre**, en ligne le **20 novembre**, extensions avant Noël.

- **2026-11-06 — MVP en UAT** : Parcours complet en UAT : inscription → clé IA → photo → reconnaissance → validation → collection filtrée → fiche carte avec courbe de valeur, anecdotes et étude en jeu.
- **2026-11-20 — En ligne** : Revue de sécurité passée, export/suppression des données, e2e verts en CI, PROD servie sur son domaine avec sauvegardes.

## V0 — Fondations (21 sept. → 29 sept.)

_Un dépôt vide : avant toute fonctionnalité, il faut le squelette, la base, la CI et une flotte capable d'y travailler._

| Lot | Prio | Titre | Couloir | Prévu | Dépend de | Décision | Statut | Prompt |
|---|---|---|---|---|---|---|---|---|
| `v0-flotte` | P0 | Équiper la flotte pour PokeBoyManager (clones, clés de dépôt, fleet-run) | DA2 (devAI) | 21 sept. → 22 sept. | — | — | À faire | [prompt](prompts/v0-flotte.md) |
| `v0-monorepo` | P0 | Monorepo, environnement local Docker et CI | DA1 (devAI) | 22 sept. → 23 sept. | — | D1 | À faire | [prompt](prompts/v0-monorepo.md) |
| `v0-schema` | P0 | Modèle de données PostgreSQL v1 et migrations Alembic | DA1 (devAI) | 24 sept. → 25 sept. | v0-monorepo | — | À faire | [prompt](prompts/v0-schema.md) |
| `v0-design-system` | P1 | Design system et squelette des pages (d'après la maquette) | CH1 (chimera) | 24 sept. → 29 sept. | v0-monorepo | — | À faire | [prompt](prompts/v0-design-system.md) |

## V1 — Un compte à soi (28 sept. → 12 oct.)

_L'espace est privé : inscription, connexion, profil, et le coffre où l'utilisateur dépose sa propre clé IA._

| Lot | Prio | Titre | Couloir | Prévu | Dépend de | Décision | Statut | Prompt |
|---|---|---|---|---|---|---|---|---|
| `v1-auth` | P0 | Comptes : inscription, connexion, vérification d'e-mail, mot de passe oublié | DA1 (devAI) | 28 sept. → 2 oct. | v0-schema | D5 | À faire | [prompt](prompts/v1-auth.md) |
| `v1-accueil` | P1 | Page d'accueil publique (visiteur) | CH1 (chimera) | 30 sept. → 2 oct. | v0-design-system | — | À faire | [prompt](prompts/v1-accueil.md) |
| `v1-pages-auth` | P0 | Pages inscription, connexion, vérification et mot de passe oublié | CH1 (chimera) | 5 oct. → 7 oct. | v1-auth, v0-design-system | — | À faire | [prompt](prompts/v1-pages-auth.md) |
| `v1-byok` | P0 | Coffre de clés IA : Claude, Gemini ou OpenAI par utilisateur | DA1 (devAI) | 5 oct. → 7 oct. | v1-auth | D4 | À faire | [prompt](prompts/v1-byok.md) |
| `v1-uat` | P1 | Environnement UAT continu (images construites sur chimera, déployées par devAI) | DA2 (devAI) | 5 oct. → 9 oct. | v0-schema | D2 | À faire | [prompt](prompts/v1-uat.md) |
| `v1-profil` | P1 | Page profil : photo, pseudo, e-mail, mot de passe, clés IA | CH1 (chimera) | 8 oct. → 12 oct. | v1-pages-auth, v1-byok | — | À faire | [prompt](prompts/v1-profil.md) |
| `v1-identite` | P0 | Identité du compte : prénom, nom, date de naissance, acceptation des conditions, création de compte par l'administrateur | CH1 (chimera) | 13 oct. → 14 oct. | v1-profil | — | À faire | [prompt](prompts/v1-identite.md) |

## V2 — Toutes les cartes, tous les prix (28 sept. → 9 oct.)

_Reconnaître une carte suppose de connaître toutes les cartes ; tracer sa valeur suppose de relever les prix chaque jour, dès maintenant._

| Lot | Prio | Titre | Couloir | Prévu | Dépend de | Décision | Statut | Prompt |
|---|---|---|---|---|---|---|---|---|
| `v2-catalogue` | P0 | Import du catalogue complet FR + EN avec images officielles | CH3 (chimera) | 28 sept. → 2 oct. | v0-schema | — | À faire | [prompt](prompts/v2-catalogue.md) |
| `v2-prix` | P0 | Relevé quotidien des prix et historique de valeur | CH3 (chimera) | 5 oct. → 8 oct. | v2-catalogue | D3 | À faire | [prompt](prompts/v2-prix.md) |
| `v2-recherche` | P1 | Recherche dans le catalogue (nom, numéro, extension) | DA1 (devAI) | 8 oct. → 9 oct. | v2-catalogue | — | À faire | [prompt](prompts/v2-recherche.md) |
| `v2-catalogue-complet` | P0 | Base de référence complète : toutes les cartes, toutes leurs infos, tous les prix — avant la première photo | CH3 (chimera) | 12 oct. → 14 oct. | v2-prix, v2-recherche | — | À faire | [prompt](prompts/v2-catalogue-complet.md) |

## V3 — Des photos aux cartes (8 oct. → 27 oct.)

_Le cœur du produit : une photo (une carte ou un classeur de neuf) devient une liste de cartes identifiées, vérifiées par l'utilisateur._

| Lot | Prio | Titre | Couloir | Prévu | Dépend de | Décision | Statut | Prompt |
|---|---|---|---|---|---|---|---|---|
| `v3-upload` | P0 | Page « Ajouter des photos » : une ou plusieurs photos, glisser-déposer, appareil photo | CH4 (chimera) | 8 oct. → 13 oct. | v1-pages-auth | D7 | À faire | [prompt](prompts/v3-upload.md) |
| `v3-ia-providers` | P0 | Couche fournisseurs IA unique (Anthropic, Google, OpenAI) | CH2 (chimera) | 8 oct. → 9 oct. | v1-byok | — | À faire | [prompt](prompts/v3-ia-providers.md) |
| `v3-detection` | P0 | Détecter et découper chaque carte d'une photo (1 à N, classeur 3×3) | CH2 (chimera) | 12 oct. → 15 oct. | v3-ia-providers | — | À faire | [prompt](prompts/v3-detection.md) |
| `v3-identification` | P0 | Identifier chaque carte et la rapprocher du catalogue (top 3 avec confiance) | CH2 (chimera) | 16 oct. → 22 oct. | v3-detection, v2-recherche | — | À faire | [prompt](prompts/v3-identification.md) |
| `v3-identification-visuelle` | P1 | Identifier sans IA : comparer chaque carte détectée aux images officielles de la base | CH3 (chimera) | 23 oct. → 29 oct. | v3-identification, v2-catalogue-complet | — | À faire | [prompt](prompts/v3-identification-visuelle.md) |
| `v3-validation` | P0 | Écran de validation : vérifier, corriger et ajouter les cartes reconnues | CH4 (chimera) | 23 oct. → 27 oct. | v3-identification, v3-upload | — | À faire | [prompt](prompts/v3-validation.md) |
| `v3-etat` | P1 | Estimation de l'état de la carte (centrage, coins, bords, surface) | CH2 (chimera) | 23 oct. → 27 oct. | v3-identification | — | À faire | [prompt](prompts/v3-etat.md) |

## V4 — La collection et ses fiches (26 oct. → 6 nov.)

_Une fois les cartes connues, on les parcourt, on les filtre, on les valorise, et chaque carte raconte son histoire._

| Lot | Prio | Titre | Couloir | Prévu | Dépend de | Décision | Statut | Prompt |
|---|---|---|---|---|---|---|---|---|
| `v4-ranking` | P1 | Classement (« ranking ») de chaque carte | DA1 (devAI) | 26 oct. → 27 oct. | v2-prix | D6 | À faire | [prompt](prompts/v4-ranking.md) |
| `v4-collection` | P0 | Page collection : grille, filtres, tris et valeur totale | CH1 (chimera) | 28 oct. → 30 oct. | v3-validation, v2-prix | — | À faire | [prompt](prompts/v4-collection.md) |
| `v4-anecdotes` | P1 | Histoire et anecdotes de la carte (sourcées) | CH2 (chimera) | 28 oct. → 30 oct. | v3-ia-providers, v2-catalogue | — | À faire | [prompt](prompts/v4-anecdotes.md) |
| `v4-fiche` | P0 | Fiche carte : image officielle, ma photo, état, valeur dans le temps, histoire | CH4 (chimera) | 2 nov. → 5 nov. | v4-collection, v4-ranking, v4-anecdotes, v3-etat | — | À faire | [prompt](prompts/v4-fiche.md) |
| `v4-jeu` | P2 | Étude d'utilisation en jeu (légalité, attaques, présence en tournoi) | CH2 (chimera) | 2 nov. → 5 nov. | v4-anecdotes | — | À faire | [prompt](prompts/v4-jeu.md) |
| `v4-dashboard` | P1 | Accueil connecté : valeur de la collection, hausses et baisses, derniers ajouts | CH1 (chimera) | 2 nov. → 3 nov. | v4-collection | — | À faire | [prompt](prompts/v4-dashboard.md) |
| `v4-insights-batch` | P1 | Pré-générer histoire et étude en jeu de TOUTES les cartes, en un seul passage par carte | CH2 (chimera) | 6 nov. → 12 nov. | v4-jeu, v2-catalogue-complet | D4 | À faire | [prompt](prompts/v4-insights-batch.md) |

## V5 — En ligne (26 oct. → 20 nov.)

_Un espace qui garde des clés IA et des photos privées ne sort qu'après une revue de sécurité et avec des données exportables._

| Lot | Prio | Titre | Couloir | Prévu | Dépend de | Décision | Statut | Prompt |
|---|---|---|---|---|---|---|---|---|
| `v5-rgpd` | P1 | Exporter mes données et supprimer mon compte | DA1 (devAI) | 28 oct. → 29 oct. | v1-byok | — | À faire | [prompt](prompts/v5-rgpd.md) |
| `v5-e2e` | P1 | Parcours e2e Playwright en CI | CH3 (chimera) | 6 nov. → 11 nov. | v4-fiche | — | À faire | [prompt](prompts/v5-e2e.md) |
| `v5-securite` | P0 | Revue de sécurité avant ouverture | DA1 (devAI) | 9 nov. → 12 nov. | v4-fiche, v5-rgpd, v3-validation | — | À faire | [prompt](prompts/v5-securite.md) |
| `v5-prod` | P0 | Mise en PROD : domaine, sauvegardes, surveillance | DA2 (devAI) | 16 nov. → 20 nov. | v5-securite, v5-e2e, v1-uat | D8 | À faire | [prompt](prompts/v5-prod.md) |

## V6 — Après le MVP (23 nov. → 18 déc.)

_Ce qui rend le produit meilleur que la concurrence, une fois le socle en service._

| Lot | Prio | Titre | Couloir | Prévu | Dépend de | Décision | Statut | Prompt |
|---|---|---|---|---|---|---|---|---|
| `v6-contrefacon` | P2 | Détection des contrefaçons probables | CH2 (chimera) | 23 nov. → 2 déc. | v3-etat | — | À faire | [prompt](prompts/v6-contrefacon.md) |
| `v6-alertes` | P2 | Alertes de prix et récapitulatif hebdomadaire par e-mail | CH3 (chimera) | 23 nov. → 25 nov. | v4-dashboard | — | À faire | [prompt](prompts/v6-alertes.md) |
| `v6-pwa` | P2 | Application mobile installable (PWA) et scan en direct | CH1 (chimera) | 23 nov. → 4 déc. | v5-prod | — | À faire | [prompt](prompts/v6-pwa.md) |
| `v6-import-export` | P3 | Import/export CSV et liste de souhaits | DA1 (devAI) | 23 nov. → 27 nov. | v5-prod | — | À faire | [prompt](prompts/v6-import-export.md) |
| `v6-gradation` | P3 | Cartes gradées (PSA, PCA, CGC) | CH3 (chimera) | 30 nov. → 4 déc. | v5-prod | — | À faire | [prompt](prompts/v6-gradation.md) |

## Décisions de JF

| # | Avant le | Décision | Prise | Débloque |
|---|---|---|---|---|
| D1 | 2026-09-22 | Valider la stack : Next.js + FastAPI + PostgreSQL 16 + Redis/arq, monorepo pnpm + uv. | GO de JF le 19/09 : « parfait go implementation sur chimaera » puis « tu me fais tout un MVP en un coup ». Stack validée, tout le MVP s'implémente sur chimera. | v0-monorepo |
| D5 | 2026-09-26 | Nom de domaine et fournisseur d'e-mails transactionnels (vérification d'adresse, mot de passe oublié) : Brevo, Resend ou SMTP existant. | Domaine choisi par JF le 19/09 : PROD https://pokeboy.acx-connect.com, UAT https://uat.pokeboy.acx-connect.com (enregistrements A vers 5.22.213.226, serveur de kailo.life / ACX ; acx-connect.com y pointe déjà). Fournisseur d'e-mails : DÉFAUT PROVISOIRE du pilote — SMTP configurable (Mailpit en dev) ; expéditeur prévu no-reply@acx-connect.com (MX Google Workspace) à confirmer par JF. | v1-auth |
| D2 | 2026-10-02 | Hébergement UAT/PROD : nouveau petit VPS UpCloud (compte kailo) ou machine `sites-and-crons` ; base PostgreSQL managée ou conteneur + sauvegardes. | JF le 19/09 : UAT et PROD hébergées sur le même serveur que kailo.life (UpCloud « sites-and-crons », STARTER-2xCPU-4GB, de-fra1). Conséquences : images construites sur chimera et tirées par le serveur (aucun build sur place : 2 cœurs / 4 Go déjà partagés avec kailo.life et ACX) ; Caddy/proxy existant à étendre ; ressources à mesurer avant la PROD ; accès root absent sur cette machine à vérifier pour le lot v1-uat. | v1-uat, v5-prod |
| D3 | 2026-10-02 | Source de prix : gratuit (Cardmarket via TCGdex + TCGplayer, historique construit par nos relevés) ou payant (historique rétroactif, ex. PriceCharting). | DÉFAUT PROVISOIRE du pilote (à confirmer par JF) : sources gratuites (Cardmarket via TCGdex, TCGplayer via Pokémon TCG API) ; historique construit par nos relevés quotidiens ; source payante branchable plus tard. | v2-prix |
| D4 | 2026-10-05 | Sans clé IA personnelle : reconnaissance désactivée (saisie manuelle seulement) ou quota d'essai offert sur une clé plateforme (coût à plafonner). | RÉVISÉE par JF le 19/09 : « autant tout prendre dès le premier tir » — une clé IA PLATEFORME sert à pré-générer l'histoire et l'étude en jeu de toutes les cartes (lot v4-insights-batch, budget plafonné). Sans clé personnelle, la reconnaissance reste désactivée (ajout manuel possible). À FOURNIR par JF : la clé plateforme (distincte de celle d'Aymeric) et le budget maximal. | v1-byok, v4-insights-batch |
| D7 | 2026-10-07 | Stockage des photos (Object Storage UpCloud ou disque du VPS) et durée de conservation des photos d'origine. | DÉFAUT PROVISOIRE (recommandation devAI du 19/09, à confirmer par JF) : photos sur le disque local du serveur (/srv/pokeboy/<env>/data/photos) au lancement ; l'application garde une interface de stockage à deux implémentations (disque local en UAT/PROD, S3/MinIO en dev) ; UpCloud Object Storage à chiffrer si le volume l'exige. Photos conservées jusqu'à suppression. | v3-upload |
| D6 | 2026-10-23 | Définir le « ranking » affiché sur la fiche : rang de rareté, rang de valeur dans la collection, percentile dans l'extension — un, deux ou les trois. | DÉFAUT PROVISOIRE du pilote (à confirmer par JF) : les trois classements — rang de rareté, rang de valeur dans la collection, percentile de valeur dans l'extension. | v4-ranking |
| D8 | 2026-11-13 | Ouverture : sur invitation ou inscription libre ; nom public et mention « non affilié à Nintendo / The Pokémon Company ». | en attente | v5-prod |
