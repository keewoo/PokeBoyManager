"""La décision DJ5, cas par cas — lot ``j-rendu-carte``.

« L'adversaire voit ce que le joueur a choisi de montrer ; un réglage "ne jamais montrer mes
photos" existe. » Ces tests fixent **l'ordre des verdicts** et les deux propriétés qui font la
valeur du réglage de confidentialité :

* le veto est évalué **avant** toute consultation de la photo — donc aucune URL de photo ne peut
  sortir par une erreur d'ordre ;
* la raison rendue à l'adversaire est **la même** qu'une photo existe ou non — sinon le refus
  lui-même révélerait que le joueur a photographié cette carte.

Tout est pur : aucune base, aucun HTTP (le câblage est testé dans ``test_jeu_rendu_routes`` et
``test_jeu_rendu_projection``).
"""

from __future__ import annotations

import uuid

from pbm_api.jeu.rendu import (
    RAISON_PAS_PRETE,
    RENDU_OFFICIELLE,
    RENDU_PHOTO,
    PhotoDeJeu,
    ReglagesRendu,
    choisir_rendu,
    decider_origine,
    preference_effective,
)
from pbm_api.jeu.rendu_qualite import (
    RAISON_CONFIDENTIALITE,
    RAISON_FLOUE,
    RAISON_PREFERENCE,
    RAISON_SANS_PHOTO,
    NotePhoto,
)

GAME = uuid.uuid4()
CARD = uuid.uuid4()
ITEM = uuid.uuid4()


def _note(exploitable: bool, raison: str | None = None) -> NotePhoto:
    return NotePhoto(
        nettete=200.0,
        luminosite=140.0,
        part_brulee=0.0,
        cadrage=1.0,
        exploitable=exploitable,
        raison=raison,
    )


def _photo(
    *, prete: bool = True, exploitable: bool = True, raison: str | None = None
) -> PhotoDeJeu:
    return PhotoDeJeu(item_id=ITEM, prete=prete, note=_note(exploitable, raison))


def _choisir(**kwargs):
    defauts = dict(
        card_id=CARD,
        photo=_photo(),
        reglages=ReglagesRendu(),
        preference_deck=None,
        pseudo_proprietaire="Aymeric",
        cest_moi=False,
        game_id=GAME,
    )
    return choisir_rendu(**{**defauts, **kwargs})


# --- Les défauts DJ5 ----------------------------------------------------------------------------


def test_par_defaut_on_joue_avec_ses_photos_et_l_adversaire_les_voit():
    """Le défaut tranché par JF : « oui par défaut côté joueur »."""
    rendu = _choisir()
    assert rendu is not None
    assert rendu.origine == RENDU_PHOTO
    # `?v=` nomme la variante (lot `j-assets-pipeline`) : le plateau pour la carte posée, le zoom
    # pour la carte agrandie. Servir la même aux deux coûtait 5,2 Mo par partie.
    assert rendu.url == f"/jeu/rendu/parties/{GAME}/photos/{ITEM}?v=plateau"
    assert rendu.url_zoom == f"/jeu/rendu/parties/{GAME}/photos/{ITEM}?v=zoom"
    assert rendu.raison is None


def test_les_defauts_du_code_et_ceux_de_la_base_disent_la_meme_chose():
    """Deux jeux de défauts qui divergent = un réglage qui change de sens selon qu'une ligne
    existe. On compare donc ``ReglagesRendu()`` aux ``server_default`` du modèle."""
    from pbm_api.models.jeu_rendu import JeuRenduReglages

    colonnes = JeuRenduReglages.__table__.columns
    defauts = ReglagesRendu()
    assert "'photo'" in str(colonnes["rendu_defaut"].server_default.arg)
    assert defauts.rendu_defaut == "photo"
    assert "false" in str(colonnes["jamais_montrer_mes_photos"].server_default.arg).lower()
    assert defauts.jamais_montrer_mes_photos is False


# --- Le veto de confidentialité -----------------------------------------------------------------


def test_le_veto_prive_l_adversaire_de_la_photo_mais_pas_son_proprietaire():
    """« Ce réglage te protège, il ne te prive de rien » : on ne punit pas qui se protège."""
    reglages = ReglagesRendu(jamais_montrer_mes_photos=True)
    vu_par_l_adversaire = _choisir(reglages=reglages, cest_moi=False)
    vu_par_moi = _choisir(reglages=reglages, cest_moi=True)
    assert vu_par_l_adversaire is not None and vu_par_moi is not None
    assert vu_par_l_adversaire.origine == RENDU_OFFICIELLE
    assert vu_par_l_adversaire.raison == RAISON_CONFIDENTIALITE
    assert vu_par_moi.origine == RENDU_PHOTO


def test_aucune_url_de_photo_n_est_emise_sous_veto_meme_dans_url_repli():
    """La garantie structurelle : l'identifiant d'exemplaire n'apparaît **nulle part**."""
    rendu = _choisir(reglages=ReglagesRendu(jamais_montrer_mes_photos=True))
    assert rendu is not None
    assert str(ITEM) not in (rendu.url + rendu.url_zoom + (rendu.url_repli or ""))
    assert str(ITEM) not in str(rendu.en_json())


def test_le_veto_ne_revele_pas_si_une_photo_existe():
    """La raison doit être **identique** avec et sans photo : sinon le refus est un aveu.

    C'est précisément pourquoi le veto est évalué avant de regarder la photo.
    """
    reglages = ReglagesRendu(jamais_montrer_mes_photos=True)
    avec = _choisir(reglages=reglages, photo=_photo())
    sans = _choisir(reglages=reglages, photo=None)
    assert avec is not None and sans is not None
    assert avec.raison == sans.raison == RAISON_CONFIDENTIALITE
    assert avec.en_json() == sans.en_json()


