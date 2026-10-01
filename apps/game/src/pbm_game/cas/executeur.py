"""Exécuteur de **cas de règles** — rejoue un cas écrit en données contre le vrai moteur.

Module **pur** (aucune E/S, ni HTTP, ni base, ni React), comme tout ``pbm_game``. Il ne lit
**aucun** fichier : il reçoit un cas **déjà désérialisé** (un ``dict``, tel que le charge
``tests/test_cas_executables.py`` depuis ``docs/jeu/cas-executables/*.yaml``) et le **rejoue**
contre les fonctions réelles du moteur, puis **vérifie** le résultat attendu.

Principe du lot ``j-tests-regles`` : un moteur de règles **se prouve**, il ne se relit pas. Un
cas est une donnée — un état de départ, une action (ou un appel de fonction), un résultat
attendu, et la règle ``R-x.y`` qu'il vérifie — qu'un humain qui connaît les règles lit et écrit
**sans toucher au code du moteur**. L'exécuteur est le seul code ; les cas sont des données.

Le piège nommé dans la fiche du lot : des tests écrits depuis le code plutôt que depuis les
règles. On s'en garde en citant, pour chaque cas, l'identifiant de règle de ``docs/jeu/REGLES.md``
qu'il vérifie — et en écrivant l'attendu depuis la règle, pas depuis ce que le code renvoie.

Chaque cas porte une clé ``op`` (l'opération testée). Les opérations, documentées dans
``docs/jeu/CAS-EXECUTABLES.md`` :

* ``appliquer``   — construit un état, applique une (ou plusieurs) action(s) journalisée(s)
  via :func:`pbm_game.journal.transitions.appliquer`, puis vérifie l'état et les événements —
  ou une erreur attendue (``erreur``) citant la règle qui refuse le coup ;
* ``degats``      — :func:`pbm_game.combat.resolution.resoudre_degats` (ordre strict R-10) ;
* ``compteurs``   — pose de compteurs/dégâts directs (R-10.4/R-10.6) ;
* ``etat``        — pose/guérison d'états sur un Pokémon, matrice de cumul et orientation (R-11) ;
* ``recompenses`` — marqueur de règle → nombre de récompenses (R-13.3), inconnu = panne (R-13.4) ;
* ``cout``        — l'énergie paie-t-elle l'attaque (R-9.2) ;
* ``legalite``    — :func:`pbm_game.actions.valider` / :func:`actions_legales` (R-5.1/R-14) ;
* ``invariants``  — :func:`pbm_game.state.verifier` (R-3) ;
* ``rng``         — reproductibilité et vérifiabilité d'un tirage (R-4.7).
"""

from __future__ import annotations

from collections.abc import Sequence

# Importer le paquet garantit que ``banc`` et ``checkup`` ont enregistré leurs transitions dans
# le REGISTRE (retraite, promotion, échange forcé, checkup) — sinon ``appliquer`` les ignorerait.
from .. import banc as _banc  # noqa: F401
from .. import checkup as _checkup  # noqa: F401
from ..actions.generateur import actions_legales, valider
from ..combat.cout import cout_satisfait
from ..combat.fin import recompenses_pour_marqueur
from ..combat.modele import (
    CoutAttaque,
    Faiblesse,
    Resistance,
    modificateur_ajout,
    modificateur_fixe,
    modificateur_multiplie,
)
from ..combat.resolution import poser_compteurs, poser_degats, resoudre_degats
from ..etats.matrice import appliquer_etat, etat_bloquant_attaque, soigner_etats_speciaux
from ..journal.modele import ACTION_CHECKUP, Action
from ..journal.transitions import appliquer
from ..rng import Rng, verifier_journal
from ..state.invariants import verifier
from ..state.modele import Carte, PokemonEnJeu, orientation
from .constructeur import GRAINE_DEFAUT, construire, trouver_graine


class EchecCas(AssertionError):
    """Un cas dont le résultat observé ne correspond pas à l'attendu — avec son identifiant."""


def _echec(cas_id: str, message: str) -> EchecCas:
    return EchecCas(f"Cas « {cas_id} » : {message}")


# --- Petites vérifications partagées -------------------------------------------------------


def _egal(cas_id: str, nom: str, attendu: object, obtenu: object) -> None:
    if obtenu != attendu:
        raise _echec(cas_id, f"{nom} : attendu {attendu!r}, obtenu {obtenu!r}.")


