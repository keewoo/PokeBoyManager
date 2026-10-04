"""Les **primitives** du langage — une fonction pure par verbe, chacune testable isolément.

Module **pur** (aucune E/S). Chaque primitive reçoit l'``Execution`` en cours et son
:class:`~pbm_game.effets.dsl.modele.Instruction`, fait avancer l'état (toujours en
**remplaçant** la référence figée, jamais en mutant) et **journalise** ce qu'elle a fait. Les
structures de contrôle (``si``, ``repeter``, ``pile_ou_face``, ``choisir``) vivent dans
``interprete.py`` : ici, uniquement les feuilles.

**Le cas « aucune cible » est traité partout, et jamais en silence** (critère d'acceptation n°2) :
une primitive qui ne trouve rien à faire émet un :data:`~pbm_game.effets.pile.EVT_EFFET_SANS_CIBLE`
nommant la raison, et la partie continue — elle ne bloque pas, elle le **dit**.

Conventions de dégâts (R-10.4/R-10.6, cf. ``docs/jeu/DEGATS.md``) : ``compteurs_degats`` compte
en **PV**. ``poser_compteurs`` et ``soigner`` comptent en **marqueurs** (1 marqueur = 10 PV, comme
le texte des cartes « placez N marqueurs ») ; ``infliger_degats`` compte en **dégâts** (PV,
multiple de 10). On réutilise :func:`pbm_game.combat.resolution.poser_degats` et
:func:`~pbm_game.combat.resolution.poser_compteurs` — une seule arithmétique de dégâts.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from ...combat.resolution import poser_compteurs, poser_degats
from ...etats.matrice import soigner_etats_speciaux
from ...rng import Rng  # noqa: F401  (type documentaire ; le rng réel vit dans l'Execution)
from ...state.modele import ETATS_ORIENTATION, Joueur, PokemonEnJeu
from ..pile import EVT_EFFET_SANS_CIBLE
from ..verrous import EVT_VERROU_POSE, Verrou
from .execution import Execution
from .modele import Instruction
from .selection import CibleCarte, CiblePokemon, candidats
from .vocabulaire import (
    CAT_OUTIL,
    OP_ANNULER,
    OP_ATTACHER,
    OP_CHANGER_ACTIF,
    OP_CHERCHER,
    OP_DEFAUSSER,
    OP_DEPLACER,
    OP_EMPECHER,
    OP_INFLIGER_DEGATS,
    OP_MELANGER,
    OP_PIOCHER,
    OP_POSER_COMPTEURS,
    OP_POSER_ETAT,
    OP_REGARDER,
    OP_RETIRER_ETAT,
    OP_REVELER,
    OP_SOIGNER,
    POSITION_DESSOUS,
    POSITION_DESSUS,
    ZONE_DEFAUSSE,
)

#: Une primitive **a agi** — porte l'``op``, la source (via le contexte) et ce qui a été fait.
EVT_DSL_PRIMITIVE = "dsl_primitive"


# --- Journalisation ----------------------------------------------------------
from ..pile import Evenement  # noqa: E402  (après la constante, pour lisibilité)


def _evt(ex: Execution, op: str, **donnees) -> None:
    """Ajoute au journal un :data:`EVT_DSL_PRIMITIVE` nommant la source (« à cause de X »)."""
    ex.evenements.append(
        Evenement(EVT_DSL_PRIMITIVE, {"op": op, "source": ex.ctx.source.en_json(), **donnees})
    )


def _sans_cible(ex: Execution, instr: Instruction, raison: str) -> None:
    """Journalise qu'une primitive n'avait **aucune cible** — jamais un repli muet (critère 2)."""
    ex.evenements.append(
        Evenement(
            EVT_EFFET_SANS_CIBLE,
            {
                "source": ex.ctx.source.en_json(),
                "type_effet": instr.op,
                "regle": instr.regle or "",
                "libelle": instr.op,
                "raison": raison,
            },
        )
    )


# --- Helpers immuables sur l'état --------------------------------------------


def _joueur(etat, jid: str) -> Joueur:
    for j in etat.joueurs:
        if j.id == jid:
            return j
    raise ValueError(f"Joueur « {jid} » absent de la partie.")


def _remplacer_joueur(etat, joueur: Joueur):
    joueurs = list(etat.joueurs)
    for i, j in enumerate(joueurs):
        if j.id == joueur.id:
            joueurs[i] = joueur
            return replace(etat, joueurs=(joueurs[0], joueurs[1]))
    raise ValueError(f"Joueur « {joueur.id} » absent de la partie.")


def _maj_pokemon(etat, cible: CiblePokemon, fn: Callable[[PokemonEnJeu], PokemonEnJeu]):
    """Applique ``fn`` au Pokémon repéré par ``cible`` (Actif ou banc), renvoie un nouvel état."""
    joueur = _joueur(etat, cible.joueur)
    if joueur.actif is not None and joueur.actif.cartes[0].instance_id == cible.identite:
        return _remplacer_joueur(etat, replace(joueur, actif=fn(joueur.actif)))
    banc = list(joueur.banc)
    for i, p in enumerate(banc):
        if p.cartes[0].instance_id == cible.identite:
            banc[i] = fn(p)
            return _remplacer_joueur(etat, replace(joueur, banc=tuple(banc)))
    # La cible a disparu entre la sélection et l'application : c'est une incohérence, pas un cas
    # normal — on le dit (jamais deviné).
    raise ValueError(f"Pokémon cible {cible.identite!r} introuvable au moment d'agir.")


def _retirer_cartes(joueur: Joueur, zone: str, instance_ids: set[str]) -> tuple[Joueur, tuple]:
    """Retire de ``zone`` les cartes nommées ; renvoie ``(joueur, retirees)`` (ordre gardé)."""
    gardees = []
    retirees = []
    for c in getattr(joueur, zone):
        (retirees if c.instance_id in instance_ids else gardees).append(c)
    return replace(joueur, **{zone: tuple(gardees)}), tuple(retirees)


def _ajouter_cartes(joueur: Joueur, zone: str, cartes: tuple, position: str) -> Joueur:
    """Ajoute ``cartes`` à ``zone``, par le dessus / le dessous (zones ordonnées) ou à la fin."""
    actuelles = getattr(joueur, zone)
    if position == POSITION_DESSUS:
        nouvelles = tuple(cartes) + actuelles
    else:  # dessous, ou zone non ordonnée (main, défausse) → à la fin
        nouvelles = actuelles + tuple(cartes)
    return replace(joueur, **{zone: nouvelles})


# --- Résolution de cible (partagée avec l'interprète) ------------------------


def restreindre(ex: Execution, cands: list, sel) -> list:
    """Restreint ``cands`` à ``sel.nombre`` : dessus / dessous (ordre), ou stratégie (au choix)."""
    if sel.nombre is None or len(cands) <= sel.nombre:
        return cands
    if sel.position == POSITION_DESSUS:
        return cands[: sel.nombre]
    if sel.position == POSITION_DESSOUS:
        return cands[-sel.nombre :]
    return ex.strategie(cands, sel.nombre, ex.ctx)


def resoudre_cibles(ex: Execution, instr: Instruction) -> list:
    """Les cibles finales d'une instruction : son sélecteur, ou la **sélection** du ``choisir``."""
    if instr.cible is None:
        return list(ex.selection) if ex.selection is not None else []
    return restreindre(ex, candidats(ex.etat, instr.cible, ex.ctx), instr.cible)


