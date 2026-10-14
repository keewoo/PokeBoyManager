"""Les **règles** de notification du jeu (lot `j-notifications-jeu`) — sans base, sans horloge.

C'est ici que les trois critères d'acceptation du lot se vérifient, parce que c'est ici qu'ils sont
décidés (:mod:`pbm_api.notifications.regles`) :

* « chaque type de notification est désactivable séparément » → :func:`test_genre_desactive_seul`
  et :func:`test_desactiver_un_genre_nen_desactive_pas_un_autre` ;
* « le silence nocturne est respecté, y compris pour les invitations » →
  :func:`test_silence_nocturne_sapplique_a_linvitation` et les cas de fenêtre ;
* « aucune partie ne produit plus de notifications que le plafond fixé » →
  :func:`test_plafond_global_borne_la_partie_quoi_quil_arrive`, qui **simule une partie entière**
  en boucle sans jamais faire d'hypothèse sur les genres.

Aucun de ces tests ne touche Postgres : les règles sont pures, donc on peut se placer à 23 h un
mardi sans attendre 23 h. C'est exactement pourquoi le module est séparé du service.
"""

from datetime import UTC, datetime, time

import pytest

from pbm_api.models.notifications import (
    NOTIF_ADVERSAIRE_TROUVE,
    NOTIF_GENRES,
    NOTIF_INVITATION_RECUE,
    NOTIF_TON_TOUR,
)
from pbm_api.notifications.regles import (
    PLAFOND_PAR_GENRE,
    PLAFOND_PAR_PARTIE,
    Compteurs,
    GenreInconnu,
    Reglages,
    dans_silence_nocturne,
    decider,
)

#: Un mardi à 14 h, heure de Paris — hors de toute fenêtre de silence par défaut.
EN_PLEIN_JOUR = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)  # 14 h à Paris (UTC+2)
#: Le même mardi à 23 h 30, heure de Paris — en plein silence nocturne par défaut.
EN_PLEINE_NUIT = datetime(2026, 10, 13, 21, 30, tzinfo=UTC)  # 23 h 30 à Paris


def test_genre_inconnu_leve_plutot_que_denregistrer():
    """Genre hors vocabulaire = bug d'appelant : on lève, on n'écrit pas une ligne illisible."""
    with pytest.raises(GenreInconnu):
        decider(
            "sonnerie_imaginaire",
            reglages=Reglages(),
            compteurs=Compteurs(),
            instant=EN_PLEIN_JOUR,
        )


def test_par_defaut_on_notifie_en_plein_jour():
    """Compte sans réglage, en pleine journée : la notification part, et l'e-mail d'invitation."""
    decision = decider(
        NOTIF_INVITATION_RECUE,
        reglages=Reglages(),
        compteurs=Compteurs(),
        instant=EN_PLEIN_JOUR,
    )
    assert decision.enregistrer
    assert not decision.silencieuse
    assert decision.relais_email, "l'invitation est le seul genre relayé par e-mail"
    assert decision.relais_push


def test_ton_tour_nest_jamais_relaye_par_email():
    """« C'est ton tour » par e-mail serait du harcèlement par un autre moyen : jamais d'e-mail."""
    decision = decider(
        NOTIF_TON_TOUR, reglages=Reglages(), compteurs=Compteurs(), instant=EN_PLEIN_JOUR
    )
    assert decision.enregistrer
    assert not decision.relais_email


# --- Critère 1 : chaque type est désactivable séparément --------------------------------------


@pytest.mark.parametrize("genre", sorted(NOTIF_GENRES))
def test_genre_desactive_seul(genre):
    """**Chaque** genre, sans exception, se coupe séparément — y compris l'invitation."""
    decision = decider(
        genre,
        reglages=Reglages(genres_desactives=frozenset({genre})),
        compteurs=Compteurs(),
        instant=EN_PLEIN_JOUR,
    )
    assert not decision.enregistrer
    assert not decision.relais_email and not decision.relais_push
    assert genre in decision.motif, "le refus doit nommer le genre coupé"


def test_desactiver_un_genre_nen_desactive_pas_un_autre():
    """Couper « c'est ton tour » laisse passer l'invitation : interrupteurs indépendants."""
    reglages = Reglages(genres_desactives=frozenset({NOTIF_TON_TOUR}))
    assert not decider(
        NOTIF_TON_TOUR, reglages=reglages, compteurs=Compteurs(), instant=EN_PLEIN_JOUR
    ).enregistrer
    assert decider(
        NOTIF_INVITATION_RECUE, reglages=reglages, compteurs=Compteurs(), instant=EN_PLEIN_JOUR
    ).enregistrer


