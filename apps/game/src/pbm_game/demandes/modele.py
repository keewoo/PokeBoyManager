"""Le **modèle** d'une demande de décision — une donnée dans l'état, jamais une attente de code.

Module **pur** (aucune E/S), comme tout ``pbm_game``. C'est le point où beaucoup de moteurs se
cassent : une carte demande à un joueur — parfois à l'**adversaire**, en plein tour de l'autre —
de choisir quelque chose, et la résolution doit **s'arrêter là** jusqu'à la réponse. Le piège
serait de bloquer un fil d'exécution côté serveur : une partie sur deux resterait figée à la
première déconnexion. Ici, la demande est une **structure sérialisable** portée par l'état : elle
survit à un F5, à un redémarrage, à une reprise de journal.

Six **catégories** de demande (:data:`CATEGORIES`) couvrent ce qu'une carte peut réclamer :

* :data:`CAT_CARTE` — choisir **une** carte parmi un ensemble ;
* :data:`CAT_CARTES` — en choisir **plusieurs** (entre ``minimum`` et ``maximum``) ;
* :data:`CAT_ORDRE` — **ordonner** un ensemble (une permutation de ``options``) ;
* :data:`CAT_OUI_NON` — répondre **oui** ou **non** ;
* :data:`CAT_TYPE` — choisir **un type** (d'énergie, de Pokémon) parmi ``options`` ;
* :data:`CAT_NOMBRE` — choisir **un entier** dans ``[minimum, maximum]``.

Une demande porte **à qui** elle s'adresse (``destinataire`` — y compris l'adversaire), **ce**
qu'elle réclame (``categorie``, ``options``, ``minimum``/``maximum``), si elle est **obligatoire**,
si l'ensemble de choix est **caché** (``ensemble_cache`` : la projection ne montrera alors qu'un
nombre, jamais les identités — anti-triche), une **réponse par défaut** (appliquée à l'expiration)
et une **horloge** (``delai_ms`` / ``temps_restant_ms``). Le moteur étant pur, il ne consulte
**aucune horloge** : le temps est une donnée que l'extérieur fait descendre (lot ``j-timer``).

**D9.** Une catégorie inconnue est refusée (``ValueError``), jamais devinée.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..effets.pile import SourceEffet

# --- Catégories de demande ---------------------------------------------------
CAT_CARTE = "carte"
CAT_CARTES = "cartes"
CAT_ORDRE = "ordre"
CAT_OUI_NON = "oui_non"
CAT_TYPE = "type"
CAT_NOMBRE = "nombre"

#: Les six catégories reconnues. Une demande d'une autre catégorie est refusée (D9).
CATEGORIES: frozenset[str] = frozenset(
    {CAT_CARTE, CAT_CARTES, CAT_ORDRE, CAT_OUI_NON, CAT_TYPE, CAT_NOMBRE}
)

#: Les deux réponses d'une demande oui/non (jamais un booléen nu : un journal se lit sans table).
OUI = "oui"
NON = "non"


@dataclass(frozen=True)
class Reponse:
    """La **réponse** d'un joueur à une demande — autosuffisante et sérialisable.

    * ``demande_id`` — l'identifiant de la demande à laquelle elle répond (appariement strict) ;
    * ``choix`` — les **identifiants d'option** retenus, en valeurs JSON natives :

      - :data:`CAT_CARTE` / :data:`CAT_TYPE` : un seul id ;
      - :data:`CAT_CARTES` : de ``minimum`` à ``maximum`` ids, sans doublon ;
      - :data:`CAT_ORDRE` : **tous** les ids de ``options``, dans l'ordre choisi (une permutation) ;
      - :data:`CAT_OUI_NON` : ``("oui",)`` ou ``("non",)`` ;
      - :data:`CAT_NOMBRE` : ``(str(n),)`` avec ``minimum ≤ n ≤ maximum``.

    Un ``choix`` **vide** ``()`` est l'**abandon** d'un effet facultatif (``obligatoire = False``) :
    « je renonce à ce que cette carte me propose ». Il est refusé pour une demande obligatoire.
    """

    demande_id: str
    choix: tuple[str, ...] = ()

    def en_json(self) -> dict:
        return {"demande_id": self.demande_id, "choix": list(self.choix)}

    @staticmethod
    def depuis_json(donnees: object) -> Reponse:
        if not isinstance(donnees, dict):
            raise ValueError("Une réponse doit être un mapping {demande_id, choix}.")
        did = donnees.get("demande_id")
        if not isinstance(did, str) or not did:
            raise ValueError("Réponse : « demande_id » manquant ou invalide.")
        choix = donnees.get("choix", [])
        if not isinstance(choix, list) or not all(isinstance(c, str) for c in choix):
            raise ValueError("Réponse : « choix » doit être une liste de chaînes.")
        return Reponse(demande_id=did, choix=tuple(choix))


@dataclass(frozen=True)
class DemandeDecision:
    """Une **demande de décision** en attente — portée par l'état, donc sérialisée, donc reprise.

    Voir l'en-tête du module pour le sens de chaque champ. ``id`` est attribué par le
    :class:`~pbm_game.demandes.gestionnaire.Gestionnaire` au moment où la demande est levée, de
    façon **déterministe** (``d0``, ``d1``…, dans l'ordre des décisions de la résolution) : c'est ce
    qui permet, à la reprise, d'apparier une réponse enregistrée à la bonne décision quand le script
    est re-déroulé.
    """

    destinataire: str
    categorie: str
    source: SourceEffet
    regle: str
    libelle: str
    options: tuple[str, ...] = ()
    minimum: int = 1
    maximum: int = 1
    obligatoire: bool = True
    ensemble_cache: bool = False
    delai_ms: int | None = None
    temps_restant_ms: int | None = None
    id: str = ""

    def __post_init__(self) -> None:
        if self.categorie not in CATEGORIES:
            raise ValueError(
                f"Catégorie de demande inconnue : {self.categorie!r} — jamais devinée (D9). "
                f"Connues : {sorted(CATEGORIES)}."
            )
        if not self.destinataire:
            raise ValueError("Une demande doit nommer son destinataire (le joueur qui décide).")
        if not isinstance(self.regle, str) or not self.regle.strip():
            raise ValueError("Une demande doit citer la règle R-x.y qu'elle sert (D9).")
        if not isinstance(self.libelle, str) or not self.libelle.strip():
            raise ValueError("Une demande doit porter un libellé lisible (journal, interface).")
        if self.minimum < 0 or self.maximum < self.minimum:
            raise ValueError(
                f"Bornes de demande incohérentes : minimum={self.minimum}, maximum={self.maximum}."
            )
        for cle, valeur in (
            ("delai_ms", self.delai_ms),
            ("temps_restant_ms", self.temps_restant_ms),
        ):
            if valeur is not None and (
                not isinstance(valeur, int) or isinstance(valeur, bool) or valeur < 0
            ):
                raise ValueError(f"Demande : « {cle} » doit être un entier ≥ 0 ou None.")

    def avec_id(self, identifiant: str) -> DemandeDecision:
        """Renvoie une copie portant ``id`` (attribué par le gestionnaire au moment de lever)."""
        return replace(self, id=identifiant)

    def avec_temps_restant(self, ms: int | None) -> DemandeDecision:
        """Renvoie une copie dont l'horloge restante vaut ``ms`` — posée par l'extérieur (j-timer).

        Le moteur ne décompte rien lui-même (il est pur, sans horloge) : l'adaptateur qui tient
        le temps réel décrémente ``temps_restant_ms`` et, à zéro, appelle l'expiration. La valeur
        vit dans l'état, donc une reprise après coupure retrouve **le temps restant**, pas le délai
        initial remis à neuf.
        """
        return replace(self, temps_restant_ms=ms)

    def en_json(self) -> dict:
        return {
            "id": self.id,
            "destinataire": self.destinataire,
            "categorie": self.categorie,
            "source": self.source.en_json(),
            "regle": self.regle,
            "libelle": self.libelle,
            "options": list(self.options),
            "minimum": self.minimum,
            "maximum": self.maximum,
            "obligatoire": self.obligatoire,
            "ensemble_cache": self.ensemble_cache,
            "delai_ms": self.delai_ms,
            "temps_restant_ms": self.temps_restant_ms,
        }

    @staticmethod
    def depuis_json(donnees: object) -> DemandeDecision:
        if not isinstance(donnees, dict):
            raise ValueError("Une demande doit être un mapping.")
        options = donnees.get("options", [])
        if not isinstance(options, list) or not all(isinstance(o, str) for o in options):
            raise ValueError("Demande : « options » doit être une liste de chaînes.")
        return DemandeDecision(
            destinataire=donnees.get("destinataire", ""),
            categorie=donnees.get("categorie", ""),
            source=SourceEffet.depuis_json(donnees.get("source")),
            regle=donnees.get("regle", ""),
            libelle=donnees.get("libelle", ""),
            options=tuple(options),
            minimum=donnees.get("minimum", 1),
            maximum=donnees.get("maximum", 1),
            obligatoire=donnees.get("obligatoire", True),
            ensemble_cache=donnees.get("ensemble_cache", False),
            delai_ms=donnees.get("delai_ms"),
            temps_restant_ms=donnees.get("temps_restant_ms"),
            id=donnees.get("id", ""),
        )


def valider_reponse(demande: DemandeDecision, reponse: Reponse) -> None:
    """Vérifie qu'une réponse est **recevable** pour sa demande, ou lève ``ValueError``.

    Aucun repli silencieux : une réponse hors-ensemble, en doublon, de mauvaise cardinalité ou
    sur la mauvaise demande est **refusée** (le serveur fait autorité, R-1 du jeu). C'est ce qui
    garde l'anti-triche : un client ne peut pas « répondre » un id qu'il n'a pas le droit de jouer.
    """
    if reponse.demande_id != demande.id:
        raise ValueError(
            f"Réponse à la mauvaise demande : {reponse.demande_id!r} ≠ {demande.id!r}."
        )
    choix = reponse.choix
    if choix == ():
        if demande.obligatoire:
            raise ValueError(
                f"Demande « {demande.id} » obligatoire : l'abandon (réponse vide) est refusé."
            )
        return  # abandon légitime d'un effet facultatif
    if len(set(choix)) != len(choix):
        raise ValueError(f"Demande « {demande.id} » : réponse avec des doublons ({choix}).")

    cat = demande.categorie
    if cat in (CAT_CARTE, CAT_TYPE):
        if len(choix) != 1 or choix[0] not in demande.options:
            raise ValueError(
                f"Demande « {demande.id} » ({cat}) : attendu un seul id de {demande.options}, "
                f"reçu {choix}."
            )
    elif cat == CAT_CARTES:
        if not (demande.minimum <= len(choix) <= demande.maximum):
            raise ValueError(
                f"Demande « {demande.id} » : {len(choix)} choix hors de "
                f"[{demande.minimum}, {demande.maximum}]."
            )
        hors = [c for c in choix if c not in demande.options]
        if hors:
            raise ValueError(f"Demande « {demande.id} » : ids hors de l'ensemble ({hors}).")
    elif cat == CAT_ORDRE:
        if sorted(choix) != sorted(demande.options):
            raise ValueError(
                f"Demande « {demande.id} » (ordre) : la réponse doit être une permutation de "
                f"{demande.options}, reçu {choix}."
            )
    elif cat == CAT_OUI_NON:
        if len(choix) != 1 or choix[0] not in (OUI, NON):
            raise ValueError(f"Demande « {demande.id} » (oui/non) : attendu « oui » ou « non ».")
    elif cat == CAT_NOMBRE:
        if len(choix) != 1:
            raise ValueError(f"Demande « {demande.id} » (nombre) : attendu un seul entier.")
        try:
            n = int(choix[0])
        except ValueError as exc:
            raise ValueError(
                f"Demande « {demande.id} » (nombre) : « {choix[0]} » n'est pas un entier."
            ) from exc
        if not (demande.minimum <= n <= demande.maximum):
            raise ValueError(
                f"Demande « {demande.id} » (nombre) : {n} hors de "
                f"[{demande.minimum}, {demande.maximum}]."
            )
    else:  # pragma: no cover - CATEGORIES garde déjà cette porte fermée
        raise ValueError(f"Catégorie de demande non gérée à la validation : {cat!r}.")


def reponse_par_defaut(demande: DemandeDecision) -> Reponse:
    """La réponse appliquée **à l'expiration du délai** (le joueur n'a pas répondu à temps).

    Règle (mission du lot) : **le premier choix valide**, ou **l'abandon** si l'effet est
    facultatif. Elle est **déterministe** (donc rejouable) et par construction **recevable** —
    :func:`valider_reponse` l'accepte toujours. Concrètement :

    * facultatif → abandon (``choix`` vide) : on renonce à ce que la carte proposait ;
    * :data:`CAT_CARTE` / :data:`CAT_TYPE` / :data:`CAT_OUI_NON` → la **première** option ;
    * :data:`CAT_CARTES` → les ``minimum`` premières options ;
    * :data:`CAT_ORDRE` → l'ordre **identité** (les options telles quelles) ;
    * :data:`CAT_NOMBRE` → la borne ``minimum`` (le plus petit entier légal).
    """
    if not demande.obligatoire:
        return Reponse(demande.id, ())
    cat = demande.categorie
    if cat in (CAT_CARTE, CAT_TYPE):
        choix: tuple[str, ...] = (demande.options[0],) if demande.options else ()
    elif cat == CAT_CARTES:
        choix = tuple(demande.options[: demande.minimum])
    elif cat == CAT_ORDRE:
        choix = tuple(demande.options)
    elif cat == CAT_OUI_NON:
        choix = (demande.options[0] if demande.options else NON,)
    elif cat == CAT_NOMBRE:
        choix = (str(demande.minimum),)
    else:  # pragma: no cover
        raise ValueError(f"Catégorie sans réponse par défaut : {cat!r}.")
    return Reponse(demande.id, choix)


__all__ = [
    "CAT_CARTE",
    "CAT_CARTES",
    "CAT_ORDRE",
    "CAT_OUI_NON",
    "CAT_TYPE",
    "CAT_NOMBRE",
    "CATEGORIES",
    "OUI",
    "NON",
    "Reponse",
    "DemandeDecision",
    "valider_reponse",
    "reponse_par_defaut",
]
