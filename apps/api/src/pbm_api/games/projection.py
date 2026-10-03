"""Point de sortie unique de l'API vers un client : la **vue autoritaire** d'une partie.

Le moteur `pbm_game` porte la projection pure (`pbm_game.sortie.projeter`) : état réduit à ce que
le joueur a le droit de voir, jetons opaques pour les cartes cachées, événements redécrits par
destinataire. Ce module est l'**adaptateur** qui l'alimente depuis les objets de la couche base :

* il dérive le **secret des jetons** de la graine de la partie (un secret serveur, jamais renvoyé) ;
* il dérive l'**époque** des jetons du journal du Rng — le nombre de mélanges du deck du joueur,
  pour que les jetons de ses récompenses changent à chaque mélange (non-corrélables) ;
* il mappe l'`user_id` de la session sur l'identifiant de joueur du moteur (`joueur_id_de`).

**Toute** sortie de partie vers un client passe par ici (routes HTTP de ce lot, canal temps réel du
lot `j-temps-reel`) : aucune route ne refiltre à la main, aucune donnée brute ne circule au-delà.
"""

from __future__ import annotations

import uuid

from pbm_game.journal.serialisation import evenement_depuis_json
from pbm_game.rng import Rng, flux_melange_deck
from pbm_game.sortie import Jetonneur, enrichir_indicateurs, projeter, secret_jetons
from pbm_game.state.modele import EtatPartie
from pbm_game.state.serialisation import depuis_json

from pbm_api.games.actions import actions_pour
from pbm_api.games.construction import joueur_id_de
from pbm_api.games.indicateurs import CatalogueAffichage
from pbm_api.games.service import ResultatAction


def _jetonneur(graine_hex: str, compteurs: dict[str, int], joueur_id: str) -> Jetonneur:
    """Le :class:`Jetonneur` du joueur : secret dérivé de la graine, époque = mélanges de son deck.

    L'époque est le nombre de tirages du flux de mélange du deck de ce joueur
    (`flux_melange_deck`) : chaque mélange la fait avancer, donc les jetons de ses récompenses
    changent à chaque mélange.
    """
    epoque = compteurs.get(flux_melange_deck(joueur_id), 0)
    return Jetonneur(secret=secret_jetons(bytes.fromhex(graine_hex)), epoque=epoque)


def vue_autoritaire(
    etat: EtatPartie,
    rng: Rng,
    *,
    user_id: uuid.UUID,
    graine_hex: str,
    catalogue: CatalogueAffichage,
    catalogue_jeu=None,
) -> dict:
    """La vue projetée de l'état courant pour `user_id`, sans événement (objets purs en entrée).

    Sert la route de consultation d'état : le client reçoit exclusivement ce que `projeter` autorise
    pour lui — jamais la main adverse, ni l'ordre d'une pioche, ni l'identité d'une récompense.
    """
    joueur_id = joueur_id_de(user_id)
    jetonneur = _jetonneur(graine_hex, rng.compteurs(), joueur_id)
    sortie = projeter(etat, (), pour=joueur_id, jetonneur=jetonneur)
    # Indicateurs d'affichage (lot ``j-plateau-etat-visuel``) : PV restants, types des énergies,
    # Outil — calculés par le moteur pur à partir des données du catalogue, pour que l'écran
    # dessine sans recalcul.
    enrichir_indicateurs(
        sortie["vue"],
        etat,
        pv_imprimes=catalogue.pv_imprimes,
        types=catalogue.types,
        registre=catalogue.registre,
    )
    # Actions légales du destinataire + commandes refusées motivées (lot j-plateau-interactions) :
    # l'écran illumine les cibles et grise les refus sans réécrire aucune règle.
    actions = actions_pour(etat, joueur_id, catalogue_jeu)
    sortie["vue"]["actions_legales"] = actions["legales"]
    sortie["vue"]["actions_refusees"] = actions["refusees"]
    return sortie


def projeter_resultat(
    resultat: ResultatAction,
    *,
    user_id: uuid.UUID,
    graine_hex: str,
    catalogue: CatalogueAffichage,
    catalogue_jeu=None,
) -> dict:
    """La vue projetée **après** un coup + les événements de ce coup, pour `user_id`.

    Réhydrate l'état et les événements (formes JSON portées par le :class:`ResultatAction`) pour les
    repasser par le point de sortie unique du moteur : on ne refiltre pas à la main ici, on délègue
    à `projeter`, qui retire la main adverse et redécrit la pioche selon le destinataire.
    """
    joueur_id = joueur_id_de(user_id)
    etat = depuis_json(resultat.etat)
    evenements = tuple(evenement_depuis_json(e) for e in resultat.evenements)
    jetonneur = _jetonneur(graine_hex, resultat.rng_compteurs, joueur_id)
    sortie = projeter(etat, evenements, pour=joueur_id, jetonneur=jetonneur)
    enrichir_indicateurs(
        sortie["vue"],
        etat,
        pv_imprimes=catalogue.pv_imprimes,
        types=catalogue.types,
        registre=catalogue.registre,
    )
    # Actions légales du destinataire + commandes refusées motivées (lot j-plateau-interactions) :
    # l'écran illumine les cibles et grise les refus sans réécrire aucune règle.
    actions = actions_pour(etat, joueur_id, catalogue_jeu)
    sortie["vue"]["actions_legales"] = actions["legales"]
    sortie["vue"]["actions_refusees"] = actions["refusees"]
    return sortie
