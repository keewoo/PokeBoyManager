"""La **porte de vérification** — ce qui décide si un script proposé entre en jeu (DJ8).

Module **pur** (aucune E/S, aucun appel réseau) : on lui donne une :class:`Proposition` déjà
obtenue de l'IA et le :class:`VerdictContradicteur` de la seconde IA, il rend le verdict final. La
décision s'appuie sur **l'exécution réelle** (les essais rejoués contre le moteur, via
:func:`pbm_game.effets.dsl.essais.verifier_script`) et la cohérence maison — jamais sur la confiance
annoncée par le modèle.

DJ8, sans détour : un script n'entre en jeu (``scripte``) que si **ses tests passent ET** la seconde
IA, chargée de le contredire, **l'a approuvé**. Le reste est refusé — jamais joué « au mieux » :

* l'IA a déclaré l'effet hors du langage → ``non_supporte`` (D9, la raison est conservée) ;
* le script ne se charge pas, un essai échoue, aucun essai n'est fourni, ou le contradicteur rejette
  (ou son contre-cas met le script en défaut) → ``a_revoir`` (un script existe mais n'est pas
  prouvé : il ne se joue pas tant qu'il n'est pas repassé).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pbm_game.effets.dsl.chargement import ProgrammeInvalide, charger_programme
from pbm_game.effets.dsl.essais import executer_essai, verifier_script

from pbm_api.jeu.scripts.assistance.familles import famille as _famille
from pbm_api.jeu.scripts.assistance.fournisseur import Proposition, VerdictContradicteur

#: Issue : le script entre en jeu (tests verts + contradicteur approuve).
GATE_SCRIPTE = "scripte"
#: Issue : l'effet n'entre pas dans le langage (l'IA l'a déclaré) — refusé, nommé (D9).
GATE_NON_SUPPORTE = "non_supporte"
#: Issue : un script existe mais n'est pas prouvé (tests ou contradicteur) — ne se joue pas.
GATE_A_REVOIR = "a_revoir"


@dataclass(frozen=True)
class ResultatPorte:
    """Le verdict final pour un effet : l'issue, les preuves, la raison, la famille.

    * ``resultat`` — :data:`GATE_SCRIPTE` / :data:`GATE_NON_SUPPORTE` / :data:`GATE_A_REVOIR` ;
    * ``tests_ok`` — les essais (proposés + contre-cas) sont-ils tous verts ;
    * ``contradicteur_ok`` — la seconde IA a-t-elle approuvé (``None`` si l'étape n'a pas eu lieu,
      p. ex. tests déjà rouges : inutile de contredire un script déjà faux) ;
    * ``raison`` — pourquoi cette issue, nommée (jamais « au mieux ») ;
    * ``detail_essais`` — le détail par essai (nom, anomalies) pour le rapport et le débogage ;
    * ``famille`` — la famille d'effet (pour le rapport par famille et le veto de JF).
    """

    resultat: str
    tests_ok: bool
    contradicteur_ok: bool | None
    raison: str
    famille: str
    detail_essais: list[dict] = field(default_factory=list)


def _famille_de(proposition: Proposition, texte_fr: str) -> str:
    """La famille de l'effet : du script s'il existe, sinon du texte (cf. :mod:`.familles`)."""
    return _famille(texte_fr, proposition.script)


def evaluer(
    *,
    texte_fr: str,
    proposition: Proposition,
    verdict: VerdictContradicteur | None,
) -> ResultatPorte:
    """Applique la porte DJ8 à une proposition et au verdict du contradicteur, et rend l'issue.

    ``verdict`` peut être ``None`` : le runner n'appelle le contradicteur **que** si les tests sont
    déjà verts (ne pas payer une contradiction sur un script déjà faux). Dans ce cas, un script aux
    tests rouges est ``a_revoir`` avec ``contradicteur_ok=None`` — l'étape n'a pas eu lieu, et on le
    dit plutôt que de laisser croire à un rejet du contradicteur.
    """
    famille = _famille_de(proposition, texte_fr)

    if proposition.non_supporte:
        raison = proposition.raison or "effet déclaré hors du langage par l'IA (tournure manquante)"
        return ResultatPorte(
            resultat=GATE_NON_SUPPORTE,
            tests_ok=False,
            contradicteur_ok=None,
            raison=raison,
            famille=famille,
        )

    # Tests : chargement DSL + essais proposés + cohérence maison (tout dans le moteur pur).
    verdict_tests = verifier_script(proposition.script, proposition.essais)
    detail = verdict_tests["essais"]
    if not verdict_tests["valide"]:
        return ResultatPorte(
            resultat=GATE_A_REVOIR,
            tests_ok=False,
            contradicteur_ok=None,
            raison=f"tests non verts : {verdict_tests['raison']}",
            famille=famille,
            detail_essais=detail,
        )

    # Les tests sont verts : le verdict du contradicteur est requis (DJ8).
    if verdict is None:
        return ResultatPorte(
            resultat=GATE_A_REVOIR,
            tests_ok=True,
            contradicteur_ok=None,
            raison="tests verts mais aucun verdict du contradicteur (étape manquante)",
            famille=famille,
            detail_essais=detail,
        )
    if verdict.verdict != "approuve":
        return ResultatPorte(
            resultat=GATE_A_REVOIR,
            tests_ok=True,
            contradicteur_ok=False,
            raison=f"contradicteur : rejeté — {verdict.raison}",
            famille=famille,
            detail_essais=detail,
        )

    # Le contradicteur approuve mais fournit un contre-cas : on le rejoue. S'il mord, le script est
    # faux malgré l'approbation — la preuve l'emporte sur l'avis (le vrai garde-fou, pas l'opinion).
    if verdict.essai_contre is not None:
        try:
            programme = charger_programme(proposition.script)
            anomalies = executer_essai(programme, verdict.essai_contre)
        except (ProgrammeInvalide, ValueError) as exc:
            anomalies = [f"contre-cas inexploitable : {exc}"]
        if anomalies:
            detail = [*detail, {"nom": "contre-cas du contradicteur", "anomalies": anomalies}]
            return ResultatPorte(
                resultat=GATE_A_REVOIR,
                tests_ok=False,
                contradicteur_ok=True,
                raison="le contre-cas du contradicteur met le script en défaut",
                famille=famille,
                detail_essais=detail,
            )

    return ResultatPorte(
        resultat=GATE_SCRIPTE,
        tests_ok=True,
        contradicteur_ok=True,
        raison="tests verts et contradicteur approuve (DJ8)",
        famille=famille,
        detail_essais=detail,
    )


__all__ = [
    "GATE_SCRIPTE",
    "GATE_NON_SUPPORTE",
    "GATE_A_REVOIR",
    "ResultatPorte",
    "evaluer",
]
