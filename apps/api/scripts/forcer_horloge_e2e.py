"""Épuise le **budget de temps** du joueur dont le compteur tourne, pour que l'e2e puisse prouver
le parcours dégradé « expiration d'horloge » (lot `j-e2e-deux-navigateurs`).

**Pourquoi un script, et pas une variable d'environnement.** Chaque partie **fige sa configuration
d'horloges à sa création** (`ConfigHorloges` voyage dans l'état, cf. `pbm_game.horloges.modele`) :
baisser `HORLOGE_PAR_TOUR_S` côté serveur ne raccourcit donc pas une partie déjà lancée, et le
baisser pour toute l'instance e2e ferait expirer le **parcours nominal** en cours de route. On agit
ici sur l'état d'UNE partie nommée, sans toucher ni à la configuration ni aux autres parties.

**Ce qui est écrit, et pourquoi exactement ça.** `premiere_echeance` vérifie le **budget total en
premier** (il « prime », DJ4) et n'expire qu'au-delà de la limite *plus* la tolérance réseau
(10 s par défaut). On pose donc le budget du joueur actif à 0 et on recule le départ de son
compteur de `RECUL_S` secondes : `passe >= budget + tolerance` est alors vrai, et la cause est
`budget` → `action_par_defaut` journalise `defaite_temps` (le joueur actif perd, `raison_fin` =
`temps_ecoule`). Avec un recul de 30 s on reste **sous** la limite par tour (90 s + 10 s), donc
aucune ambiguïté avec la cause `tour`, qui produirait un simple `fin_tour`.

**Qui déclenche réellement l'expiration** : personne ici. Il n'y a ni minuteur ni cron d'horloge —
le seul déclencheur en production est le **battement de cœur du WebSocket**, qui appelle
`expirer_horloge` à chaque silence de 20 s (`pbm_api.games.temps_reel.piloter_canal`). Le test
laisse donc les deux navigateurs ouverts et attend ; ce script ne fait que rendre l'expiration
*due*. Ni `GET /state` ni `GET /sync` ne la déclenchent.

Usage : uv run python scripts/forcer_horloge_e2e.py <game_id>
Sort un JSON `{"joueur", "status"}` — `joueur` est l'identifiant du joueur qui va perdre au temps.
"""

import asyncio
import json
import sys
import time
import uuid

from pbm_game.horloges import EtatHorloges

from pbm_api.db import async_session_factory
from pbm_api.models.games import Game

#: Recul (secondes) appliqué au départ du compteur actif. Doit dépasser la tolérance réseau
#: (10 s) pour que le budget soit jugé épuisé, et rester sous la limite par tour (90 s) pour que
#: la cause retenue soit bien `budget` et non `tour`.
RECUL_S = 30.0


async def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)
    game_id = uuid.UUID(sys.argv[1])

    async with async_session_factory() as session:
        game = await session.get(Game, game_id)
        if game is None:
            raise SystemExit(f"partie {game_id} introuvable")
        if game.horloges is None:
            raise SystemExit(f"partie {game_id} sans horloges (pas encore démarrée ?)")

        etat = EtatHorloges.depuis_json(game.horloges)
        if etat.actif is None:
            raise SystemExit(f"partie {game_id} : aucun compteur actif (partie terminée ?)")

        joueur = etat.actif.joueur
        epuise = EtatHorloges(
            config=etat.config,
            budgets_s={**etat.budgets_s, joueur: 0.0},
            actif=type(etat.actif)(
                joueur=joueur, genre=etat.actif.genre, depuis=time.time() - RECUL_S
            ),
            pause_depuis=etat.pause_depuis,
            pause_joueur=etat.pause_joueur,
        )
        game.horloges = epuise.en_json()
        await session.commit()

        print(json.dumps({"joueur": joueur, "status": game.status}))


if __name__ == "__main__":
    asyncio.run(main())
