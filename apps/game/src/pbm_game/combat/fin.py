"""Mises K.O., récompenses et **conditions de victoire** — la fin d'une partie (R-13, R-14).

Module **pur** (aucune E/S, ni HTTP, ni base, ni React), comme tout ``pbm_game``. Il porte le
moment où une erreur de moteur coûte le plus cher : c'est là que le résultat se décide.

Deux responsabilités, que les lots amont n'avaient volontairement pas résolues :

1. **Le nombre de récompenses se lit sur le marqueur de règle de la carte** (R-13.3/R-13.4),
   jamais depuis une liste de **noms** en dur, et un **marqueur inconnu échoue bruyamment** —
   jamais « par défaut 1 » (R-13.4/R-15.22, interdiction du repli silencieux). C'est
   :func:`recompenses_pour_marqueur` et la table :data:`MARQUEUR_RECOMPENSES` qui l'incarnent :
   une table close keyée par **marqueur** (sous-type / Rule Box du catalogue), pas par nom —
   le suffixe du nom ne suffit jamais (R-13.7).

2. **La résolution des K.O. et les trois conditions de victoire** (R-14.1), le K.O. simultané
   (R-13.5) et l'**égalité** (R-14.4/R-16.10) avec son départage (R-14.5). :func:`resoudre_kos`
   est **partagée** à dessein : le Pokémon Checkup l'appelle pour les K.O. hors attaque (R-12.4),
   et la résolution d'attaque l'appellera pour les K.O. qu'une attaque provoque — y compris
   **plusieurs à la fois**. Le code de victoire ne vit donc pas que dans l'attaque.

**Les trois façons de gagner (R-14.1).** (1) prendre sa **dernière** carte récompense après un
K.O. ; (2) l'adversaire **n'a plus de Pokémon à promouvoir** après un K.O. (banc vide, R-8.9) ;
(3) l'adversaire **ne peut pas piocher** en début de tour (R-14.2) — cette troisième condition se
vérifie ailleurs, à l'ouverture du tour (``journal.transitions._debut_tour``), car elle ne découle
pas d'un K.O. Ce module couvre les deux premières et leur simultanéité.

**Le moteur ne devine ni PV ni récompenses (D9).** Les PV (R-13.1) et le marqueur de règle
(R-13.3) viennent du catalogue, que le moteur ne connaît pas : le service les fournit par
``fiches`` (``instance_id de la carte au sommet → {"pv": int, "recompenses": int}`` **ou**
``{"pv": int, "marqueur": str}``). :func:`valider_fiches` refuse toute entrée malformée.
"""

from __future__ import annotations

from dataclasses import replace

from ..journal.modele import (
    EVT_KO,
    EVT_PARTIE_TERMINEE,
    EVT_PROMOTION_REQUISE,
    RAISON_DERNIERE_RECOMPENSE,
    RAISON_PLUS_DE_POKEMON,
    Evenement,
)
from ..state.modele import RAISON_EGALITE, EtatPartie, Joueur, PokemonEnJeu, carte_active
from ..tour.drapeaux import identite_pokemon
from .ko import cartes_a_defausser, est_ko, prendre_recompenses

# --- Marqueur de règle → nombre de récompenses (R-13.3/R-13.4/R-13.7) ---------------------

#: Table **close** du nombre de récompenses par **marqueur de règle** (sous-type / Rule Box du
#: catalogue). Keyée par marqueur, **jamais** par nom de carte : le suffixe du nom ne classe pas
#: une carte (R-13.7 — une Méga-Évolution Pokémon ex finit par « ex » mais donne 3). Chaque
#: entrée cite la règle de R-15 qui la fixe. Un marqueur **absent** de cette table fait échouer
#: :func:`recompenses_pour_marqueur` — jamais un repli « par défaut 1 » (R-13.4/R-15.22).
MARQUEUR_RECOMPENSES: dict[str, int] = {
    # 1 récompense (R-13.3).
    "ordinaire": 1,  # Pokémon ordinaire (R-13.3)
    "radiant": 1,  # Radiant (R-15.9)
    "break": 1,  # Pokémon BREAK (R-15.17)
    "prisme_etoile": 1,  # Prisme Étoile ◇ (R-15.18)
    "lv_x": 1,  # Pokémon LV.X (R-15.20)
    "etoile": 1,  # Pokémon ★ (R-15.21)
    # 2 récompenses (R-13.3).
    "ex": 2,  # Pokémon ex, minuscules — ère EX & actuel (R-15.1/R-15.16)
    "tera_ex": 2,  # Tera Pokémon ex (R-15.2)
    "pokemon_ex": 2,  # Pokémon-EX, majuscules & tiret (R-15.14)
    "m_pokemon_ex": 2,  # M Pokémon-EX (R-15.15)
    "gx": 2,  # Pokémon-GX (R-15.3)
    "v": 2,  # Pokémon V (R-15.4)
    "vstar": 2,  # Pokémon VSTAR (R-15.6)
    "legende": 2,  # LÉGENDE (R-15.19)
    # 3 récompenses (R-13.3).
    "mega_ex": 3,  # Méga-Évolution Pokémon ex (R-15.13)
    "vmax": 3,  # Pokémon VMAX (R-15.5)
    "tag_team": 3,  # TAG TEAM (R-15.7)
    "v_union": 3,  # V-UNION (R-15.8)
}


