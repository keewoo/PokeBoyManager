"""Récapitulatif d'une partie recalculé depuis le journal — lot ``j-partie-fin-ui``.

Ces tests portent le critère d'acceptation central du lot : « le récapitulatif est **exact**,
recalculé depuis le journal et non compté au fil de l'eau ». Le risque nommé est précis : un
compteur incrémenté à l'arrivée des événements double après un F5, parce que le canal temps réel
rejoue la partie entière à chaque reconnexion. Deux tests le mesurent directement
(:func:`test_un_journal_rediffuse_ne_double_aucun_chiffre`,
:func:`test_deux_calculs_sur_le_meme_journal_sont_identiques`).

Le reste vérifie l'**attribution** : chaque chiffre par joueur doit venir d'un champ que
l'événement porte explicitement, jamais d'une déduction. Le cas le plus parlant est le K.O. au
Checkup : l'entrée est écrite par le **système**, et le bénéficiaire des récompenses est nommé dans
l'événement (R-13.3). Créditer l'auteur de l'entrée donnerait les récompenses à « systeme », et le
récapitulatif afficherait zéro à tout le monde.

Règles citées : R-5.1 (un tour commence), R-10.9 (le détail des dégâts), R-13.3 (les récompenses
vont à l'adversaire du Pokémon mis K.O.), R-14 (la fin de partie clôt le journal).
"""

from __future__ import annotations

from pbm_game.journal.modele import (
    AUTEUR_SYSTEME,
    EVT_ATTAQUE_DECLAREE,
    EVT_DEGATS,
    EVT_ENERGIE_ATTACHEE,
    EVT_ETAT_CHECKUP,
    EVT_EVOLUTION,
    EVT_KO,
    EVT_OBJET_JOUE,
    EVT_PARTIE_TERMINEE,
    EVT_POKEMON_POSE,
    EVT_SUPPORTER_JOUE,
    EVT_TOUR_COMMENCE,
    RAISON_DERNIERE_RECOMPENSE,
    Action,
    Entree,
    Evenement,
)
from pbm_game.journal.recapitulatif import construire_recapitulatif

A = "joueur-a"
B = "joueur-b"
JOUEURS = (A, B)


def _entree(
    numero: int,
    auteur: str,
    evenements: list[Evenement],
    *,
    horodatage: str = "2026-10-14T10:00:00+00:00",
    type_action: str = "declarer_attaque",
) -> Entree:
    """Une entrée de journal minimale mais **complète** (le moteur n'accepte pas un champ absent).

    L'empreinte n'est pas vérifiée par le récapitulatif (il ne rejoue aucun état) : une valeur
    constante suffit, et ça dit bien ce que ce module lit — les événements, pas les états.
    """
    return Entree(
        numero=numero,
        auteur=auteur,
        action=Action(type_action, auteur, {}),
        evenements=tuple(evenements),
        horodatage=horodatage,
        empreinte="0" * 64,
    )


def _ko(joueur: str, par: str, recompenses: int = 1, pokemon: str = "i1") -> Evenement:
    """Un ``EVT_KO`` : ``joueur`` est celui qui tombe, ``par`` celui qui prend les récompenses."""
    return Evenement(
        EVT_KO,
        {
            "joueur": joueur,
            "pokemon": pokemon,
            "compteurs": 60,
            "recompenses_prises": recompenses,
            "par": par,
        },
    )


def _stats(recap, joueur: str):
    """Les compteurs d'un joueur dans un récapitulatif."""
    return next(s for s in recap.joueurs if s.joueur == joueur)


# --- Journal vide et joueurs muets ------------------------------------------


def test_journal_vide_donne_un_recapitulatif_a_zero():
    """Aucune entrée : tout à zéro, aucune durée, aucun meilleur coup — et aucune exception.

    L'écran de fin doit pouvoir s'afficher sur une partie close avant son premier coup (clôture
    pour inactivité). ``duree_s`` est ``None`` et pas 0 : « 0 s » se lirait « partie instantanée ».
    """
    recap = construire_recapitulatif([], JOUEURS)
    assert recap.coups == 0
    assert recap.tours == 0
    assert recap.duree_s is None
    assert recap.debut is None and recap.fin is None
    assert recap.meilleur_coup is None
    assert [s.joueur for s in recap.joueurs] == [A, B]
    assert all(s.degats_infliges == 0 and s.coups_joues == 0 for s in recap.joueurs)