# --- Les primitives ----------------------------------------------------------


def prim_piocher(ex: Execution, instr: Instruction) -> None:
    """« Piochez N cartes » — du **sommet** de la pioche d'un joueur vers sa main (R-5.2).

    Le joueur qui pioche est celui que vise le ``proprietaire`` de la cible (``moi`` par défaut,
    ``adversaire`` pour « votre adversaire pioche N » — la perturbation des Supporters). On ne
    journalise que le **nombre** piochée, jamais les identités : repiocher la main de l'adversaire
    ne révèle pas son contenu (confidentialité, lot j-cartes-supporters).
    """
    jid = ex.ctx.joueur
    if instr.cible is not None and instr.cible.proprietaire != "moi":
        jid = ex.ctx.adversaire
    joueur = _joueur(ex.etat, jid)
    n = min(instr.nombre, len(joueur.pioche))
    if n == 0:
        _sans_cible(ex, instr, "pioche vide — rien à piocher")
        return
    piochees, reste = joueur.pioche[:n], joueur.pioche[n:]
    ex.etat = _remplacer_joueur(ex.etat, replace(joueur, pioche=reste, main=joueur.main + piochees))
    _evt(ex, OP_PIOCHER, joueur=jid, nombre=n, demande=instr.nombre)


def prim_chercher(ex: Execution, instr: Instruction) -> None:
    """« Cherchez dans votre deck … » — déplace les cartes trouvées vers la main (R-5.2)."""
    cibles = [c for c in resoudre_cibles(ex, instr) if isinstance(c, CibleCarte)]
    if not cibles:
        _sans_cible(ex, instr, "aucune carte ne correspond au sélecteur")
        return
    deplacees = 0
    par_joueur: dict[tuple[str, str], set[str]] = {}
    for c in cibles:
        par_joueur.setdefault((c.joueur, c.zone), set()).add(c.instance_id)
    for (jid, zone), ids in par_joueur.items():
        joueur, retirees = _retirer_cartes(_joueur(ex.etat, jid), zone, ids)
        joueur = _ajouter_cartes(joueur, "main", retirees, "au_choix")
        ex.etat = _remplacer_joueur(ex.etat, joueur)
        deplacees += len(retirees)
    _evt(ex, OP_CHERCHER, nombre=deplacees, refs=sorted(c.ref for c in cibles))


