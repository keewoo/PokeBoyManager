"""« K.O. en un coup » lu dans le journal — lot ``j-profil-jeu`` (badge du jalon J4).

Le badge « K.O. en un coup » récompense un Pokémon mis K.O. **alors qu'il était intact**, pas un
coup de grâce sur un Pokémon déjà entamé. Le journal ne porte pas les dégâts *antérieurs* d'un
Pokémon : ``EVT_KO`` porte ses ``compteurs`` au moment où il tombe, et ``EVT_ATTAQUE_DECLAREE`` les
dégâts du coup. L'égalité des deux signe une cible intacte — à condition qu'il n'y ait **qu'une**
attaque et **qu'un** K.O. dans le coup, sans quoi l'appariement n'est plus sûr.

Ces tests mesurent les deux moitiés de cette promesse, et la seconde compte autant que la première :

* ce qui **doit** compter : une attaque, un K.O., des compteurs égaux aux dégâts ;
* ce qui **ne doit pas** compter : le coup de grâce (compteurs > dégâts), le double K.O. (R-13.5),
  deux attaques dans le même coup, le K.O. au Checkup (poison, brûlure — infligé par personne), et
  un K.O. dont le bénéficiaire n'est pas l'attaquant.

Sans ces refus, le badge serait « probablement mérité », ce qui n'est pas mérité (D9). Règles
citées : R-10.9 (le détail des dégâts d'une attaque), R-13.1 (un Pokémon est K.O. quand ses
compteurs atteignent ses PV), R-13.3 (les récompenses vont à l'adversaire), R-13.5 (la
simultanéité).
"""

from __future__ import annotations

from pbm_game.journal.modele import (
    AUTEUR_SYSTEME,
    EVT_ATTAQUE_DECLAREE,
    EVT_ETAT_CHECKUP,
    EVT_KO,
    Action,
    Entree,
    Evenement,
)
from pbm_game.journal.recapitulatif import construire_recapitulatif

A = "joueur-a"
B = "joueur-b"
JOUEURS = (A, B)


def _entree(numero: int, auteur: str, evenements: list[Evenement]) -> Entree:
    """Une entrée de journal minimale mais complète (le moteur refuse un champ absent)."""
    return Entree(
        numero=numero,
        auteur=auteur,
        action=Action("declarer_attaque", auteur, {}),
        evenements=tuple(evenements),
        horodatage="2026-10-15T10:00:00+00:00",
        empreinte="0" * 64,
    )


def _attaque(joueur: str, degats: int) -> Evenement:
    """Une attaque déclarée et ses dégâts **finaux** (après faiblesse/résistance, R-10.9)."""
    return Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": joueur, "degats": degats})


def _ko(tombe: str, par: str, compteurs: int, pokemon: str = "i1") -> Evenement:
    """Un ``EVT_KO`` : ``tombe`` est le joueur dont le Pokémon tombe, ``par`` celui qui en profite.

    ``compteurs`` est le total de dégâts **posés sur le Pokémon** au moment du K.O. (R-13.1) :
    c'est la valeur dont l'égalité avec les dégâts de l'attaque signe une cible intacte.
    """
    return Evenement(
        EVT_KO,
        {
            "joueur": tombe,
            "pokemon": pokemon,
            "compteurs": compteurs,
            "recompenses_prises": 1,
            "par": par,
        },
    )


def _stats(recap, joueur: str):
    """Les compteurs d'un joueur dans un récapitulatif."""
    return next(s for s in recap.joueurs if s.joueur == joueur)


# --- Ce qui compte -----------------------------------------------------------


def test_une_attaque_qui_met_ko_une_cible_intacte_est_un_ko_en_un_coup():
    """90 dégâts, un K.O. à 90 compteurs : la cible n'avait rien encaissé — c'est le badge.

    C'est le test qui **échoue sans le changement** de ce lot : avant lui, le récapitulatif ne
    portait pas ce fait, et le badge n'avait aucune source.
    """
    recap = construire_recapitulatif(
        [_entree(1, A, [_attaque(A, 90), _ko(B, A, compteurs=90)])], JOUEURS
    )
    assert _stats(recap, A).ko_en_un_coup is True
    # Et seulement pour celui qui l'a fait : la victime n'a rien gagné.
    assert _stats(recap, B).ko_en_un_coup is False


def test_le_fait_survit_a_un_journal_rediffuse():
    """Le même journal relu deux fois donne le même fait : c'est un booléen, pas un compteur.

    Le canal temps réel rejoue toute la partie à chaque reconnexion (le risque nommé par
    ``j-partie-fin-ui``). Un compteur doublerait ; un fait ne peut pas devenir « deux fois vrai ».
    """
    entrees = [_entree(1, A, [_attaque(A, 60), _ko(B, A, compteurs=60)])]
    premier = construire_recapitulatif(entrees, JOUEURS)
    second = construire_recapitulatif(list(entrees) + list(entrees), JOUEURS)
    assert _stats(premier, A).ko_en_un_coup is True
    assert _stats(second, A).ko_en_un_coup is True


