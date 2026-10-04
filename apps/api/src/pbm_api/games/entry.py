"""Vérification d'un deck **à l'entrée de la file** (lot `j-file-attente`).

Avant qu'un joueur entre dans la file d'attente, son deck doit être jouable — sinon l'appariement
fabriquerait une partie refusée à la création (:class:`~pbm_api.games.errors.CartesNonJouables`), et
le joueur attendrait pour rien. On vérifie donc **en amont**, et on dit précisément ce qui manque
(critère d'acceptation du lot : « le refus d'un deck nomme les cartes en cause et la raison »).

Trois contrôles, dans l'ordre :

1. **Propriété** — le deck appartient au joueur. Sinon :class:`DeckIntrouvable`, que la couche HTTP
   traduit en **404** (jamais 403 : pas de fuite d'existence, même règle que les decks et les
   parties). On ne file jamais avec le deck d'autrui.
2. **Compilation (D9)** — chaque carte se compile en une définition que le moteur sait manipuler
   (PV, stade, marqueur de règle, coût de retraite présents et cohérents). On réutilise
   :func:`pbm_api.games.construction.resoudre_deck`, exactement le contrôle que ferait la création
   de partie. Une carte dont la définition manque est nommée, avec sa raison.
3. **Scripts d'effet (D9, jalon J2)** — chaque **texte d'effet** porté par une carte (talent,
   attaque à effet, texte de Dresseur) a un script **scripté et lisible** au registre `card_scripts`
   (:func:`pbm_api.jeu.scripts.refus_scripts_deck`). C'est le passage du jalon J1 (« la carte est
   posable ») au J2 (« ce que la carte dit, le moteur le fait ») : un effet non scripté bloque la
   carte et le deck le dit, plutôt que d'être joué de travers. Une carte **sans** effet (dégâts
   secs, Énergie de base) n'exige aucun script — on ne resserre le jeu que là où un effet existe.

Les refus de compilation et de scripts sont **réunis** dans un seul :class:`DeckInjouable` : le
joueur voit d'un coup tout ce qui cloche dans son deck, pas une erreur à la fois.

**Pourquoi pas la légalité de format (60 cartes, max 4, possession en collection) ici.** Ces règles
de *construction* de deck existent déjà dans `pbm_api.decks.legality` (mission `v7-decks-legalite`)
et s'appliquent quand on **bâtit** un deck. Le service de parties livré (`j-partie-service` /
:func:`~pbm_api.games.service.creer_partie`) ne les impose pas : au jalon J1 (« laid
mais juste »), la mise en place réelle (main de sept, bancs, six récompenses, deck de 60) est le lot
`j-initialisation`, pas encore livré. Imposer la légalité tournoi à l'entrée rendrait le jeu
injouable avec les decks minimaux d'aujourd'hui et contredirait le moteur. La porte « deck légal »
s'ajoutera ici quand `j-initialisation` fera du deck complet l'unité de jeu — report explicite, pas
un abandon silencieux.

Ce module vit dans `apps/api` (il lit la base) : le moteur `pbm_game` reste pur.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.games.construction import joueur_id_de, resoudre_deck
from pbm_api.games.errors import GameError
from pbm_api.jeu.scripts import refus_scripts_deck
from pbm_api.models import Deck


class DeckIntrouvable(GameError):
    """Le deck n'existe pas, ou n'appartient pas au joueur (→ 404, jamais 403).

    Comme pour un deck ou une partie d'autrui : on ne révèle pas l'existence d'un objet qui n'est
    pas le vôtre. La couche HTTP répond 404 sans distinguer les deux cas.
    """


class DeckInjouable(GameError):
    """Le deck du joueur porte une ou plusieurs cartes non jouables (→ 422), cartes **nommées**.

    `refus` est la liste des `(nom_ou_libellé, raison)`. Un effet non implémenté n'est jamais
    approximé (D9) : plutôt que d'apparier un deck qui serait refusé à la création, on refuse
    l'entrée dans la file en disant exactement ce qui manque — qu'il s'agisse d'une carte qui ne se
    compile pas (donnée manquante) ou d'un effet sans script validé.
    """

    def __init__(self, refus: list[tuple[str, str]]) -> None:
        self.refus = refus
        details = " ; ".join(f"« {nom} » : {raison}" for nom, raison in refus)
        super().__init__(
            f"Deck non jouable, entrée refusée : {len(refus)} carte(s) — {details}"
        )


async def verifier_deck(db: AsyncSession, user_id: uuid.UUID, deck_id: uuid.UUID) -> None:
    """Vérifie qu'un deck est jouable à l'entrée de la file, ou **lève** en nommant ce qui manque.

    Lève :class:`DeckIntrouvable` si le deck n'est pas celui du joueur (→ 404), ou
    :class:`DeckInjouable` si une carte ne se compile pas pour le moteur **ou** si un de ses effets
    n'a pas de script validé (→ 422, cartes nommées). Ne renvoie rien en cas de succès : l'appelant
    (la file, le lancement) sait alors que l'appariement aboutira et que les cartes se jouent.
    """
    deck = await db.get(Deck, deck_id)
    if deck is None or deck.user_id != user_id:
        raise DeckIntrouvable(f"Deck {deck_id} introuvable.")

    _cartes, refus_compilation = await resoudre_deck(db, deck_id, joueur_id_de(user_id))
    refus_scripts = await refus_scripts_deck(db, deck_id)
    refus = refus_compilation + refus_scripts
    if refus:
        raise DeckInjouable(refus)