def prim_defausser(ex: Execution, instr: Instruction) -> None:
    """« Défaussez … » — déplace les cartes désignées vers la défausse de leur propriétaire."""
    cibles = [c for c in resoudre_cibles(ex, instr) if isinstance(c, CibleCarte)]
    if not cibles:
        _sans_cible(ex, instr, "aucune carte à défausser")
        return
    par_joueur: dict[tuple[str, str], set[str]] = {}
    for c in cibles:
        par_joueur.setdefault((c.joueur, c.zone), set()).add(c.instance_id)
    for (jid, zone), ids in par_joueur.items():
        if zone == "defausse":
            continue  # déjà à la défausse
        joueur, retirees = _retirer_cartes(_joueur(ex.etat, jid), zone, ids)
        joueur = _ajouter_cartes(joueur, "defausse", retirees, "au_choix")
        ex.etat = _remplacer_joueur(ex.etat, joueur)
    _evt(ex, OP_DEFAUSSER, nombre=len(cibles), refs=sorted(c.ref for c in cibles))


def prim_attacher(ex: Execution, instr: Instruction) -> None:
    """« Attachez cette carte Énergie/Outil à … » — de la source vers un Pokémon destination."""
    sources = [
        c
        for c in restreindre(ex, candidats(ex.etat, instr.source, ex.ctx), instr.source)
        if isinstance(c, CibleCarte)
    ]
    dests = [c for c in resoudre_cibles(ex, instr) if isinstance(c, CiblePokemon)]
    if not sources:
        _sans_cible(ex, instr, "aucune carte à attacher")
        return
    if not dests:
        _sans_cible(ex, instr, "aucun Pokémon où attacher")
        return
    dest = dests[0]
    outil = instr.source.categorie == CAT_OUTIL
    for src in sources:
        joueur, retirees = _retirer_cartes(
            _joueur(ex.etat, src.joueur), src.zone, {src.instance_id}
        )
        ex.etat = _remplacer_joueur(ex.etat, joueur)
        carte = retirees[0]

        def _attache(pok: PokemonEnJeu, carte=carte, outil=outil) -> PokemonEnJeu:
            if outil:
                return replace(pok, outil=carte)
            return replace(pok, energies=pok.energies + (carte,))

        ex.etat = _maj_pokemon(ex.etat, dest, _attache)
    _evt(ex, OP_ATTACHER, nombre=len(sources), vers=dest.identite, outil=outil)