def _attend_erreur(cas_id: str, sous_chaine: str, fn) -> None:
    """Exige que ``fn()`` lève ``ValueError`` dont le message contient ``sous_chaine``.

    C'est ce qui prouve qu'une règle **mord** : un coup illégal est refusé en citant sa règle,
    jamais accepté en silence. Une absence d'erreur, ou une erreur dont le message ne cite pas la
    règle attendue, fait échouer le cas.
    """
    try:
        fn()
    except ValueError as exc:
        if sous_chaine not in str(exc):
            raise _echec(
                cas_id, f"erreur levée mais « {sous_chaine} » absent du message : {exc}"
            ) from exc
        return
    raise _echec(cas_id, f"aucune erreur levée, or « {sous_chaine} » était attendu.")


# --- op: appliquer -------------------------------------------------------------------------


def _action_depuis(brut: object) -> Action:
    if not isinstance(brut, dict):
        raise ValueError(f"Une action se décrit par un mapping, reçu {type(brut).__name__}.")
    type_ = brut.get("type")
    auteur = brut.get("auteur")
    params = brut.get("params", {})
    if not isinstance(type_, str) or not type_:
        raise ValueError("Action : « type » manquant.")
    if not isinstance(auteur, str) or not auteur:
        raise ValueError("Action : « auteur » manquant.")
    if not isinstance(params, dict):
        raise ValueError("Action : « params » doit être un mapping.")
    return Action(type=type_, auteur=auteur, params=dict(params))


def _graine_du_cas(cas: dict) -> bytes:
    tirages = cas.get("tirages", [])
    if not tirages:
        return GRAINE_DEFAUT
    exigences = [(t["flux"], t["resultat"]) for t in tirages]
    return trouver_graine(exigences)


def _verifier_pokemon_attendu(
    cas_id: str, etiq: str, pokemon: PokemonEnJeu | None, attendu: object
) -> None:
    if attendu is None or attendu is False:
        if pokemon is not None:
            raise _echec(cas_id, f"{etiq} : attendu absent, mais un Pokémon est présent.")
        return
    if not isinstance(attendu, dict):
        raise _echec(cas_id, f"{etiq} : l'attendu d'un Pokémon doit être un mapping ou false.")
    if attendu.get("present") is False:
        if pokemon is not None:
            raise _echec(cas_id, f"{etiq} : attendu absent (present:false), mais présent.")
        return
    if pokemon is None:
        raise _echec(cas_id, f"{etiq} : attendu présent, mais absent (None).")
    if "degats" in attendu:
        _egal(cas_id, f"{etiq}.degats", attendu["degats"], pokemon.compteurs_degats)
    if "etats" in attendu:
        _egal(cas_id, f"{etiq}.etats", set(attendu["etats"]), set(pokemon.etats_speciaux))
    if "energies" in attendu:
        _egal(cas_id, f"{etiq}.energies", attendu["energies"], len(pokemon.energies))
    if "cartes" in attendu:
        _egal(cas_id, f"{etiq}.cartes", attendu["cartes"], len(pokemon.cartes))
    if "outil" in attendu:
        _egal(cas_id, f"{etiq}.outil", attendu["outil"], pokemon.outil is not None)


def _verifier_etat_attendu(cas_id: str, etat, attendu: dict) -> None:
    for cle, val in attendu.items():
        if cle == "terminee":
            _egal(cas_id, "terminee", val, etat.terminee)
        elif cle == "vainqueur":
            _egal(cas_id, "vainqueur", val, etat.vainqueur)
        elif cle == "raison_fin":
            _egal(cas_id, "raison_fin", val, etat.raison_fin)
        elif cle == "tour":
            _verifier_tour_attendu(cas_id, etat.tour, val)
        else:
            # Une clé restante nomme un joueur.
            joueur = next((j for j in etat.joueurs if j.id == cle), None)
            if joueur is None:
                raise _echec(cas_id, f"attendu.etat : « {cle} » n'est ni un champ ni un joueur.")
            _verifier_joueur_attendu(cas_id, joueur, val)


def _verifier_tour_attendu(cas_id: str, tour, attendu: dict) -> None:
    correspondances = {
        "phase": tour.phase,
        "numero": tour.numero,
        "joueur_actif": tour.joueur_actif,
        "energie_posee": tour.energie_posee,
        "supporter_joue": tour.supporter_joue,
        "retraite_faite": tour.retraite_faite,
    }
    for cle, val in attendu.items():
        if cle == "entres":
            _egal(cas_id, "tour.entres", set(val), set(tour.entres_en_jeu_ce_tour))
        elif cle == "evolues":
            _egal(cas_id, "tour.evolues", set(val), set(tour.evolues_ce_tour))
        elif cle in correspondances:
            _egal(cas_id, f"tour.{cle}", val, correspondances[cle])
        else:
            raise _echec(cas_id, f"attendu.tour : clé inconnue « {cle} ».")