def test_un_genre_coupe_prime_sur_le_silence_et_les_plafonds():
    """La coupure du joueur est le premier contrôle : son motif ne doit pas être masqué."""
    decision = decider(
        NOTIF_TON_TOUR,
        reglages=Reglages(genres_desactives=frozenset({NOTIF_TON_TOUR})),
        compteurs=Compteurs(total_partie=PLAFOND_PAR_PARTIE, doublon_non_lu=True),
        instant=EN_PLEINE_NUIT,
    )
    assert not decision.enregistrer
    assert "désactivé" in decision.motif


# --- Critère 2 : le silence nocturne, y compris pour les invitations --------------------------


def test_silence_nocturne_actif_par_defaut():
    """Un compte sans réglage **est** en silence la nuit : mieux vaut demander le réveil."""
    assert dans_silence_nocturne(Reglages(), EN_PLEINE_NUIT)
    assert not dans_silence_nocturne(Reglages(), EN_PLEIN_JOUR)


def test_silence_nocturne_sapplique_a_linvitation():
    """L'invitation reçue de nuit est **enregistrée sans réveiller** : aucun e-mail, aucune alerte.

    C'est la lecture retenue du critère « y compris pour les invitations » : on ne perd pas
    l'invitation (elle sera lue au matin, et elle reste dans la liste des reçues), on ne sonne pas.
    """
    decision = decider(
        NOTIF_INVITATION_RECUE,
        reglages=Reglages(),
        compteurs=Compteurs(),
        instant=EN_PLEINE_NUIT,
    )
    assert decision.enregistrer, "rien ne doit être perdu : la nuit, on enregistre"
    assert decision.silencieuse
    assert not decision.relais_email, "le relais e-mail attend le réveil"
    assert not decision.relais_push
    assert "silence nocturne" in decision.motif


@pytest.mark.parametrize("genre", sorted(NOTIF_GENRES))
def test_aucun_genre_nechappe_au_silence(genre):
    """Aucun genre ne contourne le silence : s'il en existait un, ce serait la fuite du critère."""
    decision = decider(
        genre, reglages=Reglages(), compteurs=Compteurs(), instant=EN_PLEINE_NUIT
    )
    assert decision.silencieuse
    assert not decision.relais_email and not decision.relais_push


def test_silence_franchit_minuit():
    """La fenêtre par défaut (21 h → 7 h) couvre bien les deux côtés de minuit."""
    reglages = Reglages()
    # 22 h et 6 h, heure de Paris (UTC+2 en octobre) → 20 h et 4 h UTC.
    assert dans_silence_nocturne(reglages, datetime(2026, 10, 13, 20, 0, tzinfo=UTC))
    assert dans_silence_nocturne(reglages, datetime(2026, 10, 14, 4, 0, tzinfo=UTC))
    # 8 h à Paris → 6 h UTC : la fenêtre est fermée.
    assert not dans_silence_nocturne(reglages, datetime(2026, 10, 14, 6, 0, tzinfo=UTC))


def test_silence_dans_la_meme_journee():
    """Une fenêtre qui ne franchit pas minuit (sieste 13 h → 14 h) se comporte normalement."""
    reglages = Reglages(silence_debut=time(13, 0), silence_fin=time(14, 0))
    assert dans_silence_nocturne(reglages, datetime(2026, 10, 13, 11, 30, tzinfo=UTC))  # 13 h 30
    # 14 h 30 à Paris : la sieste est passée.
    assert not dans_silence_nocturne(reglages, datetime(2026, 10, 13, 12, 30, tzinfo=UTC))


def test_silence_borne_inclusive_puis_exclusive():
    """La fenêtre est ``[debut, fin[`` : 21 h pile est silencieuse, 7 h pile ne l'est plus."""
    reglages = Reglages()
    assert dans_silence_nocturne(reglages, datetime(2026, 10, 13, 19, 0, tzinfo=UTC))  # 21 h
    assert not dans_silence_nocturne(reglages, datetime(2026, 10, 14, 5, 0, tzinfo=UTC))  # 7 h


def test_silence_desactivable():
    """Le silence se coupe : un joueur qui veut être prévenu la nuit le peut."""
    assert not dans_silence_nocturne(Reglages(silence_actif=False), EN_PLEINE_NUIT)


def test_fenetre_vide_nest_pas_un_silence_permanent():
    """« De 21 h à 21 h » est une fenêtre **vide**, jamais un silence de 24 h.

    Sans cette garde, régler début = fin désactiverait toutes les notifications par un chemin
    détourné — alors que la façon de les couper, c'est ``genres_desactives``.
    """
    reglages = Reglages(silence_debut=time(21, 0), silence_fin=time(21, 0))
    assert not dans_silence_nocturne(reglages, EN_PLEINE_NUIT)
    assert not dans_silence_nocturne(reglages, EN_PLEIN_JOUR)


