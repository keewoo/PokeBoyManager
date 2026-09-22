"""Quand rendre la main à l'IA pour TOUT refaire — découpe comprise (lot `h1-seconde-passe-ia`).

Règle posée par JF le 22/09/2026 :

> si la découpe présente 30 % d'image tronquée OU si le taux de reconnaissance moyen est
> inférieur à 55 %, alors on demande à l'IA de faire ET la découpe, ET la reconnaissance.

Les deux déclencheurs disent la même chose par deux chemins. Une troncature se voit sur les
pixels : le cadre est à cheval sur deux cartes, ou la carte déborde de la photo. Une confiance
moyenne qui s'effondre se voit sur le résultat : le catalogue ne reconnaît rien de ce qu'on lui
montre, ce qui arrive surtout quand on lui montre un morceau de deux cartes. L'un rattrape
l'autre : une découpe franchement fausse mais bien découpée à l'œil passe le premier contrôle
et tombe sur le second.
"""

from dataclasses import dataclass

# 30 % du cadre qui n'appartient pas à la carte visée. Au-delà, ce qu'on identifie n'est plus
# la carte : autant redemander la découpe à l'IA.
SEUIL_TRONCATURE = 0.30
# Sous 55 % de confiance moyenne, le rapprochement au catalogue ne tient plus. Les découpes à
# cheval constatées le 22/09 sortaient à 34 % et 43 %.
SEUIL_CONFIANCE_MOYENNE = 0.55


@dataclass(frozen=True)
class VerdictSecondePasse:
    needed: bool
    reason: str | None  # "troncature" | "confiance" | "troncature+confiance"
    truncated_max: float
    mean_confidence: float | None  # `None` si aucune détection n'a de candidat

    def as_dict(self) -> dict:
        return {
            "needed": self.needed,
            "reason": self.reason,
            "truncated_max": round(self.truncated_max, 3),
            "mean_confidence": (
                None if self.mean_confidence is None else round(self.mean_confidence, 3)
            ),
        }


def _troncature(detection) -> float:
    quality = (detection.bbox or {}).get("crop_quality") or {}
    try:
        return float(quality.get("truncated") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _confiance(detection) -> float | None:
    """Confiance du meilleur candidat de cette détection, `None` si elle n'en a aucun.

    Une détection sans candidat n'est PAS comptée comme 0 : elle n'a rien à dire sur la qualité
    du rapprochement (l'identification a pu être interrompue). La compter à zéro ferait chuter la
    moyenne et déclencherait une seconde passe pour une raison qui n'est pas la bonne.
    """
    candidats = detection.candidates or []
    if not candidats:
        return None
    try:
        return max(float(c.get("combined_score") or 0.0) for c in candidats)
    except (AttributeError, TypeError, ValueError):
        return None


def evaluer(detections) -> VerdictSecondePasse:
    """Décide si l'IA doit tout refaire, à partir des détections d'UN envoi."""
    if not detections:
        return VerdictSecondePasse(
            needed=False, reason=None, truncated_max=0.0, mean_confidence=None
        )

    troncature_max = max(_troncature(d) for d in detections)
    confiances = [c for c in (_confiance(d) for d in detections) if c is not None]
    moyenne = sum(confiances) / len(confiances) if confiances else None

    raisons = []
    if troncature_max >= SEUIL_TRONCATURE:
        raisons.append("troncature")
    if moyenne is not None and moyenne < SEUIL_CONFIANCE_MOYENNE:
        raisons.append("confiance")

    return VerdictSecondePasse(
        needed=bool(raisons),
        reason="+".join(raisons) if raisons else None,
        truncated_max=troncature_max,
        mean_confidence=moyenne,
    )