# --- Préférences : compte et deck ---------------------------------------------------------------


def test_la_preference_du_deck_l_emporte_sur_celle_du_compte():
    assert preference_effective(ReglagesRendu(), None) == RENDU_PHOTO
    assert preference_effective(ReglagesRendu(), RENDU_OFFICIELLE) == RENDU_OFFICIELLE
    assert (
        preference_effective(ReglagesRendu(rendu_defaut=RENDU_OFFICIELLE), RENDU_PHOTO)
        == RENDU_PHOTO
    )


def test_une_preference_inconnue_montre_moins_jamais_plus():
    """Base retouchée à la main, réglage d'une version future : en cas de doute, l'officielle."""
    assert preference_effective(ReglagesRendu(rendu_defaut="dos"), None) == RENDU_OFFICIELLE
    assert preference_effective(ReglagesRendu(), "n'importe quoi") == RENDU_OFFICIELLE


def test_choisir_l_officielle_le_dit_sans_accuser_la_photo():
    rendu = _choisir(preference_deck=RENDU_OFFICIELLE)
    assert rendu is not None
    assert rendu.origine == RENDU_OFFICIELLE
    assert rendu.raison == RAISON_PREFERENCE


# --- Le repli, et sa raison ---------------------------------------------------------------------


def test_sans_photo_on_joue_l_officielle_en_le_disant():
    """Critère d'acceptation : « une carte sans photo exploitable se joue avec l'image officielle,
    sans trou ni attente »."""
    rendu = _choisir(photo=None)
    assert rendu is not None
    assert rendu.origine == RENDU_OFFICIELLE
    assert rendu.url == f"/img/cards/{CARD}?size=low"
    assert rendu.url_zoom == f"/img/cards/{CARD}?size=high"
    assert rendu.raison == RAISON_SANS_PHOTO


def test_une_photo_inexploitable_replie_avec_la_raison_mesuree():
    """La raison vient de la **note**, pas d'un libellé générique : c'est elle que le joueur lit."""
    rendu = _choisir(photo=_photo(exploitable=False, raison=RAISON_FLOUE))
    assert rendu is not None
    assert rendu.origine == RENDU_OFFICIELLE
    assert rendu.raison == RAISON_FLOUE


def test_une_variante_pas_encore_prete_replie_sans_faire_attendre():
    """On ne fabrique pas d'image pendant une partie : on replie, et on le dit."""
    rendu = _choisir(photo=_photo(prete=False))
    assert rendu is not None
    assert rendu.origine == RENDU_OFFICIELLE
    assert rendu.raison == RAISON_PAS_PRETE


def test_une_photo_servie_porte_le_repli_officiel_pour_le_cas_degrade():
    """« Sans trou » tient jusque dans le cas dégradé : l'écran a de quoi afficher si la photo
    ne se charge pas. L'officielle est publique, donc ça ne révèle rien."""
    rendu = _choisir()
    assert rendu is not None
    assert rendu.url_repli == f"/img/cards/{CARD}?size=low"


# --- Crédit et carte inconnue -------------------------------------------------------------------


def test_le_credit_nomme_le_proprietaire_et_seulement_chez_l_adversaire():
    chez_l_adversaire = _choisir(cest_moi=False)
    chez_moi = _choisir(cest_moi=True)
    assert chez_l_adversaire is not None and chez_moi is not None
    assert chez_l_adversaire.credit == "photo de Aymeric"
    assert chez_moi.credit is None, "créditer mes propres cartes serait du bruit"


def test_sans_pseudo_le_credit_dit_quand_meme_que_c_est_la_carte_de_quelqu_un():
    rendu = _choisir(pseudo_proprietaire=None)
    assert rendu is not None
    assert rendu.credit == "photo de l'adversaire"


def test_une_carte_inconnue_du_catalogue_n_a_aucune_image_et_on_n_en_invente_pas():
    """D9 : pas même d'image officielle à proposer — l'écran retombe sur son repère texte."""
    assert _choisir(card_id=None) is None


# --- L'ordre des verdicts, en un seul endroit ---------------------------------------------------


def test_decider_origine_est_le_seul_ordre_de_verdicts_et_le_deck_passe_par_lui():
    """Le constructeur de deck et la vue de partie doivent dire **la même** chose.

    S'ils divergeaient, l'avertissement « ta photo est trop sombre » et ce que le joueur voit en
    jeu ne concorderaient plus, et aucun test de l'un ou de l'autre ne l'attraperait.
    """
    cas = [
        (dict(photo=None, reglages=ReglagesRendu(), preference_deck=None, cest_moi=True),
         (RENDU_OFFICIELLE, RAISON_SANS_PHOTO)),
        (dict(photo=_photo(), reglages=ReglagesRendu(), preference_deck=None, cest_moi=True),
         (RENDU_PHOTO, None)),
        (dict(photo=_photo(), reglages=ReglagesRendu(), preference_deck=RENDU_OFFICIELLE,
              cest_moi=True), (RENDU_OFFICIELLE, RAISON_PREFERENCE)),
        (dict(photo=_photo(), reglages=ReglagesRendu(jamais_montrer_mes_photos=True),
              preference_deck=None, cest_moi=False), (RENDU_OFFICIELLE, RAISON_CONFIDENTIALITE)),
    ]
    for entrees, attendu in cas:
        assert decider_origine(**entrees) == attendu, entrees
        # et la décision complète en dérive, elle ne la refait pas
        rendu = choisir_rendu(
            card_id=CARD, pseudo_proprietaire="Aymeric", game_id=GAME, **entrees
        )
        assert rendu is not None
        assert (rendu.origine, rendu.raison) == attendu