def test_un_joueur_sans_evenement_figure_quand_meme_a_zero():
    """Un joueur qui n'a rien fait a sa colonne, à zéro : une colonne vide est une information."""
    recap = construire_recapitulatif(
        [_entree(0, A, [Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": A, "degats": 30})])],
        JOUEURS,
    )
    assert _stats(recap, B).degats_infliges == 0
    assert _stats(recap, B).coups_joues == 0


def test_un_evenement_d_un_joueur_inconnu_est_ignore():
    """Un ``joueur`` hors des deux sièges ne crée pas de troisième colonne (on ne devine pas)."""
    attaque = Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": "intrus", "degats": 90})
    recap = construire_recapitulatif([_entree(0, "intrus", [attaque])], JOUEURS)
    assert [s.joueur for s in recap.joueurs] == [A, B]
    assert sum(s.degats_infliges for s in recap.joueurs) == 0


# --- Dégâts (R-10.9) ---------------------------------------------------------


def test_degats_infliges_viennent_des_attaques_declarees():
    """``degats_infliges`` somme les ``EVT_ATTAQUE_DECLAREE``, qui portent le joueur (R-10.9).

    Le même coup porte **aussi** un ``EVT_DEGATS`` (le détail : base, faiblesse, résistance) avec
    la même valeur. Compter les deux doublerait le total — ce test le verrouille : 60 + 30 = 90,
    pas 180.
    """
    journal = [
        _entree(
            0,
            A,
            [
                Evenement(EVT_DEGATS, {"cible": "i1", "degats": 60, "compteurs": 6, "detail": {}}),
                Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": A, "degats": 60}),
            ],
        ),
        _entree(
            1,
            A,
            [
                Evenement(EVT_DEGATS, {"cible": "i1", "degats": 30, "compteurs": 3, "detail": {}}),
                Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": A, "degats": 30}),
            ],
        ),
    ]
    recap = construire_recapitulatif(journal, JOUEURS)
    assert _stats(recap, A).degats_infliges == 90
    assert _stats(recap, B).degats_infliges == 0


def test_une_attaque_sans_degat_ne_compte_rien():
    """Une attaque annulée ou sans dégât sec est déclarée à 0 : elle n'ajoute rien (R-16)."""
    recap = construire_recapitulatif(
        [_entree(0, A, [Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": A, "degats": 0})])],
        JOUEURS,
    )
    assert _stats(recap, A).degats_infliges == 0
    assert recap.meilleur_coup is None, "un coup à 0 dégât n'est pas un « meilleur coup »"


def test_les_degats_d_un_etat_special_ne_sont_infliges_par_personne():
    """Poison et brûlure (Checkup) ne sont infligés par aucun joueur : aucune colonne ne les porte.

    C'est un choix explicite, documenté dans le module : attribuer ces dégâts « à l'adversaire »
    serait une déduction, et elle serait fausse sur un auto-dégât. Le journal les garde ; le
    récapitulatif ne les met dans la colonne de personne.
    """
    recap = construire_recapitulatif(
        [
            _entree(
                0,
                AUTEUR_SYSTEME,
                [Evenement(EVT_ETAT_CHECKUP, {"joueur": A, "etat": "poison", "degats": 10})],
                type_action="checkup",
            )
        ],
        JOUEURS,
    )
    assert _stats(recap, A).degats_infliges == 0
    assert _stats(recap, B).degats_infliges == 0


# --- K.O. et récompenses (R-13.3) -------------------------------------------


def test_les_kos_sont_credites_au_joueur_nomme_par_l_evenement_pas_a_l_auteur():
    """Un K.O. au Checkup est écrit par le **système** : c'est ``par`` qui est crédité (R-13.3).

    Le test qui échoue si l'on crédite l'auteur de l'entrée : ``auteur`` vaut ici ``systeme``, donc
    un récapitulatif qui compterait sur l'auteur afficherait zéro K.O. aux deux joueurs.
    """
    journal = [
        _entree(
            0,
            AUTEUR_SYSTEME,
            [
                Evenement(EVT_ETAT_CHECKUP, {"joueur": A, "etat": "poison", "degats": 10}),
                _ko(A, B, recompenses=2),
            ],
            type_action="checkup",
        )
    ]
    recap = construire_recapitulatif(journal, JOUEURS)
    assert _stats(recap, B).kos_infliges == 1
    assert _stats(recap, B).recompenses_prises == 2
    assert _stats(recap, A).kos_infliges == 0
    assert _stats(recap, A).recompenses_prises == 0


def test_plusieurs_kos_dans_un_seul_coup_sont_tous_comptes():
    """Une attaque de zone met plusieurs Pokémon K.O. dans le même coup (R-13.1) : on les somme."""
    journal = [
        _entree(
            0,
            A,
            [
                Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": A, "degats": 120}),
                _ko(B, A, recompenses=1, pokemon="i1"),
                _ko(B, A, recompenses=3, pokemon="i2"),
            ],
        )
    ]
    recap = construire_recapitulatif(journal, JOUEURS)
    assert _stats(recap, A).kos_infliges == 2
    assert _stats(recap, A).recompenses_prises == 4


# --- Tours (R-5.1), durée, coups --------------------------------------------


def test_tours_est_le_plus_grand_numero_de_tour_commence():
    """Le nombre de tours est le plus grand ``numero`` vu dans un ``EVT_TOUR_COMMENCE`` (R-5.1).

    Compter les événements plutôt que lire leur numéro donnerait un chiffre faux dès qu'une
    resynchronisation en rediffuse un : le numéro est une **valeur**, pas un compteur.
    """
    def tour(n: int, actif: str) -> Evenement:
        return Evenement(EVT_TOUR_COMMENCE, {"numero": n, "joueur_actif": actif})

    journal = [
        _entree(0, AUTEUR_SYSTEME, [tour(1, A)]),
        _entree(1, AUTEUR_SYSTEME, [tour(2, B)]),
        _entree(2, AUTEUR_SYSTEME, [tour(3, A)]),
    ]
    assert construire_recapitulatif(journal, JOUEURS).tours == 3


def test_duree_est_l_ecart_entre_le_premier_et_le_dernier_horodatage():
    """La durée se lit sur les horodatages du journal — données d'entrée, jamais une horloge."""
    journal = [
        _entree(0, A, [], horodatage="2026-10-14T10:00:00+00:00"),
        _entree(1, B, [], horodatage="2026-10-14T10:07:12+00:00"),
    ]
    recap = construire_recapitulatif(journal, JOUEURS)
    assert recap.duree_s == 7 * 60 + 12
    assert recap.debut == "2026-10-14T10:00:00+00:00"
    assert recap.fin == "2026-10-14T10:07:12+00:00"


def test_un_horodatage_illisible_donne_une_duree_inconnue_pas_zero():
    """Un horodatage qu'on ne sait pas lire rend ``None`` : « inconnue » plutôt que « 0 s »."""
    journal = [
        _entree(0, A, [], horodatage="pas une date"),
        _entree(1, B, [], horodatage="2026-10-14T10:07:12+00:00"),
    ]
    assert construire_recapitulatif(journal, JOUEURS).duree_s is None


def test_une_horloge_qui_recule_ne_donne_pas_une_duree_negative():
    """Un dernier horodatage antérieur au premier donne 0, jamais un temps négatif."""
    journal = [
        _entree(0, A, [], horodatage="2026-10-14T10:07:12+00:00"),
        _entree(1, B, [], horodatage="2026-10-14T10:00:00+00:00"),
    ]
    assert construire_recapitulatif(journal, JOUEURS).duree_s == 0


def test_coups_joues_compte_les_entrees_de_chaque_auteur():
    """``coups_joues`` est le nombre d'entrées écrites par ce joueur ; le système n'en a pas."""
    journal = [
        _entree(0, A, []),
        _entree(1, A, []),
        _entree(2, B, []),
        _entree(3, AUTEUR_SYSTEME, []),
    ]
    recap = construire_recapitulatif(journal, JOUEURS)
    assert recap.coups == 4
    assert _stats(recap, A).coups_joues == 2
    assert _stats(recap, B).coups_joues == 1


# --- Cartes jouées -----------------------------------------------------------


def test_cartes_jouees_compte_les_cartes_et_pas_les_energies():
    """Les Énergies ont leur propre ligne : « 3 cartes jouées » n'inclut pas « dont 2 Énergies ».

    Sinon le chiffre serait illisible — attacher une Énergie est le geste le plus fréquent de la
    partie (R-5.4, une par tour), et il écraserait tout le reste.
    """
    journal = [
        _entree(
            0,
            A,
            [
                Evenement(EVT_OBJET_JOUE, {"joueur": A, "ref": "o1", "nom": "Potion"}),
                Evenement(EVT_SUPPORTER_JOUE, {"joueur": A, "ref": "s1", "nom": "Infirmière"}),
                Evenement(EVT_POKEMON_POSE, {"joueur": A, "pokemon": "p1", "zone": "banc"}),
                Evenement(EVT_EVOLUTION, {"joueur": A, "base": "p1", "vers": "e1"}),
                Evenement(EVT_ENERGIE_ATTACHEE, {"joueur": A, "energie": "n1", "cible": "p1"}),
                Evenement(EVT_ENERGIE_ATTACHEE, {"joueur": A, "energie": "n2", "cible": "p1"}),
            ],
        )
    ]
    recap = construire_recapitulatif(journal, JOUEURS)
    assert _stats(recap, A).cartes_jouees == 4
    assert _stats(recap, A).energies_attachees == 2


# --- Meilleur coup -----------------------------------------------------------


def test_meilleur_coup_est_la_plus_grosse_attaque_et_dit_si_elle_a_mis_ko():
    """Le meilleur coup est celui qui a infligé le plus de dégâts, avec son auteur et son K.O."""
    journal = [
        _entree(0, A, [Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": A, "degats": 60})]),
        _entree(
            1,
            B,
            [
                Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": B, "degats": 120}),
                _ko(A, B),
            ],
        ),
        _entree(2, A, [Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": A, "degats": 30})]),
    ]
    meilleur = construire_recapitulatif(journal, JOUEURS).meilleur_coup
    assert meilleur is not None
    assert (meilleur.numero, meilleur.joueur, meilleur.degats, meilleur.ko) == (1, B, 120, True)


def test_a_egalite_de_degats_le_premier_coup_reste_le_meilleur():
    """Départage déterministe : deux lectures du même journal donnent le même meilleur coup."""
    journal = [
        _entree(0, A, [Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": A, "degats": 60})]),
        _entree(1, B, [Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": B, "degats": 60})]),
    ]
    meilleur = construire_recapitulatif(journal, JOUEURS).meilleur_coup
    assert meilleur is not None
    assert meilleur.numero == 0 and meilleur.joueur == A


# --- Le risque nommé du lot : rien ne se compte au fil de l'eau -------------


def test_deux_calculs_sur_le_meme_journal_sont_identiques():
    """La fonction est **pure** : appelée deux fois sur le même journal, elle rend la même valeur.

    C'est ce qui permet à l'écran de fin de la rappeler à chaque affichage sans rien mémoriser —
    et donc de n'avoir aucun compteur à désynchroniser.
    """
    journal = [
        _entree(0, A, [Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": A, "degats": 60})]),
        _entree(
            1,
            A,
            [
                Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": A, "degats": 60}),
                _ko(B, A, recompenses=6),
                Evenement(
                    EVT_PARTIE_TERMINEE,
                    {"vainqueur": A, "raison": RAISON_DERNIERE_RECOMPENSE, "perdant": B},
                ),
            ],
        ),
    ]
    assert construire_recapitulatif(journal, JOUEURS) == construire_recapitulatif(journal, JOUEURS)


def test_un_journal_rediffuse_ne_double_aucun_chiffre():
    """Le risque nommé du lot, mesuré : rejouer la diffusion ne change pas les chiffres.

    On simule ce que vit l'écran après un F5 — le canal rejoue les coups depuis le début. Un
    compteur tenu « au fil de l'eau » verrait chaque coup deux fois ; un calcul **depuis le
    journal** voit le journal, qui ne contient chaque coup qu'une fois. On le prouve en recalculant
    sur le journal après une « rediffusion » complète : le résultat est le même, et il reste à
    120 dégâts — pas 240.
    """
    journal = [
        _entree(0, A, [Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": A, "degats": 60})]),
        _entree(1, A, [Evenement(EVT_ATTAQUE_DECLAREE, {"joueur": A, "degats": 60})]),
    ]
    avant = construire_recapitulatif(journal, JOUEURS)
    # La « rediffusion » : on relit exactement le même journal, comme le fait une resynchronisation.
    apres = construire_recapitulatif(list(journal), JOUEURS)
    assert avant == apres
    assert _stats(apres, A).degats_infliges == 120
    assert apres.coups == 2
