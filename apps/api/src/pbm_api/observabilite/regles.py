"""Les **seuils d'alerte** du jeu — purs, donc éprouvables sans base ni serveur de mail.

Ce module décide d'une seule chose : *ce relevé mérite-t-il de réveiller quelqu'un ?* Il ne lit
rien et n'envoie rien ; la sonde (``apps/api/scripts/sonde_jeu.py``) et la route
``GET /jeu/metriques`` l'appellent tous les deux, et obtiennent donc le **même** verdict — une
métrique consultée à l'écran ne peut pas contredire l'e-mail reçu le matin.

Les seuils sont calibrés pour **deux ou trois joueurs**, pas pour un service public : à ce volume,
une seule erreur de moteur est un événement, et une rafale de refus se compte en dizaines, pas en
milliers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from pbm_api.observabilite.releve import Releve

#: Il faut agir maintenant : le jeu a produit un résultat faux ou a planté.
GRAVITE_CRITIQUE = "critique"
#: Il faut regarder : rien n'est cassé de façon certaine, mais la forme du trafic est anormale.
GRAVITE_AVERTISSEMENT = "avertissement"

#: Nombre de refus en dessous duquel on ne juge pas le taux : à trois joueurs, deux coups
#: refusés sur trois un dimanche matin n'est pas un signal — c'est quelqu'un qui apprend.
SEUIL_REFUS_VOLUME = 30
#: Part des coups soumis refusés au-delà de laquelle on alerte (avec le volume ci-dessus).
SEUIL_REFUS_TAUX = 0.25
#: Un motif qui concentre cette part des refus désigne une règle précise — donc un bug d'interface
#: (l'écran propose un coup que le moteur refuse) plutôt qu'un joueur qui apprend.
SEUIL_MOTIF_DOMINANT_PART = 0.6
#: … à partir de ce nombre de refus seulement, pour ne pas alerter sur « 3 refus sur 4 ».
SEUIL_MOTIF_DOMINANT_VOLUME = 10
#: Délai au-delà duquel l'absence de récapitulatif hebdomadaire est elle-même une panne : la sonde
#: ne tourne plus, ou n'arrive plus à écrire. 8 jours, pas 7 : un envoi décalé d'une heure ne doit
#: pas déclencher d'alerte.
DELAI_RECAP_HEBDO_J = 8

#: Part du plafond de parties simultanées au-delà de laquelle on prévient (lot
#: ``j-charge-temps-reel``). 0,8 et pas 1,0 : à 1,0 l'alerte arrive *en même temps* que le premier
#: joueur refusé, donc trop tard pour être une alerte — elle ne serait qu'un constat.
SEUIL_CAPACITE_FROLEE = 0.8


@dataclass(frozen=True)
class Alerte:
    """Une alerte : un ``code`` stable (pour dédoublonner), une gravité, un message en français."""

    code: str
    gravite: str
    message: str


def evaluer(releve: Releve) -> list[Alerte]:
    """Les alertes de ce relevé, des plus graves aux moindres (liste vide = tout va bien).

    Cinq signaux, chacun répondant à une mission du lot :

    1. **erreur de moteur** (> 0) — critique, sans seuil : le moteur fait autorité, s'il plante
       le jeu a pu produire un état faux. « Toute erreur de moteur est une alerte, jamais une
       ligne de journal » est un critère d'acceptation, pas une préférence ;
    2. **rafale de refus** — volume *et* taux : une hausse signale un bug d'interface (l'écran
       propose un coup illégal) ou une tentative de triche (client modifié) ;
    3. **motif dominant** — un seul ``R-x.y`` concentre les refus : la règle est nommée ;
    4. **capacité** — le plafond de parties simultanées est frôlé (avertissement) ou atteint
       (critique, des joueurs sont refusés) : lot ``j-charge-temps-reel`` ;
    5. **parties qui n'aboutissent pas** — en cours mais sans coup depuis trop longtemps.

    Les parties refusées pour carte non scriptée (D9) ne sont **pas** une alerte : c'est le
    comportement voulu (le jeu refuse plutôt que d'approximer). Elles restent **comptées** et
    figurent au récapitulatif — c'est la mesure de la couverture des cartes, pas une panne.
    """
    alertes: list[Alerte] = []

    if releve.erreurs_moteur > 0:
        alertes.append(
            Alerte(
                code="erreur_moteur",
                gravite=GRAVITE_CRITIQUE,
                message=(
                    f"{releve.erreurs_moteur} erreur(s) de moteur en {releve.fenetre_heures} h. "
                    "Le moteur fait autorité : une exception inattendue peut avoir produit un "
                    "état faux. Chercher le genre « erreur_moteur » dans jeu_incidents."
                ),
            )
        )

    if releve.refus >= SEUIL_REFUS_VOLUME and releve.taux_refus > SEUIL_REFUS_TAUX:
        alertes.append(
            Alerte(
                code="rafale_refus",
                gravite=GRAVITE_AVERTISSEMENT,
                message=(
                    f"{releve.refus} coup(s) refusé(s) en {releve.fenetre_heures} h, soit "
                    f"{releve.taux_refus:.0%} des coups soumis (seuil "
                    f"{SEUIL_REFUS_TAUX:.0%}). Soit l'écran propose des coups que le moteur "
                    "refuse, soit un client a été modifié."
                ),
            )
        )

    dominant = releve.motif_dominant
    if dominant is not None:
        motif, compte = dominant
        if compte >= SEUIL_MOTIF_DOMINANT_VOLUME and compte / releve.refus >= (
            SEUIL_MOTIF_DOMINANT_PART
        ):
            alertes.append(
                Alerte(
                    code="motif_dominant",
                    gravite=GRAVITE_AVERTISSEMENT,
                    message=(
                        f"{compte} des {releve.refus} refus portent le même motif « {motif} » "
                        f"({compte / releve.refus:.0%}). Une règle précise est en cause : lire "
                        "docs/jeu/REGLES.md à cet identifiant."
                    ),
                )
            )

    if releve.capacite_plafond > 0 and releve.capacite_taux >= SEUIL_CAPACITE_FROLEE:
        # Critique seulement quand le plafond est **atteint** : à ce moment-là des joueurs sont
        # effectivement refusés (503), ce n'est plus un risque mais une panne de service.
        atteint = releve.parties_actives >= releve.capacite_plafond
        alertes.append(
            Alerte(
                code="capacite_atteinte" if atteint else "capacite_frolee",
                gravite=GRAVITE_CRITIQUE if atteint else GRAVITE_AVERTISSEMENT,
                message=(
                    f"{releve.parties_actives} partie(s) simultanée(s) pour un plafond de "
                    f"{releve.capacite_plafond} ({releve.capacite_taux:.0%}). "
                    + (
                        "Toute nouvelle partie est refusée en 503. Agrandir le serveur ou relever "
                        "le plafond — avec une mesure à l'appui (docs/jeu/CHARGE.md)."
                        if atteint
                        else "Il reste peu de places : regarder la taille du serveur maintenant, "
                        "pas le soir où un joueur reçoit un 503 (docs/jeu/CHARGE.md)."
                    )
                ),
            )
        )

    if releve.parties_bloquees > 0:
        alertes.append(
            Alerte(
                code="parties_bloquees",
                gravite=GRAVITE_AVERTISSEMENT,
                message=(
                    f"{releve.parties_bloquees} partie(s) en cours sans aucun coup depuis "
                    "longtemps : elles n'aboutissent pas. Vérifier que l'expiration des parties "
                    "fantômes tourne (expirer_parties) et qu'aucun coup système ne reste coincé."
                ),
            )
        )

    ordre = {GRAVITE_CRITIQUE: 0, GRAVITE_AVERTISSEMENT: 1}
    return sorted(alertes, key=lambda a: (ordre.get(a.gravite, 9), a.code))


def alerte_recap_manquant(dernier_envoi: date | None, aujourdhui: date) -> Alerte | None:
    """L'absence de récapitulatif hebdomadaire, transformée en **signal** (``None`` si à jour).

    C'est l'« homme mort » du dispositif, sur le modèle du récapitulatif de 08:00 de la sonde
    d'infrastructure : si personne ne vérifie que le récapitulatif *part*, son silence se confond
    avec « rien à signaler ». La sonde quotidienne lit donc la date du dernier envoi dans son
    fichier d'état et appelle cette fonction : plus de récapitulatif depuis
    :data:`DELAI_RECAP_HEBDO_J` jours = alerte, y compris quand le jeu lui-même va bien.

    ``dernier_envoi`` à ``None`` (sonde jamais passée en mode hebdomadaire) est traité comme un
    retard : une sonde qui n'a jamais envoyé n'est pas une sonde qui va bien.
    """
    if dernier_envoi is None:
        return Alerte(
            code="recap_hebdo_jamais_envoye",
            gravite=GRAVITE_AVERTISSEMENT,
            message=(
                "Aucun récapitulatif hebdomadaire n'a jamais été envoyé : vérifier que la sonde "
                "est bien planifiée en mode hebdomadaire (voir docs/jeu/OBSERVABILITE.md)."
            ),
        )
    retard = aujourdhui - dernier_envoi
    if retard >= timedelta(days=DELAI_RECAP_HEBDO_J):
        return Alerte(
            code="recap_hebdo_manquant",
            gravite=GRAVITE_AVERTISSEMENT,
            message=(
                f"Aucun récapitulatif hebdomadaire depuis {retard.days} jours (dernier : "
                f"{dernier_envoi.isoformat()}). Son absence est un signal : la sonde ne tourne "
                "plus, ou n'écrit plus son état."
            ),
        )
    return None


def verdict(alertes: list[Alerte]) -> str:
    """Un mot qui résume la situation : ``PANNE``, ``A_SURVEILLER`` ou ``OK``.

    Même vocabulaire d'intention que la sonde des prix (``verdict:"PANNE"`` dans son fichier
    d'état, ``docs/infra/JOBS-LOURDS.md``) : on ne conclut jamais « tout va bien » par défaut,
    on le conclut parce que la liste d'alertes est vide.
    """
    if any(a.gravite == GRAVITE_CRITIQUE for a in alertes):
        return "PANNE"
    if alertes:
        return "A_SURVEILLER"
    return "OK"


__all__ = [
    "DELAI_RECAP_HEBDO_J",
    "GRAVITE_AVERTISSEMENT",
    "GRAVITE_CRITIQUE",
    "SEUIL_CAPACITE_FROLEE",
    "SEUIL_MOTIF_DOMINANT_PART",
    "SEUIL_MOTIF_DOMINANT_VOLUME",
    "SEUIL_REFUS_TAUX",
    "SEUIL_REFUS_VOLUME",
    "Alerte",
    "alerte_recap_manquant",
    "evaluer",
    "verdict",
]
