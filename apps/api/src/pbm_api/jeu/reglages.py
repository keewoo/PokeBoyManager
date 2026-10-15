"""Le vocabulaire des réglages **globaux** du jeu : quelles clés existent, et ce qu'on peut y
mettre (lot `j-classement-prive`, DJ6).

Module **pur** : aucune base, aucune requête, aucun effet. Il ne dit que *ce qui est permis* — la
lecture et l'écriture vivent dans :mod:`pbm_api.jeu.reglages_service`, la table dans
:class:`pbm_api.models.jeu_reglages.JeuReglage`, et la commande d'administration dans
:mod:`pbm_api.admin`.

**Pourquoi un registre plutôt qu'une table clé/valeur libre.** Un réglage libre se trompe en
silence : `python -m pbm_api.admin set-reglage-jeu classement_active oui` (un « e » de trop)
écrirait une ligne que personne ne lit jamais, et JF croirait avoir activé le classement. Ici la
clé est refusée, avec la liste de celles qui existent. C'est la même règle que partout dans ce
dépôt : un réglage qui n'a pas d'effet doit le **dire**, pas se taire.

**Les trois clés d'aujourd'hui** — les deux premières posées par `j-classement-prive`, la
troisième par `j-profil-jeu` :

* ``classement_actif`` — le classement privé est-il calculé et montré ? Défaut **non**, parce que
  DJ6 le veut « en option, activable par JF » : un lot ne s'auto-active pas sur une décision qui
  dit « en option ». C'est aussi la parade au risque social nommé par le plan (« ce qui peut
  transformer un jeu entre frères en dispute ») — tant que JF n'a rien décidé, rien ne s'affiche.
* ``classement_bareme`` — **quelle** formule compte les points, parmi
  :data:`pbm_api.jeu.classement.BAREMES`. C'est ce qui rend la formule remplaçable sans toucher au
  code (mission du lot : « la formule n'est pas dans le code de clôture »).

* ``badges_actifs`` — la **vitrine** des badges est-elle montrée ? Défaut **non**, pour la même
  raison que le classement : DJ6 dit « en option, activables par JF ». ⚠️ Ce réglage gouverne
  l'**affichage**, pas l'attribution : les badges continuent d'être écrits à la clôture même quand
  il est à ``non``, sinon allumer la vitrine six mois plus tard donnerait une vitrine vide et
  « K.O. en un coup » — qui se lit dans le journal, purgé à trente jours — serait perdu à jamais.
  Le raisonnement complet est dans :mod:`pbm_api.jeu.badges_service`.

Ajouté par `j-profil-jeu` **sans migration**, comme annoncé : c'est tout l'intérêt du registre.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pbm_api.jeu.classement import BAREME_DEFAUT, BAREMES

#: Valeur d'un réglage booléen quand il est actif. On écrit « oui »/« non » plutôt que
#: « true »/« false » parce qu'un humain tape cette valeur à la main dans une commande sur le
#: serveur, et qu'un réglage mal orthographié est refusé plutôt qu'interprété.
OUI = "oui"
#: Valeur d'un réglage booléen quand il est inactif.
NON = "non"

#: Les deux valeurs d'un booléen, et aucune autre (« 1 », « true », « yes » sont refusés : accepter
#: dix orthographes, c'est accepter une faute de frappe qui ressemble à un succès).
BOOLEENS: tuple[str, ...] = (OUI, NON)

#: Clé : le classement privé est-il actif ? (DJ6 — « activable par JF »)
CLE_CLASSEMENT_ACTIF = "classement_actif"
#: Clé : quel barème de points le classement applique.
CLE_CLASSEMENT_BAREME = "classement_bareme"
#: Clé : la vitrine des badges est-elle montrée ? (DJ6 — « activables par JF »). Gouverne
#: l'affichage, **pas** l'attribution (voir l'en-tête du module).
CLE_BADGES_ACTIFS = "badges_actifs"


@dataclass(frozen=True)
class Reglage:
    """La déclaration d'un réglage global : son défaut, ses valeurs possibles, et à quoi il sert.

    ``valeurs`` est volontairement **fermé** : un réglage dont les valeurs ne sont pas énumérables
    n'a pas sa place ici (il irait en variable d'environnement, comme un plafond numérique). Les
    deux réglages de DJ6 sont des choix, pas des nombres.

    ``libelle`` est affiché par la commande d'administration : JF doit pouvoir lire ce qu'il change
    sans ouvrir le code.
    """

    cle: str
    defaut: str
    valeurs: tuple[str, ...]
    libelle: str


#: Les réglages globaux déclarés. Toute clé absente de ce dictionnaire est **inconnue** : ni écrite,
#: ni lue. Ajouter un réglage, c'est ajouter une entrée ici — jamais une migration.
REGLAGES: Mapping[str, Reglage] = {
    CLE_CLASSEMENT_ACTIF: Reglage(
        cle=CLE_CLASSEMENT_ACTIF,
        # Défaut « non » : DJ6 dit « en option, activable par JF ». S'activer tout seul serait
        # décider à sa place.
        defaut=NON,
        valeurs=BOOLEENS,
        libelle="Classement privé entre comptes invités : calculé et affiché ?",
    ),
    CLE_CLASSEMENT_BAREME: Reglage(
        cle=CLE_CLASSEMENT_BAREME,
        defaut=BAREME_DEFAUT,
        # Les valeurs possibles sont DÉRIVÉES des barèmes du module de calcul : ajouter un barème
        # le rend choisissable sans qu'on ait à penser à l'inscrire ici (une liste recopiée finit
        # toujours par mentir).
        valeurs=tuple(sorted(BAREMES)),
        libelle="Barème de points du classement",
    ),
    CLE_BADGES_ACTIFS: Reglage(
        cle=CLE_BADGES_ACTIFS,
        # Défaut « non », comme le classement : DJ6 veut les badges « en option ». Les badges sont
        # néanmoins ATTRIBUÉS pendant ce temps — ce réglage ferme la vitrine, il n'efface pas
        # l'histoire (voir :mod:`pbm_api.jeu.badges_service`).
        defaut=NON,
        valeurs=BOOLEENS,
        libelle="Badges : la vitrine du profil de joueur les montre-t-elle ?",
    ),
}


class ReglageInconnu(KeyError):
    """La clé demandée n'est pas déclarée dans :data:`REGLAGES` — jamais écrite, jamais lue.

    Levée plutôt que tolérée : c'est tout l'intérêt du registre. Son message nomme les clés
    existantes, pour que la faute de frappe se corrige sans aller lire le code.
    """

    def __init__(self, cle: str) -> None:
        self.cle = cle
        super().__init__(
            f"Réglage inconnu : {cle!r}. "
            f"Clés déclarées : {', '.join(sorted(REGLAGES))}."
        )

    def __str__(self) -> str:
        # `KeyError.__str__` met le message entre guillemets (`'…'`) : inutile dans une sortie de
        # commande destinée à être lue.
        return self.args[0] if self.args else ""


class ValeurInvalide(ValueError):
    """La valeur proposée n'est pas dans les valeurs possibles du réglage."""


