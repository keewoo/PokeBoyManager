"""Les **verrous nommés** — « ce tour, tel coup est interdit », et leur portée.

Module **pur** (aucune E/S). Un verrou est une **interdiction nommée** qu'une carte pose :
« pas de Supporter ce tour » (type *Marnie*/*Judge* inversé, ou un talent adverse), « ce
Pokémon ne peut pas attaquer au prochain tour », « les talents sont sans effet » (type
*Garbodor*). Sans eux, ces règles seraient codées en dur dans le socle de la machine à tour —
et, dit la fiche, *le socle pourrirait* dès la première carte qui dit « votre adversaire ne
peut pas ».

Un verrou porte une **portée** qui dit quand il tombe :

* :data:`PORTEE_CE_TOUR` — jusqu'à la fin du tour courant (expire au Checkup, R-12.5) ;
* :data:`PORTEE_PROCHAIN_TOUR` — pèse sur le **prochain** tour de sa cible, puis tombe ;
* :data:`PORTEE_TANT_QUE_ACTIF` — tant que le Pokémon source reste l'Actif ;
* :data:`PORTEE_TANT_QUE_STADE` — tant que le Stade source reste en jeu ;
* :data:`PORTEE_TANT_QUE_EN_JEU` — tant que le Pokémon source reste en jeu (banc compris).

Les verrous « ce tour » et « prochain tour » **expirent au Checkup** et chaque levée est
**journalisée** (:data:`EVT_VERROU_LEVE`) — un verrou qui disparaîtrait en silence rendrait un
coup interdit « sans raison visible », exactement le reproche fait aux replis muets. Les
verrous liés à une source (Actif, Stade, en jeu) sont *dérivés* comme les effets continus :
ils tombent quand leur source quitte sa place, sans qu'on ait à les retirer.

**Périmètre du lot.** Ce module livre la **structure** interrogeable (poser, lever, demander
« ce coup est-il verrouillé ? ») et son expiration. Le branchement sur les gardes réelles —
le refus d'un Supporter sous :data:`VERROU_PAS_DE_SUPPORTER` (R-5.5), d'une attaque sous
:data:`VERROU_NE_PEUT_ATTAQUER` — appartient aux lots de cartes (``j-cartes-supporters``,
``j-cartes-attaques-effets``), qui consultent :meth:`JeuDeVerrous.est_verrouille`.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..journal.modele import Evenement
from .pile import SourceEffet

# --- Verrous nommés (les trois de la fiche, et ceux que les lots de cartes ajouteront) ---
#: « Pas de Supporter ce tour » (R-5.5 : un Supporter par tour, qu'un effet peut interdire).
VERROU_PAS_DE_SUPPORTER = "pas_de_supporter"
#: « Ce Pokémon ne peut pas attaquer » (R-5.7, bloqué par un effet).
VERROU_NE_PEUT_ATTAQUER = "ne_peut_attaquer"
#: « Les talents sont sans effet » (type *Garbodor* — R-12.3, un talent qui éteint les talents).
VERROU_TALENTS_SANS_EFFET = "talents_sans_effet"
#: « Pas de retraite ce tour » (R-8, bloqué par un effet — distinct de Sommeil/Paralysie R-8.4).
VERROU_PAS_DE_RETRAITE = "pas_de_retraite"

#: Les verrous nommés reconnus. Un nom hors de cette liste est refusé (D9) : un verrou non
#: prévu n'est pas inventé, il est ajouté ici avec la règle qu'il sert.
VERROUS: frozenset[str] = frozenset(
    {
        VERROU_PAS_DE_SUPPORTER,
        VERROU_NE_PEUT_ATTAQUER,
        VERROU_TALENTS_SANS_EFFET,
        VERROU_PAS_DE_RETRAITE,
    }
)

# --- Portées ------------------------------------------------------------------
PORTEE_CE_TOUR = "ce_tour"
PORTEE_PROCHAIN_TOUR = "prochain_tour"
PORTEE_TANT_QUE_ACTIF = "tant_que_actif"
PORTEE_TANT_QUE_STADE = "tant_que_stade"
PORTEE_TANT_QUE_EN_JEU = "tant_que_en_jeu"

PORTEES_VERROU: frozenset[str] = frozenset(
    {
        PORTEE_CE_TOUR,
        PORTEE_PROCHAIN_TOUR,
        PORTEE_TANT_QUE_ACTIF,
        PORTEE_TANT_QUE_STADE,
        PORTEE_TANT_QUE_EN_JEU,
    }
)

#: Les portées qui **expirent au Checkup** (R-12.5), par opposition à celles dérivées d'une
#: source en jeu (Actif, Stade, en jeu), qui tombent avec leur source.
PORTEES_A_EXPIRATION: frozenset[str] = frozenset({PORTEE_CE_TOUR, PORTEE_PROCHAIN_TOUR})

#: Un verrou a été **levé** (expiré) — journalisé pour qu'il ne disparaisse jamais en silence.
EVT_VERROU_LEVE = "verrou_leve"
#: Un verrou a été **posé** par une carte — porte le nom, la portée et la source (journal).
EVT_VERROU_POSE = "verrou_pose"


@dataclass(frozen=True)
class Verrou:
    """Une interdiction nommée, posée par une carte, avec sa portée et sa cible.

    * ``nom`` — un des :data:`VERROUS` ;
    * ``portee`` — une des :data:`PORTEES_VERROU` ;
    * ``source`` — la carte responsable (:class:`SourceEffet`), pour que le refus la **nomme** ;
    * ``regle`` — l'identifiant ``R-x.y`` que le verrou sert ;
    * ``cible`` — le joueur ou le Pokémon visé (``None`` = s'applique globalement, p. ex. un
      Stade qui verrouille les deux camps) ;
    * ``pose_au_tour`` — le numéro de tour où il a été posé (pour l'expiration « ce tour » /
      « prochain tour »).
    """

    nom: str
    portee: str
    source: SourceEffet
    regle: str
    cible: str | None = None
    pose_au_tour: int | None = None

    def __post_init__(self) -> None:
        if self.nom not in VERROUS:
            raise ValueError(
                f"Verrou inconnu : {self.nom!r} — un verrou non prévu n'est pas inventé (D9). "
                f"Connus : {sorted(VERROUS)}."
            )
        if self.portee not in PORTEES_VERROU:
            raise ValueError(
                f"Portée de verrou inconnue : {self.portee!r} — jamais approximée (D9). "
                f"Connues : {sorted(PORTEES_VERROU)}."
            )
        if not isinstance(self.regle, str) or not self.regle.strip():
            raise ValueError("Un verrou doit citer la règle R-x.y qu'il sert (D9).")

    def en_json(self) -> dict:
        return {
            "nom": self.nom,
            "portee": self.portee,
            "source": self.source.en_json(),
            "regle": self.regle,
            "cible": self.cible,
            "pose_au_tour": self.pose_au_tour,
        }

    @staticmethod
    def depuis_json(donnees: object) -> Verrou:
        """Relit un verrou produit par :meth:`en_json` — pour reprendre un état après un F5.

        La validation de :meth:`__post_init__` **mord** ici (nom/portée hors liste, règle vide) :
        un verrou sérialisé incohérent est une panne, jamais chargé « au mieux ».
        """
        if not isinstance(donnees, dict):
            raise ValueError("Un verrou doit être un mapping {nom, portee, source, regle, …}.")
        pose = donnees.get("pose_au_tour")
        if pose is not None and (not isinstance(pose, int) or isinstance(pose, bool)):
            raise ValueError("Verrou : « pose_au_tour » doit être un entier ou None.")
        cible = donnees.get("cible")
        if cible is not None and not isinstance(cible, str):
            raise ValueError("Verrou : « cible » doit être une chaîne ou None.")
        return Verrou(
            nom=donnees.get("nom", ""),
            portee=donnees.get("portee", ""),
            source=SourceEffet.depuis_json(donnees.get("source")),
            regle=donnees.get("regle", ""),
            cible=cible,
            pose_au_tour=pose,
        )


@dataclass(frozen=True)
class JeuDeVerrous:
    """La collection **immuable** des verrous en vigueur — interrogeable et sérialisable.

    ``poser`` et ``retirer`` renvoient un nouveau jeu (jamais de mutation).
    :meth:`est_verrouille` est ce que les gardes des lots de cartes consultent avant d'autoriser
    un coup. :meth:`expirer_au_checkup` tombe les verrous « ce tour » / « prochain tour » et
    journalise chaque levée.
    """

    verrous: tuple[Verrou, ...] = ()

    def poser(self, verrou: Verrou) -> tuple[JeuDeVerrous, Evenement]:
        """Pose ``verrou`` et renvoie ``(nouveau_jeu, evenement_pose)`` (toujours journalisé)."""
        if not isinstance(verrou, Verrou):
            raise TypeError(f"On ne pose qu'un Verrou, reçu {type(verrou).__name__}.")
        evt = Evenement(EVT_VERROU_POSE, verrou.en_json())
        return JeuDeVerrous(self.verrous + (verrou,)), evt

    def est_verrouille(self, nom: str, *, cible: str | None = None) -> bool:
        """Y a-t-il un verrou ``nom`` en vigueur pour ``cible`` (ou global) ?

        Un verrou global (``cible=None``) frappe tout le monde ; un verrou ciblé ne frappe que
        sa cible. Lève ``ValueError`` sur un nom hors de :data:`VERROUS` (D9 : on ne demande pas
        un verrou qui n'existe pas).
        """
        if nom not in VERROUS:
            raise ValueError(f"Verrou inconnu demandé : {nom!r}. Connus : {sorted(VERROUS)}.")
        for v in self.verrous:
            if v.nom != nom:
                continue
            if v.cible is None or cible is None or v.cible == cible:
                return True
        return False

    def source_du_verrou(self, nom: str, *, cible: str | None = None) -> SourceEffet | None:
        """La source du premier verrou ``nom`` en vigueur pour ``cible`` — pour nommer le refus."""
        for v in self.verrous:
            if v.nom == nom and (v.cible is None or cible is None or v.cible == cible):
                return v.source
        return None

    def retirer(self, verrou: Verrou) -> JeuDeVerrous:
        """Retire une occurrence de ``verrou`` (p. ex. sa source a quitté le jeu)."""
        restants = list(self.verrous)
        restants.remove(verrou)
        return JeuDeVerrous(tuple(restants))

    def expirer_au_checkup(self, numero_tour: int) -> tuple[JeuDeVerrous, list[Evenement]]:
        """Tombe les verrous à expiration (R-12.5) et journalise chaque levée.

        Un :data:`PORTEE_CE_TOUR` tombe dès que le tour où il a été posé s'achève ; un
        :data:`PORTEE_PROCHAIN_TOUR` pèse sur le tour suivant puis tombe au Checkup de celui-ci.
        Les verrous dérivés d'une source (Actif, Stade, en jeu) ne sont **pas** touchés ici :
        ils tombent avec leur source (voir :meth:`retirer_sources_absentes`). Jamais un retrait
        muet : chaque levée produit un :data:`EVT_VERROU_LEVE`.
        """
        gardes: list[Verrou] = []
        leves: list[Evenement] = []
        for v in self.verrous:
            if v.portee == PORTEE_CE_TOUR and (
                v.pose_au_tour is None or numero_tour >= v.pose_au_tour
            ):
                leves.append(Evenement(EVT_VERROU_LEVE, {**v.en_json(), "au_tour": numero_tour}))
            elif v.portee == PORTEE_PROCHAIN_TOUR and (
                v.pose_au_tour is not None and numero_tour > v.pose_au_tour
            ):
                leves.append(Evenement(EVT_VERROU_LEVE, {**v.en_json(), "au_tour": numero_tour}))
            else:
                gardes.append(v)
        return JeuDeVerrous(tuple(gardes)), leves

    def expirer_au_checkup_oriente(
        self, numero_tour: int, *, joueur_actif: str, proprietaire_de
    ) -> tuple[JeuDeVerrous, list[Evenement]]:
        """Expire les verrous « ce tour » / « prochain tour » **en tenant compte du propriétaire**.

        La différence avec :meth:`expirer_au_checkup` (pur, aveugle au propriétaire) : un verrou
        « prochain tour » pèse sur le prochain tour **de sa cible**, pas sur le tour global suivant.
        Comme les tours alternent, le prochain tour de la cible n'est pas toujours le tour N+1 :
        un auto-blocage posé par Alice (« ce Pokémon ne peut pas attaquer au prochain tour ») doit
        survivre au tour de Bob et ne tomber qu'au Checkup du **prochain tour d'Alice**. La règle :

        * un :data:`PORTEE_CE_TOUR` tombe au Checkup du tour où il a été posé (``numero_tour >=
          pose_au_tour``, et c'est alors le tour de son propriétaire) ;
        * un :data:`PORTEE_PROCHAIN_TOUR` tombe au premier Checkup **du propriétaire de sa cible**
          postérieur à la pose (``joueur_actif == proprietaire_de(cible)`` et ``numero_tour >
          pose_au_tour``) — donc il a bien pesé sur un tour entier de la cible avant de tomber.

        ``proprietaire_de(cible)`` renvoie l'identifiant du joueur à qui appartient la cible du
        verrou (le joueur lui-même, ou le propriétaire du Pokémon visé), ou ``None`` si la cible est
        **globale** (``cible is None``) ou introuvable — un verrou global « prochain tour » retombe
        alors sur la règle aveugle (``numero_tour > pose_au_tour``), faute de propriétaire à qui
        rattacher le tour. Chaque levée est journalisée (:data:`EVT_VERROU_LEVE`), jamais muette.
        """
        gardes: list[Verrou] = []
        leves: list[Evenement] = []
        for v in self.verrous:
            proprio = proprietaire_de(v.cible) if v.cible is not None else None
            if v.portee == PORTEE_CE_TOUR and (
                v.pose_au_tour is None or numero_tour >= v.pose_au_tour
            ):
                leves.append(Evenement(EVT_VERROU_LEVE, {**v.en_json(), "au_tour": numero_tour}))
            elif (
                v.portee == PORTEE_PROCHAIN_TOUR
                and v.pose_au_tour is not None
                and (numero_tour > v.pose_au_tour and (proprio is None or proprio == joueur_actif))
            ):
                leves.append(Evenement(EVT_VERROU_LEVE, {**v.en_json(), "au_tour": numero_tour}))
            else:
                gardes.append(v)
        return JeuDeVerrous(tuple(gardes)), leves

    def en_json(self) -> list[dict]:
        """Les verrous en vigueur en liste de ``dict`` JSON-natifs (ordre de pose conservé)."""
        return [v.en_json() for v in self.verrous]

    @staticmethod
    def depuis_json(donnees: object) -> JeuDeVerrous:
        """Relit un jeu de verrous produit par :meth:`en_json` (ou lève ``ValueError``)."""
        if not isinstance(donnees, list):
            raise ValueError("Les verrous doivent être une liste de verrous (jeu de verrous).")
        return JeuDeVerrous(tuple(Verrou.depuis_json(v) for v in donnees))

    def retirer_sources_absentes(
        self, refs_en_jeu: frozenset[str]
    ) -> tuple[JeuDeVerrous, list[Evenement]]:
        """Tombe les verrous dérivés d'une source qui a quitté le jeu (Actif, Stade, en jeu).

        ``refs_en_jeu`` est l'ensemble des ``instance_id`` encore présents (Pokémon, Stade). Un
        verrou de portée liée dont la source n'y est plus est levé et **journalisé** — comme un
        effet continu dont la source part, mais rendu explicite côté verrou pour que le journal
        garde la trace.
        """
        gardes: list[Verrou] = []
        leves: list[Evenement] = []
        liees = {PORTEE_TANT_QUE_ACTIF, PORTEE_TANT_QUE_STADE, PORTEE_TANT_QUE_EN_JEU}
        for v in self.verrous:
            iid = v.source.instance_id
            if v.portee in liees and iid is not None and iid not in refs_en_jeu:
                leves.append(Evenement(EVT_VERROU_LEVE, {**v.en_json(), "source_absente": True}))
            else:
                gardes.append(v)
        return JeuDeVerrous(tuple(gardes)), leves


#: Un jeu de verrous **vide** — l'état de départ d'une partie (aucun verrou posé).
VERROUS_VIDES = JeuDeVerrous()


__all__ = [
    "VERROU_PAS_DE_SUPPORTER",
    "VERROU_NE_PEUT_ATTAQUER",
    "VERROU_TALENTS_SANS_EFFET",
    "VERROU_PAS_DE_RETRAITE",
    "VERROUS",
    "PORTEE_CE_TOUR",
    "PORTEE_PROCHAIN_TOUR",
    "PORTEE_TANT_QUE_ACTIF",
    "PORTEE_TANT_QUE_STADE",
    "PORTEE_TANT_QUE_EN_JEU",
    "PORTEES_VERROU",
    "PORTEES_A_EXPIRATION",
    "EVT_VERROU_LEVE",
    "EVT_VERROU_POSE",
    "Verrou",
    "JeuDeVerrous",
    "VERROUS_VIDES",
]
