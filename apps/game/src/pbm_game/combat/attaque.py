"""Résolution complète d'une **attaque déclarée** — coût, effet scripté, dégâts, K.O. (R-9/10/13).

Module **pur** (aucune E/S). Il **branche** sur la déclaration d'attaque la machinerie déjà livrée :
:func:`pbm_game.combat.cout.payer_cout` (R-9.2), le **langage d'effets** (lot ``j-effets-dsl``,
:func:`pbm_game.effets.dsl.executer_programme`), :func:`pbm_game.combat.resolution.resoudre_degats`
(l'ordre strict R-10) et :func:`pbm_game.combat.fin.resoudre_kos` (K.O., récompenses, victoire —
R-13/R-14).

**Les attaques à effet (ce lot, ``j-cartes-attaques-effets``).** Une attaque peut porter un
**script DSL** (``params["attaque"]["script"]`` ou ``params["script"]``) : pile ou face, dégâts au
banc, auto-dégâts, défausse d'énergies en coût, soins, états spéciaux, blocage du tour suivant. Le
script se résout **entre ``avant_degats`` et ``apres_degats``** : il s'exécute d'abord (il peut
poser un état, blesser le banc, ou **annuler** les dégâts — « si pile, cette attaque ne fait
rien »), puis les dégâts **principaux** sont posés sur l'Actif adverse (avec faiblesse/résistance),
sauf s'ils ont été annulés. Une attaque dont le texte porte un effet **sans script** reste refusée
(R-15.12/D9) : un effet non implémenté n'est jamais approximé.

**Les dégâts variables** (``params["attaque"]["degats"]`` peut être un **mapping** et non un entier)
se calculent **au moment de la résolution** (:mod:`pbm_game.combat.valeur`), jamais à la déclaration
— un joueur qui défausse une énergie entre les deux obtiendrait sinon un résultat faux.

**Les verrous** posés par un ``empecher`` du script (« ne peut pas attaquer au prochain tour »)
rejoignent ``etat.verrous`` : ils pèsent sur les tours suivants et expirent au Checkup (R-12.5).

Cette fonction **n'entre pas** en Checkup : c'est la transition ``declarer_attaque`` qui termine le
tour (R-5.8), sauf si l'attaque a déjà terminé la partie.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from ..journal.modele import EVT_ATTAQUE_DECLAREE, Action, Evenement
from ..state.modele import EtatPartie, Joueur, carte_active
from .cout import EnergieAttachee, payer_cout
from .fin import resoudre_kos
from .modele import CoutAttaque, Faiblesse, Modificateur, Resistance
from .resolution import evenement_degats, poser_degats, resoudre_degats
from .valeur import est_valeur_dynamique, valeur_depuis


def _index_joueur(etat: EtatPartie, jid: str) -> int:
    for i, joueur in enumerate(etat.joueurs):
        if joueur.id == jid:
            return i
    raise ValueError(f"Joueur « {jid} » absent de la partie.")


def _remplacer_joueur(etat: EtatPartie, index: int, joueur: Joueur) -> EtatPartie:
    joueurs = list(etat.joueurs)
    joueurs[index] = joueur
    return replace(etat, joueurs=(joueurs[0], joueurs[1]))


def _autre_joueur(etat: EtatPartie, jid: str) -> str:
    a, b = etat.joueurs[0].id, etat.joueurs[1].id
    if jid == a:
        return b
    if jid == b:
        return a
    raise ValueError(f"Joueur « {jid} » absent de la partie.")


def _cout_depuis(brut: object) -> CoutAttaque:
    if not isinstance(brut, Mapping):
        return CoutAttaque()
    return CoutAttaque(types=dict(brut.get("types", {})), incolore=brut.get("incolore", 0))


def _energies_depuis(brut: object) -> list[EnergieAttachee]:
    """Les énergies attachées à l'Actif, telles que le service les a extraites (R-9.2)."""
    if brut is None:
        return []
    if not isinstance(brut, (list, tuple)):
        raise ValueError("« energies » doit être une liste de fournitures d'énergie (R-9.2).")
    energies: list[EnergieAttachee] = []
    for e in brut:
        if not isinstance(e, Mapping):
            raise ValueError("Chaque énergie attachée se décrit par un mapping (R-9.2).")
        energies.append(
            EnergieAttachee(
                instance_id=e.get("instance_id", ""),
                fournit=dict(e.get("fournit", {})),
                libelle=e.get("libelle", ""),
            )
        )
    return energies


