# fix-projection-evenements — sept (puis dix) événements sans projecteur : le 500 des coups du joueur

**Lot hors plan**, ouvert le 03/10/2026 après le double blocage de `livraison-jeu-coups` (13:07 et
13:22). Objectif : rendre le jeu **jouable** — qu'un vrai coup ne fasse plus 500 — et **blinder** la
faille pour qu'elle casse en CI, jamais plus en PROD.

## Le défaut

`docs/LIVRAISON.md` (« Tentative de livraison des coups du joueur — 03/10/2026 — BLOQUÉE ») : la
mise en place et `j-coups-joueur` émettent des événements absents du registre `PROJECTEURS`
(`apps/game/src/pbm_game/sortie/evenements.py`). `projeter_evenement` **refuse** à raison tout type
inconnu (jamais de repli silencieux) ; donc `POST /games/{id}/actions` (`placer_mise_en_place`)
répondait **500** et le WebSocket ne diffusait rien. La CI était verte parce que les tests de partie
complète passent par `appliquer_action` / `reprendre_partie`, **jamais** par le point de sortie
`projeter` / `projeter_resultat`.

Reproduit localement au premier coup réel : `POST .../actions` `placer_mise_en_place` → **500**.

## Ce qui a été fait

### 1. Les sept événements nommés — et leur décision de visibilité

Chacun déclaré dans `PROJECTEURS` avec sa règle, en docstring et dans `docs/jeu/AUTORITE-VUES.md`
(cité à `REGLES.md`) :

| Événement | Règle | Décision |
|---|---|---|
| `placement_cache` | R-4.2 | **public** : l'événement ne porte **que** le joueur — le contenu posé face cachée n'y figure jamais (garanti à l'émission). L'adversaire sait seulement que l'autre a placé. |
| `mise_en_place_revelee` | R-4.2/R-4.3 | **public** : la révélation **rend** Actif et banc publics (refs, nombres de récompenses/bonus). |
| `mulligan` | R-4.5 | **public** : numéro de mulligan et à qui revient l'éventuelle carte bonus — aucune identité de carte. |
| `main_revelee` | R-4.4 | **projecteur dédié `_main_revelee`** : la main révélée est montrée à l'**adversaire** par ses `ref` seulement, **jamais** les `instance_id` (ces cartes retournent dans la pioche cachée → un `instance_id` serait un repère de suivi ; règle muette sur ce point ⇒ **moins révélateur**). Le propriétaire voit sa main entière. |
| `mise_en_place_prete` | R-4.5 | **public** : résumé (mulligans, bonus par joueur). |
| `fin_tour` | R-5.8 | **public** : joueur et phase quittée. |
| `energie_attachee` | R-5.4 | **public** : attacher une énergie est un geste visible (zone en jeu). |

### 2. Un huitième, puis dix autres : la faille était plus large que `journal.modele`

Le test de partie complète par HTTP (point 3) a débusqué un **8ᵉ** type — `cout_paye` — défini dans
`combat/cout.py`, **hors** de `journal.modele`. En remontant toutes les constantes `EVT_*` du
moteur, dix vivent hors `journal.modele` (combat, effets, DSL, demandes). Décision :

- **Publics, déclarés** (`_public`) : `cout_paye` (R-9.2 : payé par des énergies **attachées**,
  donc publiques), `effet_resolu`, `effet_sans_cible`, `verrou_pose`, `verrou_leve`,
  `dsl_pile_ou_face`, `dsl_cout_impayable` — ne portent que des faits publics.
- **Différés nommément** (`DIFFERES_SYSTEME_EFFETS`) : `demande_emise`, `demande_repondue`,
  `demande_expiree`, `dsl_choix`, `dsl_primitive` — ils **peuvent** porter des identités cachées
  (une primitive `piocher`/`chercher` nomme la carte tirée). Leur projection **par destinataire**
  relève du **lot des effets de carte** ; aucune partie J1 ne les émet. Tenus **hors** de
  `PROJECTEURS` : `projeter_evenement` les refuse (500 bruyant plutôt que fuite) — comportement
  voulu avant leur livraison, et nommé, pas silencieux.

### 3. Deux tests de parité (la garde qui aurait attrapé le bug)

- `apps/game/tests/test_parite_evenements_projecteurs.py` : relève **par lecture statique** toutes
  les `EVT_*` de **tout** `pbm_game` et exige que chacune soit **projetée ou nommément différée**.
  Un futur événement sans projecteur casse en CI. Un second test interdit qu'un différé soit aussi
  dans `PROJECTEURS` (pas de « public » par mégarde) et qu'un différé périmé y traîne.
- `apps/game/tests/test_parite_journal_front.py` (existant) garde l'autre bout : tout
  `PROJECTEURS` a sa traduction dans `apps/web/src/lib/game/journal.ts` (sept traducteurs combat /
  effets ajoutés, plus les sept de la mise en place / timer).

### 4. Une partie complète par les **routes HTTP et le WebSocket**

`apps/api/tests/test_games_http_ws_partie_complete.py` : deux comptes (UUID et graine **fixes** →
mise en place reproductible, mulligan inclus), decks Pokémon + Énergies de base contre cibles à
récompenses. Chaque coup — de `placer_mise_en_place` (le coup qui faisait 500) à la victoire par les
récompenses — est joué par la **vraie route HTTP** (donc par `projeter_resultat`) et diffusé sur le
`HUB` temps réel à deux abonnés. À chaque coup :

- **200** (plus de 500 de projection) — le scénario exact de la livraison bloquée ;
- **diffusion aux deux joueurs** : chacun reçoit un message projeté pour lui ;
- **aucune fuite** : aucun `instance_id` d'une zone cachée au destinataire (deux pioches, deux lots
  de récompenses, main adverse — dont les Pokémon posés **face cachée avant révélation**) n'apparaît
  dans sa vue, par parcours **structurel** de la vue (comparaison par `instance_id`, pas par
  sous-chaîne).

