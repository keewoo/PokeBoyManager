"""Mise en forme lisible d'un :class:`~pbm_sim.campagne.RapportCampagne` — écran et journal.

Rien de décoratif : on publie le **chiffre** (combien de parties saines sur combien), la
**distribution** des durées (le capteur de boucle), le détail des **anomalies** avec leur graine
(chacune rejouable en une commande), et la **couverture** (raisons de fin, affrontements de decks).
Ce que ce module produit est exactement ce que le compte rendu du lot cite comme preuve.
"""

from __future__ import annotations

from .campagne import Distribution, RapportCampagne


def _ligne_distribution(nom: str, d: Distribution) -> str:
    return (
        f"  {nom:7} min {d.minimum:>5}  médiane {d.mediane:>7.1f}  "
        f"moyenne {d.moyenne:>7.1f}  p95 {d.p95:>7.1f}  max {d.maximum:>5}"
    )


def formater(rapport: RapportCampagne, *, max_anomalies: int = 50) -> str:
    """Rend le rapport en texte. ``max_anomalies`` borne l'affichage (le total reste exact).

    Si plus de ``max_anomalies`` anomalies existent, on **le dit** (« … et N autres ») plutôt que
    de les tronquer en silence : un décompte caché serait un repli silencieux.
    """
    lignes: list[str] = []
    verdict = "✅ TOUTES SAINES" if rapport.toutes_saines else "❌ ANOMALIES DÉTECTÉES"
    lignes.append(f"Campagne de simulation — {verdict}")
    lignes.append(
        f"  parties : {rapport.nombre}   saines : {rapport.saines}   "
        f"anomalies : {len(rapport.anomalies)}"
    )
    lignes.append(_ligne_distribution("tours", rapport.distribution_tours))
    lignes.append(_ligne_distribution("coups", rapport.distribution_pas))

    if rapport.raisons:
        detail = "  ".join(f"{raison} : {n}" for raison, n in rapport.raisons.items())
        lignes.append(f"  raisons de fin : {detail}")
    if rapport.affrontements:
        lignes.append(f"  affrontements de decks couverts : {len(rapport.affrontements)}")

    if rapport.anomalies:
        lignes.append("  anomalies (graine → type : message) :")
        for a in rapport.anomalies[:max_anomalies]:
            lignes.append(f"    {a.graine}  (coup {a.pas})  → {a.type} : {a.message}")
        reste = len(rapport.anomalies) - max_anomalies
        if reste > 0:
            lignes.append(f"    … et {reste} autre(s) anomalie(s) non affichée(s) ci-dessus.")
        lignes.append("  reproduire : python -m pbm_sim reproduire <graine>")
    return "\n".join(lignes)


__all__ = ["formater"]