def _faiblesse_depuis(brut: object) -> Faiblesse | None:
    if not isinstance(brut, Mapping):
        return None
    return Faiblesse(type=brut.get("type", ""), facteur=brut.get("facteur", 2))


def _modificateurs_depuis(brut: object) -> list[Modificateur]:
    """Reconstruit les :class:`Modificateur` continus portés dans les ``params`` (Outils/Stades).

    La famille d'attaque (``actions.familles_jeu``) a calculé ces modificateurs à la génération du
    coup, depuis le ``registre_continus`` du catalogue, et les a sérialisés en dicts que le journal
    transporte. On les relit ici pour les passer à :func:`resoudre_degats` dans l'ordre strict
    R-10.1 (étape 2 attaquant, étape 5 défenseur). Absents (J1, ou aucun effet continu) : liste vide
    — l'attaque garde ses dégâts imprimés (D9). Une entrée mal formée est **ignorée**, jamais
    devinée : seuls des modificateurs complets et valides pèsent sur le calcul.
    """
    if not isinstance(brut, (list, tuple)):
        return []
    mods: list[Modificateur] = []
    for item in brut:
        if not isinstance(item, Mapping):
            continue
        try:
            mods.append(
                Modificateur(
                    libelle=item["libelle"],
                    regle=item["regle"],
                    operation=item["operation"],
                    valeur=item["valeur"],
                )
            )
        except (KeyError, ValueError, TypeError):
            continue
    return mods


def _resistance_depuis(brut: object) -> Resistance | None:
    if not isinstance(brut, Mapping):
        return None
    return Resistance(type=brut.get("type", ""), reduction=brut.get("reduction", 30))


def _base_degats(attaque: Mapping, etat: EtatPartie, *, attaquant: str, adversaire: str) -> int:
    """Les dégâts **de base** de l'attaque : entier sec, ou valeur **variable** calculée sur l'état.

    R-10.1 (le piège de la fiche) : une base variable (« 20 par énergie attachée ») est résolue
    **ici**, au moment de la résolution, sur l'état courant — jamais figée à la déclaration.
    """
    brut = attaque.get("degats", 0)
    if est_valeur_dynamique(brut):
        return valeur_depuis(brut).evaluer(etat, attaquant=attaquant, adversaire=adversaire)
    if not isinstance(brut, int) or isinstance(brut, bool) or brut < 0:
        raise ValueError(f"« degats » invalides {brut!r} (entier ≥ 0 ou dégâts variables).")
    return brut