def _verifier_joueur_attendu(cas_id: str, joueur, attendu: dict) -> None:
    comptes = {
        "main": joueur.main,
        "pioche": joueur.pioche,
        "defausse": joueur.defausse,
        "recompenses": joueur.recompenses,
        "zone_perdue": joueur.zone_perdue,
    }
    for cle, val in attendu.items():
        if cle == "actif":
            _verifier_pokemon_attendu(cas_id, f"{joueur.id}.actif", joueur.actif, val)
        elif cle == "actif_present":
            _egal(cas_id, f"{joueur.id}.actif_present", val, joueur.actif is not None)
        elif cle == "banc":
            if isinstance(val, list):
                _egal(cas_id, f"{joueur.id}.banc (taille)", len(val), len(joueur.banc))
                for i, slot in enumerate(val):
                    etiq = f"{joueur.id}.banc[{i}]"
                    _verifier_pokemon_attendu(cas_id, etiq, joueur.banc[i], slot)
            else:
                _egal(cas_id, f"{joueur.id}.banc", val, len(joueur.banc))
        elif cle in comptes:
            _egal(cas_id, f"{joueur.id}.{cle}", val, len(comptes[cle]))
        else:
            raise _echec(cas_id, f"attendu.{joueur.id} : clé inconnue « {cle} ».")


def _verifier_evenements(cas_id: str, produits: Sequence, attendus: list) -> None:
    """Chaque événement attendu doit exister dans ``produits``, dans l'ordre (sous-séquence).

    Un événement attendu ``{type, donnees?}`` correspond à un événement produit de même ``type``
    dont ``donnees`` contient (au moins) les paires attendues. On ne contraint pas les événements
    produits en trop : un cas nomme ce qui compte, pas l'exhaustivité du journal.
    """
    i = 0
    for exp in attendus:
        type_exp = exp.get("type")
        donnees_exp = exp.get("donnees", {})
        trouve = False
        while i < len(produits):
            evt = produits[i]
            i += 1
            if evt.type == type_exp and all(
                evt.donnees.get(k) == v for k, v in donnees_exp.items()
            ):
                trouve = True
                break
        if not trouve:
            produits_txt = ", ".join(f"{e.type}{e.donnees}" for e in produits)
            raise _echec(
                cas_id,
                f"événement attendu {exp} introuvable (dans l'ordre). Produits : [{produits_txt}].",
            )


def _op_appliquer(cas: dict) -> None:
    cas_id = cas["id"]
    etat, fiches = construire(cas["etat"])
    rng = Rng(_graine_du_cas(cas))

    bruts = cas.get("actions")
    if bruts is None:
        bruts = [cas["action"]]
    if not isinstance(bruts, list) or not bruts:
        raise _echec(cas_id, "« action » ou « actions » (liste non vide) est requis.")

    def _appliquer_tout():
        e = etat
        derniers_evts: tuple = ()
        for brut in bruts:
            action = _action_depuis(brut)
            # Le Checkup réclame les fiches du catalogue (D9) : on injecte celles décrites dans
            # l'état si le cas ne les a pas fournies explicitement.
            if action.type == ACTION_CHECKUP and "fiches" not in action.params:
                action = Action(action.type, action.auteur, {**action.params, "fiches": fiches})
            e, derniers_evts = appliquer(e, action, rng)
        return e, derniers_evts

    if "erreur" in cas:
        _attend_erreur(cas_id, cas["erreur"], _appliquer_tout)
        return

    etat_final, evenements = _appliquer_tout()
    attendu = cas.get("attendu", {})
    if "etat" in attendu:
        _verifier_etat_attendu(cas_id, etat_final, attendu["etat"])
    if "evenements" in attendu:
        _verifier_evenements(cas_id, evenements, attendu["evenements"])


# --- op: degats ----------------------------------------------------------------------------


def _modificateurs(bruts: object):
    if not bruts:
        return ()
    mods = []
    for m in bruts:
        op = m["op"]
        libelle = m.get("libelle", "effet")
        regle = m.get("regle", "R-10.1")
        valeur = m["valeur"]
        if op == "ajout":
            mods.append(modificateur_ajout(libelle, regle, valeur))
        elif op == "multiplie":
            mods.append(modificateur_multiplie(libelle, regle, valeur))
        elif op == "fixe":
            mods.append(modificateur_fixe(libelle, regle, valeur))
        else:
            raise ValueError(f"Opération de modificateur inconnue dans le cas : {op!r}.")
    return tuple(mods)