def recompenses_pour_marqueur(marqueur: object) -> int:
    """Le nombre de récompenses d'une carte K.O. depuis son **marqueur de règle** (R-13.3).

    ``marqueur`` est le sous-type / Rule Box lu dans le catalogue (le moteur ne lit **jamais** le
    nom : R-13.7). Un marqueur **inconnu** lève ``ValueError`` — c'est la panne bruyante exigée
    (R-13.4/R-15.22), jamais « par défaut 1 ».
    """
    if not isinstance(marqueur, str) or not marqueur:
        raise ValueError(
            f"Marqueur de règle invalide : {marqueur!r} — une chaîne non vide lue dans le "
            "catalogue est attendue (R-13.3)."
        )
    nb = MARQUEUR_RECOMPENSES.get(marqueur)
    if nb is None:
        raise ValueError(
            f"Marqueur de règle inconnu : « {marqueur} » — il fait échouer bruyamment "
            f"(R-13.4/R-15.22), jamais « par défaut 1 ». Marqueurs connus : "
            f"{sorted(MARQUEUR_RECOMPENSES)}."
        )
    return nb


# --- Fiches catalogue (PV + récompenses) — validation partagée ----------------------------


def _recompenses_de_fiche(fiche: dict) -> int:
    """Le nombre de récompenses d'une fiche : via ``marqueur`` (préféré, R-13.3) ou via un
    ``recompenses`` déjà calculé par le service. Suppose la fiche déjà validée par
    :func:`valider_fiches`.
    """
    if "marqueur" in fiche:
        return recompenses_pour_marqueur(fiche["marqueur"])
    return fiche["recompenses"]


def valider_fiches(fiches: object) -> dict:
    """Valide ``fiches`` : un mapping ``instance_id → {pv ≥ 1, (recompenses ≥ 1 | marqueur)}``.

    Chaque fiche porte des **PV** (R-13.1) et, pour les récompenses (R-13.3), **soit** un
    ``marqueur`` de règle (préféré : la table close en déduit le nombre, R-13.4/R-13.7) **soit**
    un ``recompenses`` entier ≥ 1 déjà calculé par le service. Toute entrée malformée — PV absurde,
    ni marqueur ni récompenses, marqueur inconnu — est une **panne** (D9 : jamais « par défaut 1 »).
    Un mapping **vide** est permis (une partie sans aucun Pokémon endommagé n'a besoin d'aucune
    fiche). Renvoie le mapping validé.
    """
    if not isinstance(fiches, dict):
        raise ValueError(
            "« fiches » doit être un mapping instance_id → {pv, recompenses|marqueur}, fourni "
            "par le service depuis le catalogue (R-13.1/R-13.3, D9)."
        )
    for cle, fiche in fiches.items():
        if not isinstance(cle, str) or not cle:
            raise ValueError(f"Fiche : clé invalide {cle!r} (un instance_id est attendu).")
        if not isinstance(fiche, dict):
            raise ValueError(
                f"Fiche « {cle} » : doit être un mapping {{pv, recompenses|marqueur}}."
            )
        pv = fiche.get("pv")
        if not isinstance(pv, int) or isinstance(pv, bool) or pv <= 0:
            raise ValueError(f"Fiche « {cle} » : « pv » invalide {pv!r} (entier ≥ 1, R-13.1).")
        if "marqueur" in fiche:
            # Lève sur un marqueur inconnu (R-13.4/R-15.22) : la validation est **eager**, une
            # carte au marqueur inconnu ne passe pas, même si elle ne sera jamais K.O.
            recompenses_pour_marqueur(fiche["marqueur"])
        elif "recompenses" in fiche:
            rec = fiche["recompenses"]
            if not isinstance(rec, int) or isinstance(rec, bool) or rec < 1:
                raise ValueError(
                    f"Fiche « {cle} » : « recompenses » invalide {rec!r} (entier ≥ 1, R-13.3)."
                )
        else:
            raise ValueError(
                f"Fiche « {cle} » : ni « marqueur » (R-13.3) ni « recompenses » — le nombre de "
                "récompenses ne se devine pas (R-13.4)."
            )
    return fiches