def _executer_script(
    etat: EtatPartie, script_brut: object, attaque: Mapping, action: Action, jid: str, rng: object
) -> tuple[EtatPartie, list[Evenement], bool]:
    """Exécute le **script d'effet** de l'attaque entre ``avant_degats`` et ``apres_degats``.

    Renvoie ``(etat, evenements, degats_annules)``. Les verrous posés (``empecher``) rejoignent
    ``etat.verrous`` — sans re-journaliser (la primitive a déjà émis ``EVT_VERROU_POSE``). Imports
    **locaux** : ``combat`` ne dépend pas du paquet ``effets`` au chargement (il le tire à l'usage),
    comme ``journal.transitions`` tire ``combat.attaque``.
    """
    from ..effets.dsl.chargement import charger_programme
    from ..effets.dsl.contexte import ContexteEffet
    from ..effets.dsl.interprete import executer_programme
    from ..effets.pile import SourceEffet
    from ..effets.verrous import VERROUS_VIDES, JeuDeVerrous

    adversaire = _autre_joueur(etat, jid)
    actif = etat.joueurs[_index_joueur(etat, jid)].actif
    adv_actif = etat.joueurs[_index_joueur(etat, adversaire)].actif
    source = SourceEffet(
        libelle=str(attaque.get("nom") or "Attaque"),
        ref=action.params.get("ref_attaquant"),
        instance_id=carte_active(actif).instance_id if actif is not None else None,
    )
    metadonnees = action.params.get("metadonnees")
    ctx = ContexteEffet(
        source=source,
        joueur=jid,
        adversaire=adversaire,
        acteur_actif=actif.cartes[0].instance_id if actif is not None else None,
        defenseur=adv_actif.cartes[0].instance_id if adv_actif is not None else None,
        metadonnees=metadonnees if isinstance(metadonnees, Mapping) else {},
    )
    resultat = executer_programme(etat, charger_programme(script_brut), ctx, rng)
    etat = resultat.etat
    if resultat.verrous:
        base = etat.verrous if etat.verrous is not None else VERROUS_VIDES
        etat = replace(etat, verrous=JeuDeVerrous(base.verrous + tuple(resultat.verrous)))
    return etat, list(resultat.evenements), resultat.degats_annules