def prim_deplacer(ex: Execution, instr: Instruction) -> None:
    """« Déplacez N énergies de … vers … » — entre deux Pokémon, ou **vers la défausse** (coût).

    Destination ``defausse`` : c'est la **défausse d'énergie** (« défaussez N Énergie de ce
    Pokémon ») — le coût typique d'une attaque à effet. Les énergies attachées quittent le Pokémon
    pour la défausse de leur propriétaire ; les compteurs de dégâts ne bougent pas. Sinon, c'est un
    transfert d'énergie d'un Pokémon à un autre (*Transfert d'Énergie*).
    """
    origines = [
        c
        for c in restreindre(ex, candidats(ex.etat, instr.source, ex.ctx), instr.source)
        if isinstance(c, CiblePokemon)
    ]
    if not origines:
        _sans_cible(ex, instr, "origine absente pour le déplacement d'énergie")
        return
    origine = origines[0]
    joueur_src = _joueur(ex.etat, origine.joueur)
    pok_src = _pokemon_par_identite(joueur_src, origine.identite)
    n = instr.nombre if instr.nombre is not None else len(pok_src.energies)
    n = min(n, len(pok_src.energies))
    if n == 0:
        _sans_cible(ex, instr, "aucune énergie à déplacer")
        return
    bougees = pok_src.energies[:n]
    reste = pok_src.energies[n:]

    # Destination « défausse » : défausse d'énergie (coût d'attaque). On lit la zone du sélecteur
    # de destination plutôt qu'un Pokémon cible — c'est une carte, pas un Pokémon.
    if instr.cible is not None and instr.cible.zone == ZONE_DEFAUSSE:
        ex.etat = _maj_pokemon(ex.etat, origine, lambda p: replace(p, energies=reste))
        joueur_dest = _joueur(ex.etat, origine.joueur)  # relu après la maj (état figé remplacé)
        ex.etat = _remplacer_joueur(
            ex.etat, replace(joueur_dest, defausse=joueur_dest.defausse + bougees)
        )
        _evt(ex, OP_DEPLACER, nombre=n, de=origine.identite, vers="defausse")
        return

    dests = [c for c in resoudre_cibles(ex, instr) if isinstance(c, CiblePokemon)]
    if not dests:
        _sans_cible(ex, instr, "destination absente pour le déplacement d'énergie")
        return
    dest = dests[0]
    ex.etat = _maj_pokemon(ex.etat, origine, lambda p: replace(p, energies=reste))
    ex.etat = _maj_pokemon(ex.etat, dest, lambda p: replace(p, energies=p.energies + bougees))
    _evt(ex, OP_DEPLACER, nombre=n, de=origine.identite, vers=dest.identite)


def prim_soigner(ex: Execution, instr: Instruction) -> None:
    """« Soignez N marqueurs » (ou tout) — retire des compteurs de dégâts, plancher à 0 (R-10.4)."""
    cibles = [c for c in resoudre_cibles(ex, instr) if isinstance(c, CiblePokemon)]
    if not cibles:
        _sans_cible(ex, instr, "aucun Pokémon à soigner")
        return
    retire_pv = (instr.nombre * 10) if instr.nombre is not None else None
    total = 0
    for cible in cibles:

        def _soigne(pok: PokemonEnJeu, retire_pv=retire_pv) -> PokemonEnJeu:
            nouveau = 0 if retire_pv is None else max(0, pok.compteurs_degats - retire_pv)
            return replace(pok, compteurs_degats=nouveau)

        joueur = _joueur(ex.etat, cible.joueur)
        pok = _pokemon_par_identite(joueur, cible.identite)
        avant = pok.compteurs_degats
        ex.etat = _maj_pokemon(ex.etat, cible, _soigne)
        apres = _pokemon_par_identite(
            _joueur(ex.etat, cible.joueur), cible.identite
        ).compteurs_degats
        total += avant - apres
    _evt(ex, OP_SOIGNER, nombre=len(cibles), pv_soignes=total)


def prim_poser_compteurs(ex: Execution, instr: Instruction) -> None:
    """« Placez N marqueurs sur … » — compteurs directs, aucune faiblesse/résistance (R-10.6)."""
    cibles = [c for c in resoudre_cibles(ex, instr) if isinstance(c, CiblePokemon)]
    if not cibles:
        _sans_cible(ex, instr, "aucun Pokémon où poser des marqueurs")
        return
    for cible in cibles:
        ex.etat = _maj_pokemon(ex.etat, cible, lambda p: poser_compteurs(p, instr.nombre))
    _evt(ex, OP_POSER_COMPTEURS, nombre=len(cibles), marqueurs=instr.nombre)