def test_silence_lu_dans_le_fuseau_du_joueur():
    """« 21 h » veut dire 21 h **chez le joueur** : le même instant n'est pas la nuit partout.

    Échoue si l'on compare en UTC : 21 h 30 UTC, c'est 23 h 30 à Paris (silence) mais 17 h 30 à
    Montréal (pas silence).
    """
    assert dans_silence_nocturne(Reglages(fuseau="Europe/Paris"), EN_PLEINE_NUIT)
    assert not dans_silence_nocturne(Reglages(fuseau="America/Montreal"), EN_PLEINE_NUIT)


# --- Critère 3 : aucune partie ne dépasse le plafond fixé -------------------------------------


def test_doublon_non_lu_refuse():
    """On ne redit pas « c'est ton tour » quand la précédente n'a même pas été lue."""
    decision = decider(
        NOTIF_TON_TOUR,
        reglages=Reglages(),
        compteurs=Compteurs(doublon_non_lu=True),
        instant=EN_PLEIN_JOUR,
    )
    assert not decision.enregistrer
    assert "attend déjà d'être lue" in decision.motif


def test_plafond_du_genre_refuse():
    """Chaque genre s'épuise sur une partie — « c'est ton tour » le premier."""
    plafond = PLAFOND_PAR_GENRE[NOTIF_TON_TOUR]
    decision = decider(
        NOTIF_TON_TOUR,
        reglages=Reglages(),
        compteurs=Compteurs(total_partie=plafond, par_genre={NOTIF_TON_TOUR: plafond}),
        instant=EN_PLEIN_JOUR,
    )
    assert not decision.enregistrer
    assert "plafond du genre" in decision.motif


def test_plafond_de_partie_refuse_meme_un_genre_sans_plafond_propre():
    """Le plafond global mord même pour un genre qui n'a pas de plafond propre.

    C'est la garantie structurelle du critère : un genre futur qui oublierait son plafond resterait
    borné par celui de la partie.
    """
    decision = decider(
        NOTIF_INVITATION_RECUE,
        reglages=Reglages(),
        compteurs=Compteurs(total_partie=PLAFOND_PAR_PARTIE, par_genre={}),
        instant=EN_PLEIN_JOUR,
    )
    assert not decision.enregistrer
    assert "plafond de la partie" in decision.motif


def test_somme_des_plafonds_par_genre_depasse_le_plafond_global():
    """Invariant de conception : aucun genre ne peut à lui seul épuiser la partie.

    Si la somme des plafonds par genre devenait **inférieure** au plafond global, ce dernier ne
    mordrait plus jamais — et le critère ne reposerait plus que sur la table par genre, qu'un
    nouveau genre peut oublier.
    """
    assert sum(PLAFOND_PAR_GENRE.values()) > PLAFOND_PAR_PARTIE


def test_plafond_global_borne_la_partie_quoi_quil_arrive():
    """**Le critère, simulé** : une partie entière ne produit jamais plus que le plafond fixé.

    On fait tourner la boucle d'une partie bavarde — tous les genres, cent fois, chaque notification
    aussitôt « lue » pour neutraliser l'anti-doublon (le cas le plus défavorable). On compte ce que
    les règles ont laissé passer : jamais plus de :data:`PLAFOND_PAR_PARTIE`.

    Échoue si l'on retire le plafond global : les plafonds par genre, eux, totalisent plus.
    """
    compteurs = Compteurs()
    emises = 0
    for tour in range(100):
        for genre in sorted(NOTIF_GENRES):
            decision = decider(
                genre, reglages=Reglages(), compteurs=compteurs, instant=EN_PLEIN_JOUR
            )
            if not decision.enregistrer:
                continue
            emises += 1
            par_genre = dict(compteurs.par_genre)
            par_genre[genre] = par_genre.get(genre, 0) + 1
            # `doublon_non_lu` reste faux : on simule un joueur qui lit tout immédiatement.
            compteurs = Compteurs(total_partie=emises, par_genre=par_genre)
        assert emises <= PLAFOND_PAR_PARTIE, f"plafond dépassé au tour {tour} : {emises}"
    assert emises == PLAFOND_PAR_PARTIE, "la partie bavarde doit atteindre le plafond, pas moins"


def test_le_genre_a_risque_est_le_plus_serre():
    """« C'est ton tour » — le risque nommé par la fiche — ne peut pas sonner à chaque coup.

    Quatre rappels sur une partie entière, pas un par tour : c'est ce qui évite que le joueur coupe
    les notifications au niveau du système (et perde alors *aussi* les invitations).
    """
    assert PLAFOND_PAR_GENRE[NOTIF_TON_TOUR] <= 4
    assert PLAFOND_PAR_GENRE[NOTIF_ADVERSAIRE_TROUVE] == 1