def _op_degats(cas: dict) -> None:
    cas_id = cas["id"]
    args = cas["args"]
    faiblesse = None
    if args.get("faiblesse"):
        f = args["faiblesse"]
        faiblesse = Faiblesse(type=f["type"], facteur=f.get("facteur", 2))
    resistance = None
    if args.get("resistance"):
        r = args["resistance"]
        resistance = Resistance(type=r["type"], reduction=r.get("reduction", 30))

    def _calcul():
        return resoudre_degats(
            base=args["base"],
            type_attaque=args.get("type_attaque"),
            modificateurs_attaquant=_modificateurs(args.get("modificateurs_attaquant")),
            faiblesse=faiblesse,
            resistance=resistance,
            modificateurs_defenseur=_modificateurs(args.get("modificateurs_defenseur")),
            au_banc=args.get("au_banc", False),
        )

    if "erreur" in cas:
        _attend_erreur(cas_id, cas["erreur"], _calcul)
        return

    resultat = _calcul()
    attendu = cas["attendu"]
    if "degats" in attendu:
        _egal(cas_id, "degats", attendu["degats"], resultat.degats)
    if "compteurs" in attendu:
        _egal(cas_id, "compteurs", attendu["compteurs"], resultat.compteurs)
    if "detail" in attendu:
        _egal(cas_id, "detail", attendu["detail"], resultat.detail)
    if "arrete_avant_degats" in attendu:
        _egal(
            cas_id, "arrete_avant_degats",
            attendu["arrete_avant_degats"], resultat.arrete_avant_degats,
        )


# --- op: compteurs (pose directe de dégâts/compteurs) --------------------------------------


def _pokemon_simple(spec: object) -> PokemonEnJeu:
    spec = spec or {}
    etats = spec.get("etats", [])
    return PokemonEnJeu(
        cartes=(Carte("p", "ref:p"),),
        energies=tuple(Carte(f"p.e{i}", f"ref:p.e{i}") for i in range(spec.get("energies", 0))),
        compteurs_degats=spec.get("degats", 0),
        etats_speciaux=frozenset(etats),
    )


def _op_compteurs(cas: dict) -> None:
    cas_id = cas["id"]
    pokemon = _pokemon_simple(cas.get("pokemon"))

    def _poser():
        p = pokemon
        if "poser_compteurs" in cas:
            p = poser_compteurs(p, cas["poser_compteurs"])
        if "poser_degats" in cas:
            p = poser_degats(p, cas["poser_degats"])
        return p

    if "erreur" in cas:
        _attend_erreur(cas_id, cas["erreur"], _poser)
        return
    p = _poser()
    _egal(cas_id, "degats", cas["attendu"]["degats"], p.compteurs_degats)


# --- op: etat (matrice de cumul, orientation, guérison, blocage) ---------------------------


def _op_etat(cas: dict) -> None:
    cas_id = cas["id"]

    def _resoudre():
        p = _pokemon_simple(cas.get("pokemon"))
        for e in cas.get("poser", []):
            p = appliquer_etat(p, e)
        if cas.get("soigner"):
            p = soigner_etats_speciaux(p)
        return p

    if "erreur" in cas:
        _attend_erreur(cas_id, cas["erreur"], _resoudre)
        return

    p = _resoudre()
    attendu = cas["attendu"]
    if "etats" in attendu:
        _egal(cas_id, "etats", set(attendu["etats"]), set(p.etats_speciaux))
    if "orientation" in attendu:
        _egal(cas_id, "orientation", attendu["orientation"], orientation(p))
    if "bloquant" in attendu:
        _egal(cas_id, "bloquant", attendu["bloquant"], etat_bloquant_attaque(p))


# --- op: recompenses (marqueur de règle → nombre) -----------------------------------------


def _op_recompenses(cas: dict) -> None:
    cas_id = cas["id"]
    if "erreur" in cas:
        _attend_erreur(cas_id, cas["erreur"], lambda: recompenses_pour_marqueur(cas["marqueur"]))
        return
    _egal(cas_id, "recompenses", cas["attendu"], recompenses_pour_marqueur(cas["marqueur"]))


# --- op: cout (l'énergie paie-t-elle l'attaque, R-9.2) ------------------------------------