Le **mulligan** a lieu à la mise en place système (coup #0, posé avant tout abonné) : sa narration
ne transite pas par le chemin « coup joueur », donc la projection de `main_revelee` est vérifiée au
niveau moteur (`test_sortie_projection`), et le test HTTP atteste seulement que le scénario rejoué
**contient** un mulligan.

## Preuves (local, devAI, `TZ=Europe/Paris`)

- `apps/game` : **880 tests** verts (dont `test_sortie_projection` enrichi : non-fuite `_main_revelee`
  + projection des 7 types ; `test_parite_evenements_projecteurs` ×2).
- `apps/api` : la partie complète HTTP/WS verte ; **140 tests** « game/jeu/temps/projection/ingame »
  verts.
- `ruff` propre sur `apps/game` et `apps/api` ; `apps/web/src/lib/game/journal.ts` sans erreur de
  type (les seules erreurs `tsc` observées sont des artefacts de résolution de modules du lancement
  croisé hors worktree, aucune dans `journal.ts`).

Avant correctif : `POST .../actions placer_mise_en_place` → **500** (reproduit). Après : **200**,
partie complète jouée jusqu'à `derniere_recompense`.

## Portée et limites

- La PROD n'est **pas** touchée (livraison à part, par devAI). Ce lot livre le **code gaté par les
  tests**, pas une mise en ligne.
- Le système d'effets de carte (demandes, DSL) reste à projeter **par destinataire** : c'est
  explicitement différé et nommé, pas oublié. À reprendre par le lot des effets avant qu'une carte
  au script DSL n'entre en jeu.

## Fichiers

- `apps/game/src/pbm_game/sortie/evenements.py` — 7 + 7 projecteurs, `_main_revelee` dédié.
- `apps/game/tests/test_parite_evenements_projecteurs.py` — **nouveau**.
- `apps/game/tests/test_sortie_projection.py` — tests `_main_revelee` + les 7 types.
- `apps/api/tests/test_games_http_ws_partie_complete.py` — **nouveau** (partie complète HTTP/WS).
- `apps/web/src/lib/game/journal.ts` — 14 traducteurs ajoutés + 3 aides.
- `docs/jeu/AUTORITE-VUES.md`, `docs/jeu/REGLES.md` — décisions de visibilité documentées.
