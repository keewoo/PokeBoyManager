"""Le DSL **branché** sur les demandes de décision — un ``choisir`` devient une vraie décision.

Lot ``j-effets-choix``. Jusqu'ici, un ``choisir`` était tranché par une stratégie déterministe
(``strategie_canonique``) : honnête et testable, mais ce n'était pas encore une *demande*. Ici on
prouve que, avec le résolveur ``resolveur_dsl_demandes``, un ``choisir`` **suspend** la résolution,
pose la demande dans l'état, puis **reprend** à la réponse — y compris quand un ``pile ou face`` le
précède (le re-déroulé ne rejoue pas l'aléatoire). On vérifie aussi que la stratégie canonique reste
intacte (aucune régression du lot DSL).
"""

from __future__ import annotations

from fabrique_dsl import etat, joueur, pokemon

from pbm_game.demandes.modele import Reponse
from pbm_game.demandes.moteur import REGISTRE_EFFETS, demarrer_resolution, expirer, repondre
from pbm_game.effets.dsl import charger_programme, compiler_en_effet
from pbm_game.effets.dsl.contexte import ContexteEffet
from pbm_game.effets.pile import PileEffets, SourceEffet
from pbm_game.rng import Rng

_GRAINE = b"dsl-choix-000000"  # 16 octets


def _ctx(joueur_id: str = "alice", adversaire: str = "bob") -> ContexteEffet:
    return ContexteEffet(
        source=SourceEffet("Potion", ref="ref-potion", instance_id="i-potion"),
        joueur=joueur_id,
        adversaire=adversaire,
    )


def _effet_choisir_soigner():
    """« Choisissez 1 de vos Pokémon et soignez-le entièrement. » — compilé en effet de pile."""
    prog = charger_programme(
        {
            "version": 1,
            "effets": [
                {
                    "op": "choisir",
                    "cible": {"zone": "en_jeu", "proprietaire": "moi", "nombre": 1},
                    "alors": [{"op": "soigner"}],
                }
            ],
        }
    )
    return compiler_en_effet(prog, _ctx(), libelle="Potion", regle="R-9.3")


def _alice_bob():
    alice = joueur(
        "alice", actif=pokemon("a-actif", compteurs=30), banc=(pokemon("a-banc", compteurs=20),)
    )
    bob = joueur("bob", actif=pokemon("b"))
    return alice, bob


def _degats(etat, jid: str) -> dict[str, int]:
    j = next(x for x in etat.joueurs if x.id == jid)
    return {p.cartes[0].instance_id: p.compteurs_degats for p in (j.actif, *j.banc)}


def test_choisir_suspend_la_resolution_avec_la_bonne_demande():
    alice, bob = _alice_bob()
    pile = PileEffets().empiler(_effet_choisir_soigner())
    etat1, _ = demarrer_resolution(etat(alice, bob), pile, Rng(_GRAINE), registre=REGISTRE_EFFETS)
    assert etat1.resolution is not None
    d = etat1.resolution.demande
    assert d.destinataire == "alice"  # par défaut, celui qui joue l'effet
    assert set(d.options) == {"a-actif", "a-banc"}  # les Pokémon en jeu d'alice, par identité
    assert _degats(etat1, "alice") == {"a-actif": 30, "a-banc": 20}  # rien soigné tant qu'on attend


def test_choisir_reprend_a_la_reponse_et_applique_le_corps():
    alice, bob = _alice_bob()
    pile = PileEffets().empiler(_effet_choisir_soigner())
    rng = Rng(_GRAINE)
    etat1, _ = demarrer_resolution(etat(alice, bob), pile, rng, registre=REGISTRE_EFFETS)
    d = etat1.resolution.demande
    etat2, _ = repondre(etat1, Reponse(d.id, ("a-banc",)), rng, registre=REGISTRE_EFFETS)
    assert etat2.resolution is None
    assert _degats(etat2, "alice") == {"a-actif": 30, "a-banc": 0}  # le banc choisi est soigné


def test_expiration_d_un_choisir_dsl_applique_le_defaut():
    alice, bob = _alice_bob()
    pile = PileEffets().empiler(_effet_choisir_soigner())
    rng = Rng(_GRAINE)
    etat1, _ = demarrer_resolution(etat(alice, bob), pile, rng, registre=REGISTRE_EFFETS)
    # Personne ne répond : la réponse par défaut (1re option = l'Actif) est appliquée.
    etat2, _ = expirer(etat1, rng, registre=REGISTRE_EFFETS)
    assert etat2.resolution is None
    assert _degats(etat2, "alice") == {"a-actif": 0, "a-banc": 20}


def test_pile_ou_face_avant_choisir_n_est_pas_rejoue_au_re_deroule():
    """Un ``pile ou face`` précède le ``choisir`` : au re-déroulé, il retombe à l'identique.

    C'est le bout DSL du piège de la section 5 : la demande est une donnée, pas une attente de code,
    et re-dérouler le script ne doit pas re-tirer l'aléatoire (sinon le journal d'anti-triche
    compterait deux fois le même jet).
    """
    alice, bob = _alice_bob()
    prog = charger_programme(
        {
            "version": 1,
            "effets": [
                {
                    "op": "pile_ou_face",
                    "nombre": 1,
                    "alors": [
                        {
                            "op": "poser_compteurs",
                            "cible": {"zone": "actif", "proprietaire": "adversaire"},
                            "nombre": 2,
                        }
                    ],
                },
                {
                    "op": "choisir",
                    "cible": {"zone": "en_jeu", "proprietaire": "moi", "nombre": 1},
                    "alors": [{"op": "soigner"}],
                },
            ],
        }
    )
    effet = compiler_en_effet(prog, _ctx(), libelle="Potion", regle="R-9.3")
    pile = PileEffets().empiler(effet)
    rng = Rng(_GRAINE)

    etat1, _ = demarrer_resolution(etat(alice, bob), pile, rng, registre=REGISTRE_EFFETS)
    # Suspendu au choisir : le jet a été ramené en arrière, aucun tirage ne subsiste.
    assert [t for t in rng.journal() if t.flux == "dsl:pile:alice"] == []

    d = etat1.resolution.demande
    etat2, evts2 = repondre(etat1, Reponse(d.id, ("a-actif",)), rng, registre=REGISTRE_EFFETS)
    assert etat2.resolution is None
    # Le jet a bien eu lieu, une seule fois, dans la passe qui aboutit.
    assert any(e.type == "dsl_pile_ou_face" for e in evts2)
    assert len([t for t in rng.journal() if t.flux == "dsl:pile:alice"]) == 1


def test_strategie_canonique_inchangee_sans_demande():
    """Sans le résolveur de demandes, un ``choisir`` reste tranché par la stratégie canonique.

    Garantit qu'on n'a **pas** changé la sémantique du ``choisir`` (D9 : la primitive était déjà
    implémentée ; seule la *politique* de décision est devenue branchable).
    """
    from pbm_game.effets.dsl import executer_programme

    alice, bob = _alice_bob()
    prog = charger_programme(
        {
            "version": 1,
            "effets": [
                {
                    "op": "choisir",
                    "cible": {"zone": "en_jeu", "proprietaire": "moi", "nombre": 1},
                    "alors": [{"op": "soigner"}],
                }
            ],
        }
    )
    res = executer_programme(etat(alice, bob), prog, _ctx(), Rng(_GRAINE))
    # ResultatProgramme.etat porte l'état ; exactement un Pokémon soigné (comportement canonique).
    j = next(x for x in res.etat.joueurs if x.id == "alice")
    assert sorted(p.compteurs_degats for p in (j.actif, *j.banc)) == [0, 20]