def _op_cout(cas: dict) -> None:
    cas_id = cas["id"]
    c = cas["cout"]
    fournitures = cas.get("fournitures", [])

    def _valider():
        cout = CoutAttaque(types=c.get("types", {}), incolore=c.get("incolore", 0))
        return cout_satisfait(cout, fournitures)

    if "erreur" in cas:
        _attend_erreur(cas_id, cas["erreur"], _valider)
        return
    verdict = _valider()
    attendu = cas["attendu"]
    _egal(cas_id, "accepte", attendu["accepte"], verdict.accepte)
    if "regle" in attendu:
        _egal(cas_id, "regle", attendu["regle"], verdict.regle)


# --- op: legalite (valider / actions_legales) ---------------------------------------------


def _op_legalite(cas: dict) -> None:
    cas_id = cas["id"]
    etat, _ = construire(cas["etat"])
    if "action" in cas:
        verdict = valider(etat, _action_depuis(cas["action"]))
        attendu = cas["attendu"]
        _egal(cas_id, "accepte", attendu["accepte"], verdict.accepte)
        if "regle" in attendu:
            _egal(cas_id, "regle", attendu["regle"], verdict.regle)
    else:
        coups = actions_legales(etat, cas["joueur"])
        types = sorted({c.action.type for c in coups})
        _egal(cas_id, "types", sorted(cas["attendu"]["types"]), types)


# --- op: invariants (R-3) ------------------------------------------------------------------


def _op_invariants(cas: dict) -> None:
    cas_id = cas["id"]
    etat, _ = construire(cas["etat"])
    violations = verifier(etat)
    attendu = cas["attendu"]
    if attendu.get("saines"):
        if violations:
            raise _echec(cas_id, f"état attendu sain, violations trouvées : {violations}.")
    if "violation_contient" in attendu:
        motif = attendu["violation_contient"]
        if not any(motif in v for v in violations):
            raise _echec(cas_id, f"violation « {motif} » attendue, trouvées : {violations}.")


# --- op: rng (reproductibilité et vérifiabilité d'un tirage, R-4.7) -----------------------


def _op_rng(cas: dict) -> None:
    cas_id = cas["id"]
    exigences = [(t["flux"], t["resultat"]) for t in cas["tirages"]]
    graine = trouver_graine(exigences)
    # 1) Reproductibilité : rejouer les tirages sous cette graine redonne EXACTEMENT les résultats.
    rng = Rng(graine)
    besoins: dict[str, list[str]] = {}
    for flux, res in exigences:
        besoins.setdefault(flux, []).append(res)
    for flux, attendus in besoins.items():
        for attendu in attendus:
            obtenu = rng.pile_ou_face(flux, cas.get("motif", "R-4.7"))
            _egal(cas_id, f"tirage {flux}", attendu, obtenu)
    # 2) Vérifiabilité : le vérificateur a posteriori ne relève AUCUNE anomalie (anti-triche).
    anomalies = verifier_journal(graine, rng.journal())
    if anomalies:
        raise _echec(cas_id, f"vérificateur de journal : anomalies inattendues {anomalies}.")


# --- Répartition ---------------------------------------------------------------------------

_OPERATIONS = {
    "appliquer": _op_appliquer,
    "degats": _op_degats,
    "compteurs": _op_compteurs,
    "etat": _op_etat,
    "recompenses": _op_recompenses,
    "cout": _op_cout,
    "legalite": _op_legalite,
    "invariants": _op_invariants,
    "rng": _op_rng,
}

#: Les opérations reconnues par l'exécuteur (pour la documentation et les tests).
OPERATIONS: frozenset[str] = frozenset(_OPERATIONS)


def executer(cas: object) -> None:
    """Exécute un cas désérialisé contre le moteur, ou lève :class:`EchecCas`.

    Un cas est un ``dict`` avec au moins ``id``, ``regles`` (liste de ``R-x.y``), ``description``
    et ``op``. Un ``op`` inconnu est une panne (D9 : jamais deviné). L'exécuteur ne fait aucune
    E/S : l'appelant a déjà chargé le YAML.
    """
    if not isinstance(cas, dict):
        raise EchecCas(f"Un cas doit être un mapping, reçu {type(cas).__name__}.")
    cas_id = cas.get("id", "<sans id>")
    op = cas.get("op")
    handler = _OPERATIONS.get(op)
    if handler is None:
        raise _echec(cas_id, f"opération inconnue : {op!r}. Connues : {sorted(OPERATIONS)}.")
    handler(cas)


__all__ = ["EchecCas", "OPERATIONS", "executer"]
