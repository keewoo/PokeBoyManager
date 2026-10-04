"""Les **essais de script** — prouver qu'un script d'effet fait ce que la carte dit, en données.

Module **pur** (aucune E/S, ni HTTP, ni base, ni réseau), comme tout ``pbm_game``. Lot
``j-effets-assistance-ia`` (jalon J2).

**Pourquoi ce module.** L'assistance IA (``pbm_api.jeu.scripts.assistance``) demande au modèle,
pour chaque texte de carte non scripté, **un script ET ses cas de test**. Un script plausible mais
faux est plus dangereux qu'une carte non supportée : il fait perdre des parties sans que personne ne
comprenne (risque nommé de la fiche du lot). Le vrai garde-fou n'est donc pas la confiance annoncée
par le modèle, mais l'**exécution réelle** du script contre le moteur — ses essais, et une batterie
de **cohérence maison**. Ce module est ce qui exécute ; il vit dans le moteur **pur** pour la même
raison que les cas de règles (:mod:`pbm_game.cas`) : on prouve un moteur par des milliers de cas,
on ne le relit pas.

**Un essai est une donnée** (un ``dict`` sérialisable, le même grain que les cas de
``pbm_game.cas``) : un état de départ (décrit concisément, construit par
:func:`pbm_game.cas.constructeur.construire`), le contexte d'exécution de l'effet (qui joue, sur
qui), des tirages de pile ou face déterministes au besoin, et un attendu sur l'état final. On le
**rejoue** contre :func:`pbm_game.effets.dsl.interprete.executer_programme`, puis on **vérifie**.

**La cohérence maison.** Au-delà de l'attendu que l'IA écrit, chaque essai passe des contrôles que
l'IA ne peut pas désactiver (:func:`anomalies_coherence`) : un effet ne **crée ni ne détruit** de
carte (les cartes se déplacent entre zones, jamais n'apparaissent ni ne disparaissent — R-3.1), et
il ne **fabrique pas** de violation d'invariant qui n'existait pas avant lui (R-3). C'est ce
contrôle, pas la confiance du modèle, qui attrape le script « presque juste ».

Format d'un essai (toutes les clés sauf ``etat`` sont facultatives) ::

    {
      "nom": "pioche 2",                     # libellé lisible
      "etat": { ... spec constructeur ... },  # cf. docs/jeu/CAS-EXECUTABLES.md
      "contexte": {                           # défaut : joueur=alice, adversaire=bob
        "joueur": "alice", "adversaire": "bob",
        "acteur_actif": "<instance_id>|null",
        "defenseur": "<instance_id>|null",
        "metadonnees": {"ref:x": {"categorie": "energie"}}
      },
      "tirages": [{"flux": "dsl:pile:alice", "resultat": "face"}],
      "attendu": {
        "cout_paye": true,                    # facultatif
        "etat": { ... comme un cas `appliquer` ... }
      }
    }
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ...cas.constructeur import GRAINE_DEFAUT, JOUEURS_DEFAUT, construire, trouver_graine
from ...rng import Rng
from ...state.invariants import verifier
from ...state.modele import EtatPartie
from ..pile import SourceEffet
from .chargement import ProgrammeInvalide, charger_programme
from .contexte import ContexteEffet
from .interprete import ResultatProgramme, executer_programme
from .modele import Programme


def _compter_cartes(etat: EtatPartie) -> int:
    """Le nombre **total** d'exemplaires de carte présents dans un état, toutes zones confondues.

    Une carte est un ``instance_id`` : elle vit dans une zone (pioche, main, défausse, récompenses,
    zone perdue) ou sur un Pokémon (sa pile d'évolutions, ses énergies, son Outil), ou c'est le
    Stade en jeu. Un effet **déplace** des cartes entre ces emplacements ; il n'en crée ni n'en
    détruit (R-3.1). Compter avant et après l'exécution est donc le garde-fou le plus simple et le
    plus universel contre un script faux : si le total change, le script a fabriqué ou perdu une
    carte, quoi qu'en dise son attendu.
    """
    total = 1 if etat.stade is not None else 0
    for joueur in etat.joueurs:
        total += (
            len(joueur.pioche)
            + len(joueur.main)
            + len(joueur.defausse)
            + len(joueur.recompenses)
            + len(joueur.zone_perdue)
        )
        for pokemon in (joueur.actif, *joueur.banc):
            if pokemon is None:
                continue
            total += len(pokemon.cartes) + len(pokemon.energies) + (1 if pokemon.outil else 0)
    return total


def anomalies_coherence(etat_avant: EtatPartie, resultat: ResultatProgramme) -> list[str]:
    """Les anomalies de **cohérence maison** d'une exécution — liste vide = le script est cohérent.

    Deux contrôles que la confiance du modèle ne peut pas contourner :

    * **conservation des cartes** (R-3.1) : le total d'exemplaires est identique avant et après —
      un script qui en crée ou en détruit est faux, même si son attendu « passe » ;
    * **invariants** (R-3) : l'état final ne porte **aucune** violation que l'état de départ ne
      portait déjà. On compare les deux ensembles plutôt que d'exiger un état final parfait : un
      cas peut légitimement partir d'un état limite (``construire`` ne juge pas le plateau), mais le
      script ne doit pas en **ajouter** une.
    """
    anomalies: list[str] = []
    avant = _compter_cartes(etat_avant)
    apres = _compter_cartes(resultat.etat)
    if avant != apres:
        anomalies.append(
            f"conservation des cartes (R-3.1) : {avant} exemplaire(s) avant, {apres} après — "
            f"un effet déplace des cartes, il n'en crée ni n'en détruit."
        )
    violations_avant = set(verifier(etat_avant))
    violations_apres = set(verifier(resultat.etat))
    nouvelles = violations_apres - violations_avant
    for v in sorted(nouvelles):
        anomalies.append(f"invariant brisé par le script (R-3) : {v}")
    return anomalies


def _source(essai: Mapping) -> SourceEffet:
    """La :class:`SourceEffet` d'un essai — nommée par ``nom`` pour un journal lisible."""
    nom = essai.get("nom")
    libelle = str(nom) if isinstance(nom, str) and nom.strip() else "essai de script"
    ctx = essai.get("contexte") or {}
    instance_id = ctx.get("acteur_actif") if isinstance(ctx, Mapping) else None
    return SourceEffet(libelle=libelle, ref="essai", instance_id=instance_id)


def _contexte(essai: Mapping, ids: tuple[str, str]) -> ContexteEffet:
    """Construit le :class:`ContexteEffet` d'un essai (défaut : premier/second joueur de l'état)."""
    brut = essai.get("contexte") or {}
    if not isinstance(brut, Mapping):
        raise ValueError("« contexte » d'un essai doit être un mapping.")
    joueur = brut.get("joueur", ids[0])
    adversaire = brut.get("adversaire", ids[1])
    metadonnees = brut.get("metadonnees", {})
    if not isinstance(metadonnees, Mapping):
        raise ValueError("« contexte.metadonnees » doit être un mapping ref → attributs.")
    return ContexteEffet(
        source=_source(essai),
        joueur=joueur,
        adversaire=adversaire,
        acteur_actif=brut.get("acteur_actif"),
        defenseur=brut.get("defenseur"),
        metadonnees=dict(metadonnees),
    )


def _graine(essai: Mapping) -> bytes:
    """La graine d'un essai : par défaut aucune (pas de tirage), sinon celle qui produit ses
    pile ou face voulus — même mécanique que les cas de règles (:func:`trouver_graine`)."""
    tirages = essai.get("tirages") or []
    if not tirages:
        return GRAINE_DEFAUT
    exigences = [(t["flux"], t["resultat"]) for t in tirages]
    return trouver_graine(exigences)


def _ids_etat(spec: Mapping) -> tuple[str, str]:
    """Les deux identifiants de joueur d'une spec d'état (``alice``/``bob`` par défaut)."""
    meta = {"tour", "stade", "stade_proprietaire", "terminee", "vainqueur", "raison_fin"}
    nommes = [c for c in spec if c not in meta]
    if len(nommes) == 2:
        return (nommes[0], nommes[1])
    return JOUEURS_DEFAUT


def _pokemon(etat: EtatPartie, joueur_id: str, place: str, index: int):
    """Le Pokémon désigné (``actif`` ou ``banc[index]``) d'un joueur, ou ``None``."""
    joueur = next((j for j in etat.joueurs if j.id == joueur_id), None)
    if joueur is None:
        return None
    if place == "actif":
        return joueur.actif
    if place == "banc" and 0 <= index < len(joueur.banc):
        return joueur.banc[index]
    return None


def _anomalies_pokemon(etiq: str, pokemon, attendu: object) -> list[str]:
    """Vérifie l'attendu d'un Pokémon (dégâts, états, énergies, cartes, outil, présence)."""
    out: list[str] = []
    if attendu is None or attendu is False:
        if pokemon is not None:
            out.append(f"{etiq} : attendu absent, mais un Pokémon est présent.")
        return out
    if not isinstance(attendu, Mapping):
        out.append(f"{etiq} : l'attendu d'un Pokémon doit être un mapping ou false.")
        return out
    if attendu.get("present") is False:
        if pokemon is not None:
            out.append(f"{etiq} : attendu absent (present:false), mais présent.")
        return out
    if pokemon is None:
        out.append(f"{etiq} : attendu présent, mais absent.")
        return out
    controles = {
        "degats": ("compteurs_degats", lambda p: p.compteurs_degats),
        "energies": ("energies", lambda p: len(p.energies)),
        "cartes": ("cartes", lambda p: len(p.cartes)),
        "outil": ("outil", lambda p: p.outil is not None),
    }
    for cle, (_, lire) in controles.items():
        if cle in attendu and attendu[cle] != lire(pokemon):
            out.append(f"{etiq}.{cle} : attendu {attendu[cle]!r}, obtenu {lire(pokemon)!r}.")
    if "etats" in attendu and set(attendu["etats"]) != set(pokemon.etats_speciaux):
        out.append(
            f"{etiq}.etats : attendu {sorted(attendu['etats'])}, "
            f"obtenu {sorted(pokemon.etats_speciaux)}."
        )
    return out


def _anomalies_joueur(etat: EtatPartie, joueur_id: str, attendu: Mapping) -> list[str]:
    """Vérifie l'attendu d'un joueur : comptes de zones et Pokémon (actif, banc)."""
    out: list[str] = []
    joueur = next((j for j in etat.joueurs if j.id == joueur_id), None)
    if joueur is None:
        return [f"attendu.{joueur_id} : joueur inconnu dans l'état final."]
    comptes = {
        "main": joueur.main,
        "pioche": joueur.pioche,
        "defausse": joueur.defausse,
        "recompenses": joueur.recompenses,
        "zone_perdue": joueur.zone_perdue,
    }
    for cle, val in attendu.items():
        if cle == "actif":
            out += _anomalies_pokemon(f"{joueur_id}.actif", joueur.actif, val)
        elif cle == "actif_present":
            if val != (joueur.actif is not None):
                out.append(f"{joueur_id}.actif_present : attendu {val!r}.")
        elif cle == "banc":
            if isinstance(val, list):
                if len(val) != len(joueur.banc):
                    out.append(
                        f"{joueur_id}.banc : attendu {len(val)} Pokémon, obtenu {len(joueur.banc)}."
                    )
                for i, slot in enumerate(val):
                    pk = joueur.banc[i] if i < len(joueur.banc) else None
                    out += _anomalies_pokemon(f"{joueur_id}.banc[{i}]", pk, slot)
            elif val != len(joueur.banc):
                out.append(f"{joueur_id}.banc : attendu {val!r}, obtenu {len(joueur.banc)}.")
        elif cle in comptes:
            if val != len(comptes[cle]):
                out.append(f"{joueur_id}.{cle} : attendu {val!r}, obtenu {len(comptes[cle])}.")
        else:
            out.append(f"attendu.{joueur_id} : clé inconnue « {cle} ».")
    return out


def _anomalies_etat_attendu(etat: EtatPartie, attendu: Mapping) -> list[str]:
    """Compare l'état final à l'attendu de l'essai (champs globaux + par joueur)."""
    out: list[str] = []
    globaux = {
        "terminee": etat.terminee,
        "vainqueur": etat.vainqueur,
        "raison_fin": etat.raison_fin,
    }
    for cle, val in attendu.items():
        if cle in globaux:
            if val != globaux[cle]:
                out.append(f"{cle} : attendu {val!r}, obtenu {globaux[cle]!r}.")
        else:
            if not isinstance(val, Mapping):
                out.append(f"attendu.etat.{cle} : mapping de joueur attendu.")
                continue
            out += _anomalies_joueur(etat, cle, val)
    return out


def executer_essai(programme: Programme, essai: Mapping) -> list[str]:
    """Rejoue un essai contre un programme **déjà chargé**, et renvoie ses anomalies (vide = vert).

    Ne lève pas sur une anomalie **de jeu** (attendu non tenu, incohérence) : elle est rapportée
    dans la liste, pour que la porte de vérification (:mod:`pbm_api.jeu.scripts.assistance`) les
    collecte toutes. Lève ``ValueError`` seulement si l'essai lui-même est **malformé** (un essai
    illisible est une panne, pas un échec de script). Une exception levée par le moteur pendant
    l'exécution (une primitive qui refuse) est, elle, capturée et rapportée comme anomalie : un
    script qui fait planter le moteur est un script faux.
    """
    if not isinstance(essai, Mapping):
        raise ValueError(f"Un essai doit être un mapping, reçu {type(essai).__name__}.")
    if "etat" not in essai:
        raise ValueError("Un essai doit décrire un « etat » de départ.")
    etat_avant, _fiches = construire(essai["etat"])
    ids = _ids_etat(essai["etat"]) if isinstance(essai["etat"], Mapping) else JOUEURS_DEFAUT
    ctx = _contexte(essai, ids)
    rng = Rng(_graine(essai))

    try:
        resultat = executer_programme(etat_avant, programme, ctx, rng)
    except Exception as exc:  # noqa: BLE001 — un plantage moteur EST une anomalie du script.
        return [f"le script a fait planter le moteur : {type(exc).__name__}: {exc}"]

    anomalies = anomalies_coherence(etat_avant, resultat)
    attendu = essai.get("attendu") or {}
    if not isinstance(attendu, Mapping):
        raise ValueError("« attendu » d'un essai doit être un mapping.")
    if "cout_paye" in attendu and attendu["cout_paye"] != resultat.cout_paye:
        anomalies.append(
            f"cout_paye : attendu {attendu['cout_paye']!r}, obtenu {resultat.cout_paye!r}."
        )
    if "etat" in attendu:
        if not isinstance(attendu["etat"], Mapping):
            raise ValueError("« attendu.etat » doit être un mapping.")
        anomalies += _anomalies_etat_attendu(resultat.etat, attendu["etat"])
    return anomalies


def verifier_script(script: object, essais: Sequence[Mapping]) -> dict:
    """Charge un script, le passe par **tous** ses essais, et renvoie un verdict structuré.

    C'est le cœur réutilisable de la porte de vérification de l'assistance IA. Il reste **pur** :
    aucune E/S, aucun appel réseau — on lui donne un script (``dict`` JSON-ish) et des essais, il
    rend ``{"valide": bool, "raison": str, "essais": [...]}``. ``valide`` est vrai **seulement**
    si le script se charge (DSL conforme), s'il y a **au moins un essai** (on ne valide pas un
    effet qu'aucun cas ne prouve — D9), et si **chaque** essai passe (attendu tenu ET cohérence).

    ``essais[i]`` porte ``{"nom", "anomalies": [...]}`` : un essai sans anomalie est vert. La
    ``raison`` nomme le premier obstacle — script illisible, aucun essai, ou le nom de l'essai qui
    a mordu — jamais un « au mieux ».
    """
    detail: list[dict] = []
    try:
        programme = charger_programme(script)
    except ProgrammeInvalide as exc:
        return {
            "valide": False,
            "raison": f"script non conforme au langage : {exc}",
            "essais": detail,
        }

    if not essais:
        return {
            "valide": False,
            "raison": "aucun essai fourni — on ne valide pas un effet qu'aucun cas ne prouve (D9)",
            "essais": detail,
        }

    premier_echec: str | None = None
    for i, essai in enumerate(essais):
        nom = essai.get("nom") if isinstance(essai, Mapping) else None
        nom = str(nom) if isinstance(nom, str) and nom.strip() else f"essai #{i + 1}"
        try:
            anomalies = executer_essai(programme, essai)
        except ValueError as exc:
            anomalies = [f"essai malformé : {exc}"]
        detail.append({"nom": nom, "anomalies": anomalies})
        if anomalies and premier_echec is None:
            premier_echec = nom

    if premier_echec is not None:
        return {
            "valide": False,
            "raison": f"l'essai « {premier_echec} » a échoué (attendu non tenu ou incohérence)",
            "essais": detail,
        }
    return {"valide": True, "raison": "", "essais": detail}


__all__ = [
    "anomalies_coherence",
    "executer_essai",
    "verifier_script",
]