def _fiche(fiches: dict, pokemon: PokemonEnJeu) -> dict:
    """La fiche (PV + récompenses) d'un Pokémon, par l'``instance_id`` de sa carte au sommet.

    **Absente = panne bruyante** (D9) : le moteur ne devine ni PV ni marqueur de règle.
    """
    cle = carte_active(pokemon).instance_id
    fiche = fiches.get(cle)
    if not isinstance(fiche, dict):
        raise ValueError(
            f"Fiche de catalogue manquante pour le Pokémon « {cle} » : PV (R-13.1) et nombre de "
            "récompenses (R-13.3) sont requis à la mise K.O. et fournis par le service (D9)."
        )
    return fiche


# --- Index/remplacement immuables (même forme que les autres modules du moteur) -----------


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


# --- Détection et application d'un K.O. (R-13.1/R-13.2/R-13.3) -----------------------------


def _trouver_ko(joueur: Joueur, fiches: dict) -> tuple[str, int] | None:
    """Localise un Pokémon K.O. de ``joueur`` (``("actif", -1)`` ou ``("banc", i)``), ou ``None``.

    Ne considère que les Pokémon **endommagés** (compteurs > 0) : un Pokémon intact n'est jamais
    K.O. (R-13.1) et n'exige donc pas de fiche. Un Pokémon endommagé **sans** fiche fait échouer
    :func:`_fiche` (bruyamment). L'Actif est examiné avant le banc (ordre déterministe).
    """
    if joueur.actif is not None and joueur.actif.compteurs_degats > 0:
        if est_ko(joueur.actif.compteurs_degats, _fiche(fiches, joueur.actif)["pv"]):
            return ("actif", -1)
    for i, p in enumerate(joueur.banc):
        if p.compteurs_degats > 0 and est_ko(p.compteurs_degats, _fiche(fiches, p)["pv"]):
            return ("banc", i)
    return None


def _appliquer_ko(
    etat: EtatPartie, jid: str, cible: tuple[str, int], fiches: dict
) -> tuple[EtatPartie, Evenement, str, int]:
    """Met K.O. le Pokémon ``cible`` de ``jid`` : défausse (R-13.2), l'adversaire prend ses
    récompenses (R-13.3). L'Actif K.O. laisse la place **vide** (``None``) — la promotion suit.

    Renvoie ``(etat, evenement, adversaire, prises)`` : ``adversaire`` est le joueur qui a pris
    les récompenses et ``prises`` leur nombre réel — de quoi suivre qui a vidé sa réserve (R-14.1).
    """
    index = _index_joueur(etat, jid)
    joueur = etat.joueurs[index]
    zone, i = cible
    pokemon = joueur.actif if zone == "actif" else joueur.banc[i]
    nb = _recompenses_de_fiche(_fiche(fiches, pokemon))

    defausse = joueur.defausse + cartes_a_defausser(pokemon)
    if zone == "actif":
        joueur = replace(joueur, actif=None, defausse=defausse)
    else:
        banc = joueur.banc[:i] + joueur.banc[i + 1 :]
        joueur = replace(joueur, banc=banc, defausse=defausse)
    etat = _remplacer_joueur(etat, index, joueur)

    adversaire = _autre_joueur(etat, jid)
    idx_adv = _index_joueur(etat, adversaire)
    joueur_adv, prises = prendre_recompenses(etat.joueurs[idx_adv], nb)
    etat = _remplacer_joueur(etat, idx_adv, joueur_adv)

    evt = Evenement(
        EVT_KO,
        {"joueur": jid, "pokemon": identite_pokemon(pokemon),
         "compteurs": pokemon.compteurs_degats, "recompenses_prises": prises, "par": adversaire},
    )
    return etat, evt, adversaire, prises


# --- Conditions de victoire (R-14.1), simultanéité (R-13.5) et égalité (R-14.4/R-14.5) -----

