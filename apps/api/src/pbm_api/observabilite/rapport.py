"""Mise en forme des messages de supervision du jeu — pure, donc testable sans serveur de mail.

Deux corps de texte, et un seul endroit où ils vivent :

* :func:`texte_alerte` — ce qui part quand quelque chose cloche ;
* :func:`texte_recap_hebdo` — le récapitulatif hebdomadaire des parties jouées.

Texte brut, pas de HTML : ces messages sont lus sur un téléphone, souvent en diagonale, et doivent
dire en première ligne **ce qui se passe** — jamais obliger à ouvrir un tableau de bord pour le
savoir. Aucune donnée nominative (ni adresse, ni pseudo) n'y figure : les compteurs sont agrégés,
la ventilation par compte reste en base, pour l'administration.
"""

from __future__ import annotations

from pbm_api.observabilite.regles import Alerte, verdict
from pbm_api.observabilite.releve import Releve

#: Largeur de la ligne de séparation des sections — lisible en police à chasse fixe comme en
#: proportionnelle, sans dépendre d'un client de messagerie.
_TRAIT = "-" * 60


def _lignes_releve(releve: Releve) -> list[str]:
    """Le relevé en lignes « libellé : valeur », dans l'ordre où on veut le lire."""
    lignes = [
        f"Parties en cours            : {releve.parties_en_cours}",
        f"  dont sans coup récent     : {releve.parties_bloquees}",
        f"Parties créées              : {releve.parties_creees}",
        f"Parties terminées           : {releve.parties_terminees}",
    ]
    if releve.fins_par_raison:
        lignes.append("Fins par raison :")
        for raison, compte in sorted(releve.fins_par_raison.items()):
            lignes.append(f"  - {raison} : {compte}")
    if releve.duree_moyenne_minutes is not None:
        lignes.append(f"Durée moyenne               : {releve.duree_moyenne_minutes:.0f} min")
    if releve.coups_moyens is not None:
        lignes.append(f"Coups moyens par partie     : {releve.coups_moyens:.1f}")
    lignes += [
        f"Coups joués                 : {releve.coups_joues}",
        f"Coups refusés               : {releve.refus} ({releve.taux_refus:.0%} des soumis)",
    ]
    if releve.refus_par_motif:
        lignes.append("Refus par motif (règle citée) :")
        for motif, compte in sorted(
            releve.refus_par_motif.items(), key=lambda item: (-item[1], item[0])
        ):
            lignes.append(f"  - {motif} : {compte}")
    lignes += [
        f"Erreurs de moteur           : {releve.erreurs_moteur}",
        f"Parties refusées (D9)       : {releve.parties_refusees}",
        f"Expirations d'horloge       : {releve.expirations_horloge}",
        f"Désertions                  : {releve.desertions}",
    ]
    return lignes


def _lignes_alertes(alertes: list[Alerte]) -> list[str]:
    """Les alertes en clair, gravité en tête — ou une ligne qui dit qu'il n'y en a pas."""
    if not alertes:
        return ["Aucune alerte."]
    return [f"[{a.gravite.upper()}] {a.code} — {a.message}" for a in alertes]


def sujet_alerte(alertes: list[Alerte]) -> str:
    """Sujet de l'e-mail d'alerte : le verdict et le code le plus grave, lisibles sans ouvrir."""
    tete = alertes[0].code if alertes else "sans_objet"
    return f"[PokeBoy jeu] {verdict(alertes)} — {tete}"


def texte_alerte(releve: Releve, alertes: list[Alerte], *, instant: str) -> str:
    """Le corps de l'e-mail d'alerte : ce qui cloche d'abord, le relevé complet ensuite.

    ``instant`` est passé en paramètre (jamais lu depuis l'horloge ici) pour que la fonction reste
    pure : un même relevé rend toujours le même texte, et le test n'a pas à geler le temps.
    """
    lignes = [
        f"Supervision du jeu PokeBoyManager — {verdict(alertes)}",
        f"Relevé du {instant} sur les {releve.fenetre_heures} dernières heures.",
        "",
        _TRAIT,
        "CE QUI CLOCHE",
        _TRAIT,
        *_lignes_alertes(alertes),
        "",
        _TRAIT,
        "RELEVÉ",
        _TRAIT,
        *_lignes_releve(releve),
        "",
        "Détail des incidents : table `jeu_incidents` (genre, motif, detail).",
        "Métriques en ligne : GET /jeu/metriques (compte avec accès au jeu).",
        "Mode d'emploi : docs/jeu/OBSERVABILITE.md",
    ]
    return "\n".join(lignes)


def texte_recap_hebdo(releve: Releve, alertes: list[Alerte], *, instant: str) -> str:
    """Le corps du récapitulatif hebdomadaire : les parties jouées, puis ce qui reste à surveiller.

    Il part **même quand tout va bien** : c'est ce qui en fait un homme mort — son absence devient
    un signal (:func:`pbm_api.observabilite.regles.alerte_recap_manquant`).
    """
    lignes = [
        "Récapitulatif hebdomadaire du jeu PokeBoyManager",
        f"Semaine arrêtée au {instant} ({releve.fenetre_heures} h observées).",
        "",
        _TRAIT,
        "LES PARTIES",
        _TRAIT,
        *_lignes_releve(releve),
        "",
        _TRAIT,
        "À SURVEILLER",
        _TRAIT,
        *_lignes_alertes(alertes),
        "",
        "Ce message part chaque semaine, même quand tout va bien : son ABSENCE est une panne",
        "(la sonde ne tourne plus). Voir docs/jeu/OBSERVABILITE.md.",
    ]
    return "\n".join(lignes)


def sujet_recap_hebdo(releve: Releve) -> str:
    """Sujet du récapitulatif : le nombre de parties jouées, visible dans la liste des messages."""
    return (
        f"[PokeBoy jeu] Récapitulatif hebdo — {releve.parties_creees} partie(s) créée(s), "
        f"{releve.parties_terminees} terminée(s)"
    )


__all__ = [
    "sujet_alerte",
    "sujet_recap_hebdo",
    "texte_alerte",
    "texte_recap_hebdo",
]
