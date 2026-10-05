"""Du registre `card_scripts` aux **scripts DSL validés**, prêts pour le moteur (lot
`j-effets-cablage-service`).

Le :mod:`~pbm_api.jeu.scripts.chargeur` ne rend que des **refus** (la porte D9 du deck) ; il ne
produit jamais de script utilisable. Ce module est l'autre moitié du pont : il rend, pour une liste
d'empreintes de texte, le **script DSL (JSON) validé** de chaque effet `scripte` dont le programme
se recharge. L'assemblage du :class:`~pbm_game.actions.familles_jeu.CatalogueJeu` l'emploie pour :

* les **attaques à effet** — le JSON part tel quel dans ``AttaqueDef.script`` (le moteur le charge
  et le valide à la construction de la définition) ;
* les **Objets / Supporters** — le JSON est compilé en
  :class:`~pbm_game.effets.dsl.modele.Programme`
  via :func:`programme_depuis_json`, pour ``DefinitionObjet`` / ``DefinitionSupporter``.

Une empreinte sans script `scripte`, ou dont le programme ne se recharge plus (version future,
vocabulaire changé), est simplement **absente** du résultat (D9) : l'assemblage omet alors la carte
(Objet/Supporter) ou l'attaque devient non jouable, jamais approximée. Même porte que le chargeur,
vue du côté positif.

Ce module lit la base (il vit dans `apps/api`) ; le moteur `pbm_game` reste pur.
"""

from __future__ import annotations

from collections.abc import Iterable

from pbm_game.effets.dsl.chargement import ProgrammeInvalide, charger_programme
from pbm_game.effets.dsl.modele import Programme
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.jeu.scripts.depot import scripts_par_empreintes
from pbm_api.models.card_scripts import SCRIPT_STATUT_SCRIPTE


async def scripts_valides_par_empreinte(
    db: AsyncSession, empreintes: Iterable[str]
) -> dict[str, dict]:
    """Les **scripts DSL (JSON) validés** des effets `scripte`, par empreinte de texte.

    Une seule requête (``scripts_par_empreintes``). Ne retient qu'un script au statut `scripte` dont
    le ``script`` se **recharge** par l'interprète (``charger_programme``) — exactement la garde du
    chargeur, mais elle **renvoie** le JSON au lieu de refuser. Les empreintes sans script valide
    sont absentes (D9). Le JSON renvoyé est le programme brut : l'appelant le passe tel quel à
    ``AttaqueDef.script``, ou le compile par :func:`programme_depuis_json` pour un Objet/Supporter.
    """
    scripts = await scripts_par_empreintes(db, empreintes)
    valides: dict[str, dict] = {}
    for empreinte, script in scripts.items():
        if script.statut != SCRIPT_STATUT_SCRIPTE or script.script is None:
            continue
        try:
            charger_programme(script.script)
        except ProgrammeInvalide:
            # Script devenu illisible (version future, vocabulaire changé) : omis (D9). Le chargeur
            # le refuse déjà à l'entrée du deck ; ici on ne fabrique simplement pas de définition.
            continue
        valides[empreinte] = script.script
    return valides


def programme_depuis_json(script: dict) -> Programme:
    """Compile un script DSL (JSON validé) en :class:`Programme` — pour un Objet/Supporter."""
    return charger_programme(script)


__all__ = ["scripts_valides_par_empreinte", "programme_depuis_json"]