#: Voie de victoire : le joueur a pris sa **dernière** carte récompense (R-14.1 cas 1).
VOIE_DERNIERE_RECOMPENSE = "derniere_recompense"
#: Voie de victoire : l'adversaire n'a **plus de Pokémon** en jeu à promouvoir (R-14.1 cas 2).
VOIE_ADVERSAIRE_SANS_POKEMON = "adversaire_sans_pokemon"


def _sans_pokemon(joueur: Joueur) -> bool:
    """Le joueur n'a **plus aucun Pokémon en jeu** : ni Actif, ni banc (R-8.9/R-14.1 cas 2)."""
    return joueur.actif is None and not joueur.banc


def terminer(
    etat: EtatPartie, vainqueur: str | None, raison: str, **donnees: object
) -> tuple[EtatPartie, Evenement]:
    """Fige la partie (R-14.6) : ``terminee`` vrai, ``vainqueur`` + ``raison``, et l'événement
    :data:`EVT_PARTIE_TERMINEE` qui clôt le journal. ``donnees`` enrichit l'événement (perdant,
    voies…). Lève si la partie est **déjà** terminée (R-14.6 : une fin ne se rejoue pas).
    """
    if etat.terminee:
        raise ValueError("Partie déjà terminée : elle ne se re-termine pas (R-14.6).")
    etat2 = replace(etat, terminee=True, vainqueur=vainqueur, raison_fin=raison)
    evt = Evenement(EVT_PARTIE_TERMINEE, {"vainqueur": vainqueur, "raison": raison, **donnees})
    return etat2, evt


def _raison_de_voies(voies: set[str]) -> str:
    """La raison de fin d'un gagnant depuis ses voies : la **dernière récompense** (R-14.1 cas 1)
    prime comme motif affiché quand elle est présente, sinon « plus de Pokémon » (cas 2).
    """
    if VOIE_DERNIERE_RECOMPENSE in voies:
        return RAISON_DERNIERE_RECOMPENSE
    return RAISON_PLUS_DE_POKEMON


def _conclure(
    etat: EtatPartie,
    evenements: list[Evenement],
    ordre: tuple[str, str],
    avait_actif: dict[str, bool],
    a_pris_sa_derniere: set[str],
) -> tuple[EtatPartie, list[Evenement]]:
    """Évalue les conditions de victoire après tous les K.O. de la passe (R-14.1/R-14.4/R-14.5).

    Pour chaque joueur, on compte ses **voies** de victoire :

    * **dernière récompense** (R-14.1 cas 1) — il a pris sa dernière récompense **pendant cette
      passe** (réserve désormais vide). On exige « pendant cette passe » pour ne pas transformer
      une réserve déjà vide (artefact d'état) en victoire : on gagne en **prenant** la dernière,
      pas en n'en ayant aucune ;
    * **adversaire sans Pokémon** (R-14.1 cas 2) — l'adversaire n'a plus ni Actif ni banc (R-8.9).

    Puis : aucune voie → promotions demandées (R-8.7) ; une seule voie → ce joueur gagne ; les
    **deux** joueurs gagnent → départage par le **nombre** de voies (R-14.5 : « deux voies contre
    une » tranche), à égalité de nombre c'est **nul** (R-14.4/R-16.10).
    """
    voies: dict[str, set[str]] = {jid: set() for jid in ordre}
    for jid in ordre:
        joueur = etat.joueurs[_index_joueur(etat, jid)]
        if jid in a_pris_sa_derniere and not joueur.recompenses:
            voies[jid].add(VOIE_DERNIERE_RECOMPENSE)
        # R-14.1 cas 2 : l'adversaire perd s'il n'a plus de Pokémon « **après un K.O.** » — donc
        # seulement si son Actif est tombé PENDANT cette passe (``avait_actif``). Un joueur entré
        # déjà sans Actif (état artificiel, ou vide déjà traité) ne déclenche pas de victoire ici.
        adv_id = _autre_joueur(etat, jid)
        adv = etat.joueurs[_index_joueur(etat, adv_id)]
        if avait_actif[adv_id] and _sans_pokemon(adv):
            voies[jid].add(VOIE_ADVERSAIRE_SANS_POKEMON)

    gagnants = [jid for jid in ordre if voies[jid]]

    if not gagnants:
        # Personne ne gagne : chaque joueur dont l'Actif est tombé CETTE passe et qui a du banc
        # doit promouvoir (R-8.7). On ne redemande pas à un joueur entré déjà sans Actif.
        for jid in ordre:
            joueur = etat.joueurs[_index_joueur(etat, jid)]
            if avait_actif[jid] and joueur.actif is None and joueur.banc:
                evenements.append(Evenement(EVT_PROMOTION_REQUISE, {"joueur": jid}))
        return etat, evenements

    if len(gagnants) == 1:
        gagnant = gagnants[0]
        perdant = _autre_joueur(etat, gagnant)
        etat, evt = terminer(
            etat, gagnant, _raison_de_voies(voies[gagnant]),
            perdant=perdant, voies=sorted(voies[gagnant]),
        )
        evenements.append(evt)
        return etat, evenements

    # Les deux joueurs gagnent au même instant (K.O. simultané, R-13.5) : départage R-14.5.
    a, b = ordre
    if len(voies[a]) > len(voies[b]):
        gagnant = a
    elif len(voies[b]) > len(voies[a]):
        gagnant = b
    else:
        gagnant = None  # nombre de voies égal → partie NULLE (R-14.4/R-16.10)

    if gagnant is None:
        etat, evt = terminer(
            etat, None, RAISON_EGALITE,
            perdants=[a, b], voies={a: sorted(voies[a]), b: sorted(voies[b])},
        )
    else:
        perdant = _autre_joueur(etat, gagnant)
        etat, evt = terminer(
            etat, gagnant, _raison_de_voies(voies[gagnant]),
            perdant=perdant, voies=sorted(voies[gagnant]),
        )
    evenements.append(evt)
    return etat, evenements