def prim_infliger_degats(ex: Execution, instr: Instruction) -> None:
    """« … inflige N dégâts à … » — dégâts d'effet directs (R-10.6), posés en compteurs (R-10.4)."""
    cibles = [c for c in resoudre_cibles(ex, instr) if isinstance(c, CiblePokemon)]
    if not cibles:
        _sans_cible(ex, instr, "aucun Pokémon à qui infliger des dégâts")
        return
    for cible in cibles:
        ex.etat = _maj_pokemon(ex.etat, cible, lambda p: poser_degats(p, instr.nombre))
    _evt(ex, OP_INFLIGER_DEGATS, nombre=len(cibles), degats=instr.nombre)


def prim_melanger(ex: Execution, instr: Instruction) -> None:
    """« Mélangez votre deck » — mélange une zone via le flux d'aléatoire dédié (R-4.1).

    Cas particulier **« mélangez votre main dans votre deck »** (zone ``main`` — type *Judge*,
    *N*, *Cynthia*) : au jeu, on ne mélange jamais sa main *sur place*, la tournure signifie
    toujours « la remettre dans le deck ». La main rejoint la pioche, puis la **pioche entière**
    est mélangée. On ne journalise que le **nombre** de cartes remises, jamais leurs identités : une
    main (surtout celle de l'adversaire) reste cachée — le joueur actif apprend le nombre, pas le
    contenu (confidentialité, lot j-cartes-supporters).
    """
    if instr.cible is not None:
        jid = ex.ctx.joueur if instr.cible.proprietaire == "moi" else ex.ctx.adversaire
        zone = instr.cible.zone
    else:
        jid, zone = ex.ctx.joueur, "pioche"
    joueur = _joueur(ex.etat, jid)
    if zone == "main":
        main = joueur.main
        if not main:
            _sans_cible(ex, instr, "main vide — rien à remettre dans le deck")
            return
        combinee = joueur.pioche + main
        flux = f"dsl:melange:main_dans_pioche:{jid}"
        melangee = ex.rng.melanger(flux, f"DSL mélange main dans pioche de {jid}", combinee)
        ex.etat = _remplacer_joueur(ex.etat, replace(joueur, main=(), pioche=tuple(melangee)))
        _evt(ex, OP_MELANGER, joueur=jid, zone="main_dans_pioche", nombre=len(main))
        return
    cartes = getattr(joueur, zone)
    if not cartes:
        _sans_cible(ex, instr, f"{zone} vide — rien à mélanger")
        return
    flux = f"dsl:melange:{zone}:{jid}"
    melangee = ex.rng.melanger(flux, f"DSL mélange {zone} de {jid}", cartes)
    ex.etat = _remplacer_joueur(ex.etat, replace(joueur, **{zone: tuple(melangee)}))
    _evt(ex, OP_MELANGER, joueur=jid, zone=zone, nombre=len(cartes))


def prim_reveler(ex: Execution, instr: Instruction) -> None:
    """« Montrez … à votre adversaire » — rend des cartes publiques (journal), sans les déplacer."""
    cibles = [c for c in resoudre_cibles(ex, instr) if isinstance(c, CibleCarte)]
    if not cibles:
        _sans_cible(ex, instr, "aucune carte à montrer")
        return
    _evt(ex, OP_REVELER, nombre=len(cibles), refs=sorted(c.ref for c in cibles))


def prim_regarder(ex: Execution, instr: Instruction) -> None:
    """« Regardez les N du dessus » — info **privée** : on journalise le nombre, pas les refs."""
    cibles = [c for c in resoudre_cibles(ex, instr) if isinstance(c, CibleCarte)]
    if not cibles:
        _sans_cible(ex, instr, "aucune carte à regarder")
        return
    # On ne journalise PAS les refs : regarder sa pioche ne doit pas la révéler à l'adversaire.
    _evt(ex, OP_REGARDER, nombre=len(cibles))


