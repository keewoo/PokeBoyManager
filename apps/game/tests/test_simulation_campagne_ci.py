"""**La campagne réduite de CI** : à chaque poussée, des centaines de parties doivent rester saines.

C'est la garde que la fiche réclame — « intégrer une campagne réduite en CI à chaque lot de scripts
de cartes ». Elle tourne dans le job ``game`` de GitHub Actions (``uv run pytest``), donc à chaque
poussée sur une branche de lot et sur ``main``. Une régression du moteur qui casserait une partie
(état invalide, blocage, boucle, rejeu divergent) ferait **rougir** ce test, avec la graine fautive
à rejouer. Une suite verte que la CI n'exécute pas ne vaut rien ; celle-ci, la CI l'exécute.

Le chiffre est modeste (250) pour tenir en quelques secondes ; la **campagne de masse** (10 000+)
tourne sur chimera et la nuit (``.github/workflows/simulation-nuit.yml``), hors du chemin critique
de CI.
"""

from __future__ import annotations

from pbm_sim.campagne import campagne, graines

#: Taille de la campagne de CI. Assez pour couvrir plusieurs affrontements de decks et les trois
#: voies de victoire, assez petit pour rester sous ~10 s dans le job ``game``.
PARTIES_CI = 250


def test_la_campagne_reduite_de_ci_est_entierement_saine():
    """250 parties, zéro anomalie — et le chiffre est publié dans la sortie de test (preuve)."""
    rapport = campagne(graines("ci", PARTIES_CI), parallele=True)
    assert rapport.nombre == PARTIES_CI
    # Le cœur de la garde : aucune anomalie. En cas d'échec, le message liste les graines fautives.
    assert rapport.toutes_saines, (
        f"{len(rapport.anomalies)} anomalie(s) sur {rapport.nombre} parties — "
        + " | ".join(f"{a.graine}:{a.type}:{a.message}" for a in rapport.anomalies[:10])
    )
    print(f"Campagne CI : {rapport.saines}/{rapport.nombre} parties saines.")


def test_la_campagne_de_ci_exerce_vraiment_le_moteur():
    """Garde-fou de la garde : vérifier que ces parties jouent pour de vrai, pas qu'elles finissent
    toutes au premier tour (une campagne qui n'exerce rien serait verte « sur rien »)."""
    rapport = campagne(graines("ci", PARTIES_CI), parallele=True)
    # Plusieurs voies de fin de partie représentées (récompenses, pioche vide, plus de Pokémon).
    assert len(rapport.raisons) >= 2, rapport.raisons
    # Plusieurs affrontements de decks couverts, et des parties qui durent (médiane de coups > 20).
    assert len(rapport.affrontements) >= 5, rapport.affrontements
    assert rapport.distribution_pas.mediane > 20, rapport.distribution_pas