def resoudre_kos(
    etat: EtatPartie, fiches: object, ordre: tuple[str, str]
) -> tuple[EtatPartie, list[Evenement]]:
    """Résout **tous** les K.O. présents sur le plateau, prend les récompenses, puis tranche la
    fin de partie (R-13, R-14). **Partagée** par le Checkup (R-12.4) et l'attaque (R-13.5).

    ``ordre`` est le couple ``(joueur_premier, joueur_second)`` : le premier est traité avant le
    second, pour que la suite des événements soit **déterministe** et rejouable. Un K.O. peut en
    révéler d'autres (défausse qui vide un banc n'arrive pas ici, mais plusieurs Pokémon d'un même
    joueur peuvent être K.O. en même temps — attaque de zone) : on rescanne jusqu'à épuisement.

    Renvoie ``(etat, evenements)`` : les :data:`EVT_KO`, puis soit des :data:`EVT_PROMOTION_REQUISE`
    (la partie continue), soit un :data:`EVT_PARTIE_TERMINEE` (une victoire ou l'égalité). Lève si
    une fiche est malformée (:func:`valider_fiches`).
    """
    fiches = valider_fiches(fiches)
    evenements: list[Evenement] = []

    # Qui avait un Actif au DÉBUT de la passe : sert à ne demander une promotion (ou à ne conclure
    # à une défaite) que pour un Actif tombé PENDANT cette passe, pas un vide déjà présent.
    avait_actif = {jid: etat.joueurs[_index_joueur(etat, jid)].actif is not None for jid in ordre}
    # Qui a pris AU MOINS une récompense pendant cette passe : on gagne en PRENANT la dernière
    # (R-14.1 cas 1), pas en ayant une réserve vide par ailleurs.
    a_pris_sa_derniere: set[str] = set()

    for jid in ordre:
        # Retirer un K.O. du banc décale les index : on rescanne jusqu'à épuisement.
        while True:
            cible = _trouver_ko(etat.joueurs[_index_joueur(etat, jid)], fiches)
            if cible is None:
                break
            etat, evt, adversaire, prises = _appliquer_ko(etat, jid, cible, fiches)
            evenements.append(evt)
            if prises > 0:
                a_pris_sa_derniere.add(adversaire)

    # On ne retient comme « dernière récompense prise » que les joueurs dont la réserve est
    # désormais vide ET qui ont pris au moins une récompense cette passe.
    a_pris_sa_derniere = {
        jid
        for jid in a_pris_sa_derniere
        if not etat.joueurs[_index_joueur(etat, jid)].recompenses
    }

    return _conclure(etat, evenements, ordre, avait_actif, a_pris_sa_derniere)


__all__ = [
    "MARQUEUR_RECOMPENSES",
    "recompenses_pour_marqueur",
    "valider_fiches",
    "terminer",
    "resoudre_kos",
    "VOIE_DERNIERE_RECOMPENSE",
    "VOIE_ADVERSAIRE_SANS_POKEMON",
]