def prim_changer_actif(ex: Execution, instr: Instruction) -> None:
    """« Changez le Pokémon Actif … » — échange forcé Actif ↔ banc (R-8.8), sans coût.

    C'est le geste de l'**appât** quand le sélecteur vise l'adversaire (« envoie au front un
    Pokémon du banc adverse » — *Gust of Wind*, *Pokémon Catcher*), et le **changement d'Actif de
    son côté** (type *Switch*) quand il vise ``moi``. Échange **forcé** : il ne consomme **ni** la
    retraite du tour **ni** d'énergie (le DSL ne touche ni ``tour`` ni les énergies), et reste
    valable même si l'Actif échangé est Endormi ou Paralysé (R-16.12) — aucun état n'est donc testé.

    L'Actif qui **descend au banc** est nettoyé de ses états spéciaux (R-8.6), par la **même porte**
    partagée que la retraite, la promotion et l'évolution
    (:func:`~pbm_game.etats.matrice.soigner_etats_speciaux`) : « que garde / que perd un Pokémon qui
    passe au banc » ne doit pas diverger entre ces chemins. Le Pokémon qui **monte** conserve, lui,
    ses états (R-16.12). On **note** le passage dans ``ex.devenus_actifs`` pour que l'appelant
    publie :data:`~pbm_game.effets.evenements.EJ_DEVIENT_ACTIF` sur le bus — sans ce passage, les
    déclencheurs « quand ce Pokémon devient Actif… » seraient oubliés (risque de la fiche).
    """
    cibles = [
        c
        for c in resoudre_cibles(ex, instr)
        if isinstance(c, CiblePokemon) and c.emplacement == "banc"
    ]
    if not cibles:
        _sans_cible(ex, instr, "aucun Pokémon de banc où envoyer l'échange")
        return
    cible = cibles[0]
    joueur = _joueur(ex.etat, cible.joueur)
    if joueur.actif is None:
        _sans_cible(ex, instr, "pas d'Actif à échanger")
        return
    banc = list(joueur.banc)
    idx = next(i for i, p in enumerate(banc) if p.cartes[0].instance_id == cible.identite)
    nouvel_actif = banc.pop(idx)
    ancien_id = joueur.actif.cartes[0].instance_id
    descendu = soigner_etats_speciaux(joueur.actif)  # R-8.6 : l'Actif qui descend perd ses états
    banc.append(descendu)
    ex.etat = _remplacer_joueur(ex.etat, replace(joueur, actif=nouvel_actif, banc=tuple(banc)))
    ex.devenus_actifs.append((cible.joueur, cible.identite))
    _evt(
        ex,
        OP_CHANGER_ACTIF,
        joueur=cible.joueur,
        nouvel_actif=cible.identite,
        ancien_actif=ancien_id,
    )


def prim_poser_etat(ex: Execution, instr: Instruction) -> None:
    """« … est maintenant Empoisonné/… » — pose un état (R-11), un seul d'orientation (R-11.8)."""
    cibles = [c for c in resoudre_cibles(ex, instr) if isinstance(c, CiblePokemon)]
    if not cibles:
        _sans_cible(ex, instr, "aucun Pokémon à qui infliger l'état")
        return
    for cible in cibles:

        def _pose(pok: PokemonEnJeu) -> PokemonEnJeu:
            etats = set(pok.etats_speciaux)
            if instr.etat in ETATS_ORIENTATION:  # un seul état d'orientation à la fois (R-11.8)
                etats -= ETATS_ORIENTATION
            etats.add(instr.etat)
            return replace(pok, etats_speciaux=frozenset(etats))

        ex.etat = _maj_pokemon(ex.etat, cible, _pose)
    _evt(ex, OP_POSER_ETAT, nombre=len(cibles), etat=instr.etat)


def prim_retirer_etat(ex: Execution, instr: Instruction) -> None:
    """« … n'est plus Empoisonné » / « retirez tous les états » — retire un état, ou tous."""
    cibles = [c for c in resoudre_cibles(ex, instr) if isinstance(c, CiblePokemon)]
    if not cibles:
        _sans_cible(ex, instr, "aucun Pokémon dont retirer l'état")
        return
    for cible in cibles:

        def _retire(pok: PokemonEnJeu) -> PokemonEnJeu:
            if instr.etat is None:
                return replace(pok, etats_speciaux=frozenset())
            return replace(pok, etats_speciaux=pok.etats_speciaux - {instr.etat})

        ex.etat = _maj_pokemon(ex.etat, cible, _retire)
    _evt(ex, OP_RETIRER_ETAT, nombre=len(cibles), etat=instr.etat or "tous")