# --- Ce qui ne compte pas ---------------------------------------------------


def test_un_coup_de_grace_sur_un_pokemon_entame_ne_compte_pas():
    """30 dégâts sur un Pokémon qui en avait déjà 60 : K.O. à 90 compteurs, mais pas « en un coup ».

    C'est le cœur du badge : finir un Pokémon affaibli est une bonne chose, ce n'en est pas une
    rare.
    """
    recap = construire_recapitulatif(
        [
            _entree(1, A, [_attaque(A, 60)]),
            _entree(2, A, [_attaque(A, 30), _ko(B, A, compteurs=90)]),
        ],
        JOUEURS,
    )
    assert _stats(recap, A).ko_en_un_coup is False


def test_un_double_ko_ne_compte_pas_meme_si_un_total_coincide():
    """Deux K.O. dans le même coup (R-13.5) : on n'attribue rien, même quand un total coïncide.

    Avec deux K.O., rien ne dit **lequel** l'attaque a frappé de plein fouet : ``EVT_DEGATS`` nomme
    sa cible par la carte active et ``EVT_KO`` par la carte de base, qui diffèrent après une
    évolution. On préfère un badge manqué à un badge inventé.
    """
    recap = construire_recapitulatif(
        [
            _entree(
                1,
                A,
                [
                    _attaque(A, 90),
                    _ko(B, A, compteurs=90, pokemon="i1"),
                    _ko(B, A, compteurs=120, pokemon="i2"),
                ],
            )
        ],
        JOUEURS,
    )
    assert _stats(recap, A).ko_en_un_coup is False


def test_deux_attaques_dans_le_meme_coup_ne_comptent_pas():
    """Deux attaques dans une entrée : la somme ressemblerait à une attaque unique de leur total.

    Le cas vient des scripts d'effet qui enchaînent (D9) ; la stricture le refuse explicitement.
    """
    recap = construire_recapitulatif(
        [_entree(1, A, [_attaque(A, 40), _attaque(A, 50), _ko(B, A, compteurs=90)])], JOUEURS
    )
    assert _stats(recap, A).ko_en_un_coup is False


def test_un_ko_au_checkup_ne_compte_pour_personne():
    """Poison ou brûlure : le K.O. n'est infligé par aucune attaque, donc par personne.

    Même raisonnement que ``degats_infliges``, qui ne compte pas les dégâts d'état : le
    récapitulatif compte ce que le moteur a écrit, pas ce qu'on pourrait déduire.
    """
    recap = construire_recapitulatif(
        [
            _entree(
                1,
                AUTEUR_SYSTEME,
                [
                    Evenement(
                        EVT_ETAT_CHECKUP,
                        {"joueur": B, "etat": "empoisonne", "degats": 10, "regle": "R-12.2"},
                    ),
                    _ko(B, A, compteurs=100),
                ],
            )
        ],
        JOUEURS,
    )
    assert _stats(recap, A).ko_en_un_coup is False
    assert _stats(recap, B).ko_en_un_coup is False


def test_un_ko_dont_le_beneficiaire_nest_pas_lattaquant_ne_compte_pas():
    """L'attaque de A, un K.O. qui profite à B : la forme est incohérente, on n'attribue rien.

    Le cas ne devrait pas se produire — il est là pour que la condition reste **explicite** : le
    badge appartient à l'auteur du coup, nommé deux fois (``joueur`` de l'attaque, ``par`` du K.O.),
    jamais déduit d'un seul des deux.
    """
    recap = construire_recapitulatif(
        [_entree(1, A, [_attaque(A, 90), _ko(A, B, compteurs=90)])], JOUEURS
    )
    assert _stats(recap, A).ko_en_un_coup is False
    assert _stats(recap, B).ko_en_un_coup is False


def test_une_attaque_a_zero_degat_ne_compte_pas():
    """Une attaque sans dégât et un K.O. à zéro compteur : la coïncidence arithmétique est refusée.

    ``0 == 0`` serait vrai, et le badge serait offert à une attaque qui n'a rien fait. La condition
    exige donc des dégâts **strictement** positifs.
    """
    recap = construire_recapitulatif(
        [_entree(1, A, [_attaque(A, 0), _ko(B, A, compteurs=0)])], JOUEURS
    )
    assert _stats(recap, A).ko_en_un_coup is False
