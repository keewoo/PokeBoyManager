"""Le **grand livre** de l'assistance — dépense cumulée, coût par effet, et reprise.

Mission points 2 et 4 / DJ8 : plafond cumulé (50 €) qui tient sur **tous** les passages, coût
journalisé **par carte**, et une interruption au milieu d'un lot qui ne perd rien et ne retraite
rien. Comme le lot v4, c'est un **fichier JSON** (pas une table : ce lot n'expose aucune route, il
s'opère en script depuis la flotte) relu et réécrit à chaque passage — jamais une estimation
recalculée en mémoire qui oublierait la dépense d'hier.

La reprise est au grain de l'**empreinte de texte** (la clé de ``card_scripts``) : un effet déjà
tranché (scripté, non supporté, ou à revoir) est dans ``empreintes_traitees`` et n'est **pas**
repris — ni re-proposé, ni re-payé. C'est la même idempotence que le registre lui-même, portée ici
pour que la reprise n'ait pas à relire la base avant de savoir où elle en était.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path

#: Emplacement par défaut du grand livre (hors dépôt, sous ``var/`` comme le lot v4).
DEFAULT_LEDGER_PATH = Path("var/assistance_scripts/ledger.json")


@dataclass
class EntreeCout:
    """Le coût et l'issue d'un effet traité — une ligne du journal par carte (mission point 4)."""

    empreinte: str
    resultat: str  # "scripte" | "non_supporte" | "a_revoir"
    cost_usd: str = "0"
    cost_eur: str = "0"
    confiance: str = ""
    famille: str = ""


@dataclass
class GrandLivre:
    """Registre JSON de dépense cumulée, d'effets traités (reprise) et de coûts par effet."""

    total_spent_usd: str = "0"
    total_spent_eur: str = "0"
    empreintes_traitees: list[str] = field(default_factory=list)
    scriptes: int = 0
    non_supportes: int = 0
    a_revoir: int = 0
    couts: list[dict] = field(default_factory=list)

    def deja_traitee(self, empreinte: str) -> bool:
        """Vrai si cet effet a déjà été tranché lors d'un passage antérieur (reprise : on saute)."""
        return empreinte in self.empreintes_traitees

    def reste_eur(self, plafond_eur: Decimal) -> Decimal:
        """Le budget restant = plafond − dépensé cumulé (jamais négatif affiché comme positif)."""
        return plafond_eur - Decimal(self.total_spent_eur)

    def enregistrer(
        self,
        *,
        empreinte: str,
        resultat: str,
        cost_usd: Decimal,
        cost_eur: Decimal,
        confiance: str = "",
        famille: str = "",
    ) -> None:
        """Ajoute un effet traité au grand livre : coût cumulé, compteur par issue, ligne de coût.

        Idempotent par empreinte : ré-enregistrer un effet déjà traité ne double ni le coût ni le
        compteur (une reprise qui crashe après l'écriture base mais avant la sauvegarde du livre ne
        doit pas re-facturer). Le coût, lui, n'est ajouté qu'au **premier** enregistrement.
        """
        if empreinte in self.empreintes_traitees:
            return
        self.empreintes_traitees.append(empreinte)
        self.total_spent_usd = str(Decimal(self.total_spent_usd) + cost_usd)
        self.total_spent_eur = str(Decimal(self.total_spent_eur) + cost_eur)
        if resultat == "scripte":
            self.scriptes += 1
        elif resultat == "non_supporte":
            self.non_supportes += 1
        elif resultat == "a_revoir":
            self.a_revoir += 1
        self.couts.append(
            asdict(
                EntreeCout(
                    empreinte=empreinte,
                    resultat=resultat,
                    cost_usd=str(cost_usd),
                    cost_eur=str(cost_eur),
                    confiance=confiance,
                    famille=famille,
                )
            )
        )

    def cout_par_carte_validee(self) -> Decimal:
        """Le coût moyen par script **validé** (mission point 5) — 0 si aucun (jamais NaN)."""
        if self.scriptes == 0:
            return Decimal("0")
        return Decimal(self.total_spent_eur) / Decimal(self.scriptes)

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> GrandLivre:
        return cls(
            total_spent_usd=data.get("total_spent_usd", "0"),
            total_spent_eur=data.get("total_spent_eur", "0"),
            empreintes_traitees=data.get("empreintes_traitees", []),
            scriptes=data.get("scriptes", 0),
            non_supportes=data.get("non_supportes", 0),
            a_revoir=data.get("a_revoir", 0),
            couts=data.get("couts", []),
        )


def charger(path: Path = DEFAULT_LEDGER_PATH) -> GrandLivre:
    """Charge le grand livre depuis ``path`` — un livre neuf si le fichier n'existe pas encore."""
    if not path.exists():
        return GrandLivre()
    return GrandLivre.from_json(json.loads(path.read_text(encoding="utf-8")))


def sauver(livre: GrandLivre, path: Path = DEFAULT_LEDGER_PATH) -> None:
    """Écrit le grand livre sur ``path`` (répertoire créé au besoin) — à appeler après chaque effet
    traité, pour qu'une interruption reprenne à l'exact endroit (mission point 2)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(livre.to_json(), indent=2, ensure_ascii=False), encoding="utf-8")


__all__ = [
    "DEFAULT_LEDGER_PATH",
    "EntreeCout",
    "GrandLivre",
    "charger",
    "sauver",
]