def prim_annuler(ex: Execution, instr: Instruction) -> None:
    """« Prévenez tous les dégâts … » — lève le drapeau « dégâts annulés » que la résolution lit."""
    ex.degats_annules = True
    _evt(ex, OP_ANNULER, annule=True)


#: Règle par défaut d'un verrou, par nom — un :class:`~pbm_game.effets.verrous.Verrou` doit citer
#: sa règle (D9) ; si l'instruction ne la précise pas, on prend celle que le verrou sert.
_REGLE_PAR_VERROU = {
    "pas_de_supporter": "R-5.5",
    "ne_peut_attaquer": "R-5.7",
    "talents_sans_effet": "R-12.3",
    "pas_de_retraite": "R-8",
}


def prim_empecher(ex: Execution, instr: Instruction) -> None:
    """« … ne peut pas attaquer / jouer de Supporter … » — pose un verrou nommé (cf. verrous.py).

    La cible du verrou se déduit du sélecteur : un Pokémon visé → son identité ; sinon le joueur
    propriétaire visé ; aucun sélecteur → verrou **global** (les deux camps). Un sélecteur nommé
    mais vide ne verrouille **pas** tout le monde par défaut : il le **dit** (sans cible).
    """
    cible_id: str | None = None
    if instr.cible is not None:
        cibles = resoudre_cibles(ex, instr)
        if not cibles:
            _sans_cible(ex, instr, "cible du verrou absente — rien n'est verrouillé")
            return
        c0 = cibles[0]
        cible_id = c0.identite if isinstance(c0, CiblePokemon) else c0.joueur
    verrou = Verrou(
        nom=instr.verrou,
        portee=instr.portee,
        source=ex.ctx.source,
        regle=instr.regle or _REGLE_PAR_VERROU.get(instr.verrou, "R-5"),
        cible=cible_id,
        pose_au_tour=ex.etat.tour.numero,
    )
    ex.verrous.append(verrou)
    ex.evenements.append(Evenement(EVT_VERROU_POSE, verrou.en_json()))
    _evt(ex, OP_EMPECHER, verrou=instr.verrou, portee=instr.portee, cible=cible_id)


def _pokemon_par_identite(joueur: Joueur, identite: str) -> PokemonEnJeu:
    if joueur.actif is not None and joueur.actif.cartes[0].instance_id == identite:
        return joueur.actif
    for p in joueur.banc:
        if p.cartes[0].instance_id == identite:
            return p
    raise ValueError(f"Pokémon {identite!r} introuvable chez {joueur.id!r}.")


#: Le registre des primitives **feuilles** (hors structures de contrôle). Une correspondance
#: ``op → fonction`` : ajouter une primitive, c'est l'ajouter au vocabulaire **et** ici.
PRIMITIVES: dict[str, Callable[[Execution, Instruction], None]] = {
    OP_PIOCHER: prim_piocher,
    OP_CHERCHER: prim_chercher,
    OP_DEFAUSSER: prim_defausser,
    OP_ATTACHER: prim_attacher,
    OP_DEPLACER: prim_deplacer,
    OP_SOIGNER: prim_soigner,
    OP_POSER_COMPTEURS: prim_poser_compteurs,
    OP_INFLIGER_DEGATS: prim_infliger_degats,
    OP_MELANGER: prim_melanger,
    OP_REVELER: prim_reveler,
    OP_REGARDER: prim_regarder,
    OP_CHANGER_ACTIF: prim_changer_actif,
    OP_POSER_ETAT: prim_poser_etat,
    OP_RETIRER_ETAT: prim_retirer_etat,
    OP_EMPECHER: prim_empecher,
    OP_ANNULER: prim_annuler,
}

__all__ = [
    "EVT_DSL_PRIMITIVE",
    "PRIMITIVES",
    "restreindre",
    "resoudre_cibles",
]