def resoudre_attaque_declaree(
    etat: EtatPartie, action: Action, jid: str, attaque_a_lieu: bool, rng: object
) -> tuple[EtatPartie, list[Evenement]]:
    """Résout le coût, l'effet scripté, les dégâts et les K.O. d'une attaque déclarée (R-9/10/13).

    ``attaque_a_lieu`` est le verdict des états **avant** l'attaque (``pbm_game.etats.attaque``) :
    faux signifie que la Confusion est tombée sur pile — l'attaque ne porte alors ni effet ni dégâts
    (l'auto-blessure a déjà été posée par l'appelant), mais le coût **reste payé** (R-11.5). Ne gère
    pas la fin du tour (c'est la transition ``declarer_attaque``).
    """
    evenements: list[Evenement] = []
    attaque = action.params.get("attaque")
    if not isinstance(attaque, Mapping):
        raise ValueError("« attaque » (fiche de l'attaque choisie) est requise (R-9.1, D9).")
    effet = (attaque.get("effet") or "").strip()
    script_brut = action.params.get("script")
    if script_brut is None:
        script_brut = attaque.get("script")
    # D9 : un texte d'effet n'est jouable que s'il est **porté** par une forme structurée — un
    # script DSL, ou des dégâts variables (``degats`` est alors une formule). Un texte d'effet sans
    # l'un ni l'autre est un effet non implémenté : refusé, jamais approximé (R-15.12).
    degats_variables = est_valeur_dynamique(attaque.get("degats"))
    if effet and script_brut is None and not degats_variables:
        raise ValueError(
            f"L'attaque « {attaque.get('nom')} » porte un effet non scripté — un effet non "
            "implémenté n'est jamais approximé (R-15.12/D9)."
        )

    # Pouvoir à usage unique par partie (attaque GX R-15.3, VSTAR Power R-15.6) : un second usage
    # est refusé, l'usage étant suivi dans l'état du JOUEUR (jamais celui de la carte). Vérifié
    # AVANT le coût — un pouvoir déjà dépensé n'est pas une attaque à payer.
    pouvoir_unique = attaque.get("pouvoir_unique")
    if pouvoir_unique is not None:
        from .pouvoirs_uniques import REGLE_PAR_POUVOIR, deja_utilise, valider_pouvoir

        valider_pouvoir(pouvoir_unique)
        if deja_utilise(etat.joueurs[_index_joueur(etat, jid)], pouvoir_unique):
            regle = REGLE_PAR_POUVOIR[pouvoir_unique]
            raise ValueError(
                f"Pouvoir « {pouvoir_unique} » déjà utilisé cette partie : un seul par partie et "
                f"par joueur ({regle})."
            )

    cout = _cout_depuis(attaque.get("cout"))
    energies = _energies_depuis(action.params.get("energies"))
    paiement = payer_cout(cout, energies)
    if not paiement.paye:
        raise ValueError(f"{paiement.verdict.message}")
    if cout.types or cout.incolore:
        evenements.append(paiement.evenement(cout))

    # Le coût est payé : le pouvoir unique est désormais **dépensé** pour cette partie (même si la
    # Confusion annule ensuite l'attaque — il a été déclaré). Marqué dans l'état du joueur, donc
    # l'interdiction survit à un F5 et au rejeu.
    if pouvoir_unique is not None:
        from .pouvoirs_uniques import marquer_utilise

        idx_att = _index_joueur(etat, jid)
        etat = _remplacer_joueur(
            etat, idx_att, marquer_utilise(etat.joueurs[idx_att], pouvoir_unique)
        )

    if not attaque_a_lieu:
        # Confusion sur pile : ni effet ni dégât (R-11.5). Rien d'autre à résoudre ici.
        return etat, evenements

    adversaire = _autre_joueur(etat, jid)

    # Dégâts de base, calculés MAINTENANT (R-10.1) — une base variable lit l'état courant, avant
    # que le script ne défausse d'énergie ou ne change quoi que ce soit.
    base = _base_degats(attaque, etat, attaquant=jid, adversaire=adversaire)

    # Effet scripté entre avant_degats et apres_degats : il s'exécute d'abord (états, banc, verrous,
    # annulation éventuelle), puis les dégâts principaux sont posés.
    degats_annules = False
    if script_brut is not None:
        etat, evts_script, degats_annules = _executer_script(
            etat, script_brut, attaque, action, jid, rng
        )
        evenements.extend(evts_script)

    idx_adv = _index_joueur(etat, adversaire)
    adv = etat.joueurs[idx_adv]
    cible = adv.actif
    if degats_annules or base == 0 or cible is None:
        # Pas de dégâts principaux à poser : attaque annulée (R-16), attaque sans dégât sec, ou
        # aucun Actif adverse à toucher (R-9.1). L'attaque reste déclarée (le tour se termine).
        evenements.append(Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": jid, "degats": 0}))
        etat, evts_ko = resoudre_kos(etat, action.params.get("fiches", {}), (jid, adversaire))
        evenements.extend(evts_ko)
        return etat, evenements

    resultat = resoudre_degats(
        base=base,
        type_attaque=action.params.get("type_attaque"),
        faiblesse=_faiblesse_depuis(action.params.get("faiblesse")),
        resistance=_resistance_depuis(action.params.get("resistance")),
        modificateurs_attaquant=_modificateurs_depuis(
            action.params.get("modificateurs_attaquant")
        ),
        modificateurs_defenseur=_modificateurs_depuis(
            action.params.get("modificateurs_defenseur")
        ),
    )
    adv = replace(adv, actif=poser_degats(cible, resultat.degats))
    etat = _remplacer_joueur(etat, idx_adv, adv)
    evenements.append(evenement_degats(resultat, carte_active(cible).instance_id))
    evenements.append(Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": jid, "degats": resultat.degats}))

    # K.O., récompenses et conditions de victoire (R-13/R-14) — ordre (attaquant, défenseur). Le
    # résolveur voit AUSSI les K.O. d'auto-dégâts et de dégâts au banc posés par le script.
    etat, evts_ko = resoudre_kos(etat, action.params.get("fiches", {}), (jid, adversaire))
    evenements.extend(evts_ko)
    return etat, evenements


__all__ = ["resoudre_attaque_declaree"]