def declaration(cle: str) -> Reglage:
    """La déclaration d'un réglage, ou lève :class:`ReglageInconnu`."""
    try:
        return REGLAGES[cle]
    except KeyError:
        raise ReglageInconnu(cle) from None


def valider(cle: str, valeur: str) -> str:
    """Contrôle qu'on peut écrire ``valeur`` sous ``cle``, et rend la valeur normalisée.

    Normalise la casse et les espaces (``" OUI "`` → ``"oui"``) parce que la valeur est tapée à la
    main sur un serveur ; refuse tout le reste. Lève :class:`ReglageInconnu` sur une clé non
    déclarée, :class:`ValeurInvalide` sur une valeur hors vocabulaire — jamais de silence.
    """
    decl = declaration(cle)
    normalisee = valeur.strip().lower()
    if normalisee not in decl.valeurs:
        raise ValeurInvalide(
            f"Valeur {valeur!r} refusée pour {cle!r}. Valeurs possibles : "
            f"{', '.join(decl.valeurs)}."
        )
    return normalisee


def interpreter(cle: str, valeur: str | None) -> str:
    """La valeur **effective** d'un réglage : celle en base si elle est valide, sinon le défaut.

    ``valeur=None`` est le cas normal d'un réglage jamais touché (aucune ligne en base) : on rend le
    défaut déclaré. Une valeur *illisible* (écrite en SQL à la main, ou survivante d'un barème
    supprimé depuis) rend aussi le défaut : le classement continue de fonctionner sur une formule
    connue plutôt que de rendre une erreur 500 à un joueur. Ce n'est pas un repli silencieux — la
    commande ``lire-reglages-jeu`` montre la valeur stockée **et** la valeur effective, donc l'écart
    est visible à qui le cherche.
    """
    decl = declaration(cle)
    if valeur is None:
        return decl.defaut
    normalisee = valeur.strip().lower()
    return normalisee if normalisee in decl.valeurs else decl.defaut


def est_actif(valeur_effective: str) -> bool:
    """Traduit la valeur effective d'un réglage booléen en booléen Python."""
    return valeur_effective == OUI


__all__ = [
    "BOOLEENS",
    "CLE_BADGES_ACTIFS",
    "CLE_CLASSEMENT_ACTIF",
    "CLE_CLASSEMENT_BAREME",
    "NON",
    "OUI",
    "REGLAGES",
    "Reglage",
    "ReglageInconnu",
    "ValeurInvalide",
    "declaration",
    "est_actif",
    "interpreter",
    "valider",
]
