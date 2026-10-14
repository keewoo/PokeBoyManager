"""Note de qualité d'une photo et variante de jeu — lot ``j-rendu-carte``.

Mission point 2 : « noter la qualité de chaque photo (netteté, luminosité, cadrage) et replier
automatiquement sous un seuil ». Point 4 : « une photo au flash ne doit pas rendre la carte
illisible sur le plateau ».

Les images sont **fabriquées ici** plutôt que lues sur disque : un test qui dépend d'une photo
versionnée se périme (et une vraie photo de carte n'a pas sa place dans le dépôt). Chaque cas isole
**un** défaut, et on vérifie l'ordre dans lequel les défauts sont nommés — le joueur doit recevoir
la consigne utile (« reprends la photo à la lumière »), pas un diagnostic complet.

Aucune E/S : ces fonctions sont pures, c'est tout l'intérêt (``docs/CODE.md``).
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from pbm_api.jeu.rendu_image import (
    HAUTEUR_JEU,
    LARGEUR_JEU,
    PhotoIndecodable,
    cle_image_jeu,
    decoder,
    fabriquer_image_jeu,
)
from pbm_api.jeu.rendu_qualite import (
    RAISON_BRULEE,
    RAISON_CADRAGE,
    RAISON_DELAVEE,
    RAISON_FLOUE,
    RAISON_SOMBRE,
    SEUIL_NETTETE,
    NotePhoto,
    noter_photo,
    part_dans_le_cadre,
)


def _carte_nette(luminosite: int = 150) -> np.ndarray:
    """Une « carte » synthétique nette : du contraste franc partout, comme texte et liseré.

    Un damier fin a exactement la propriété qui compte ici — beaucoup de hautes fréquences — donc
    une variance de Laplacien élevée, comme une photo nette de carte imprimée.
    """
    image = np.full((880, 630, 3), luminosite, dtype=np.uint8)
    image[::4, :, :] = max(0, luminosite - 110)
    image[:, ::4, :] = min(255, luminosite + 90)
    return image


def test_une_photo_nette_et_bien_eclairee_est_exploitable():
    note = noter_photo(_carte_nette())
    assert note.exploitable, note
    assert note.raison is None
    assert note.nettete > SEUIL_NETTETE


def test_une_photo_floue_est_refusee_et_nommee():
    """Le flou de bougé : le défaut le plus courant, et le plus invisible sur une vignette."""
    floue = cv2.GaussianBlur(_carte_nette(), (31, 31), 0)
    note = noter_photo(floue)
    assert not note.exploitable
    assert note.raison == RAISON_FLOUE
    assert note.nettete < SEUIL_NETTETE


def test_une_photo_trop_sombre_est_refusee():
    """Photo prise sans lumière : à la taille d'un plateau, le type et le texte disparaissent."""
    note = noter_photo(_carte_nette(luminosite=20))
    assert not note.exploitable
    assert note.raison == RAISON_SOMBRE


def test_le_reflet_du_flash_est_detecte_meme_avec_une_moyenne_normale():
    """Le défaut que la luminance moyenne **ne voit pas** — et c'est pour ça qu'on le mesure à part.

    Un flash brûle une zone de la carte en laissant la moyenne tout à fait acceptable : sans le
    compte des pixels saturés, cette photo passerait pour correcte et arriverait illisible sur le
    plateau (point 4 de la mission).
    """
    image = _carte_nette(luminosite=110)
    image[150:500, 100:550] = 255  # la tache du flash, ~28 % de l'image
    note = noter_photo(image)
    assert 55.0 < note.luminosite < 225.0, "la moyenne reste normale : c'est tout le piège"
    assert not note.exploitable
    assert note.raison == RAISON_BRULEE


def test_une_photo_delavee_est_refusee():
    note = noter_photo(_carte_nette(luminosite=245))
    assert not note.exploitable
    assert note.raison in {RAISON_DELAVEE, RAISON_BRULEE}


def test_une_carte_coupee_est_refusee_grace_au_cadrage_mesure_a_la_detection():
    """Le cadrage n'est pas mesuré sur l'image (elle est déjà redressée) : il est **reçu**."""
    note = noter_photo(_carte_nette(), crop_quality={"truncated": 0.4})
    assert not note.exploitable
    assert note.raison == RAISON_CADRAGE
    assert note.cadrage == pytest.approx(0.6)


def test_un_cadrage_inconnu_n_empeche_rien_et_n_est_pas_devine():
    """Un exemplaire sans détection (import, saisie manuelle) n'a pas de cadrage mesuré.

    On ne suppose **pas** qu'il est parfait (ce serait faire passer une carte coupée) ; on ne le
    refuse pas non plus pour autant : ``cadrage`` reste ``None`` et ne pèse sur rien (D9).
    """
    note = noter_photo(_carte_nette(), crop_quality=None)
    assert note.cadrage is None
    assert note.exploitable


def test_part_dans_le_cadre_lit_la_qualite_de_decoupe_ou_rend_none():
    assert part_dans_le_cadre({"truncated": 0.0}) == 1.0
    assert part_dans_le_cadre({"truncated": 0.25}) == pytest.approx(0.75)
    assert part_dans_le_cadre(None) is None
    assert part_dans_le_cadre({}) is None
    assert part_dans_le_cadre({"truncated": "n'importe quoi"}) is None


def test_une_image_vide_leve_plutot_que_de_rendre_une_note_par_defaut():
    """Pas de repli silencieux : une note inventée ferait jouer une carte qu'on n'a pas regardée."""
    with pytest.raises(ValueError):
        noter_photo(np.zeros((0, 0, 3), dtype=np.uint8))


def test_la_note_fait_l_aller_retour_json_sans_rien_perdre():
    note = noter_photo(cv2.GaussianBlur(_carte_nette(), (31, 31), 0))
    relue = NotePhoto.depuis_json(note.en_json())
    assert relue is not None
    assert relue.exploitable is False
    assert relue.raison == RAISON_FLOUE
    assert NotePhoto.depuis_json(None) is None


# --- La variante de jeu -------------------------------------------------------------------------


def test_la_variante_de_jeu_est_au_format_carte_et_bien_plus_legere():
    """Le risque nommé par la fiche : servir la photo d'origine pleine résolution.

    On compare les deux poids sur la même image — c'est le chiffre qui justifie la variante.
    """
    origine = cv2.imencode(".jpg", _carte_nette(), [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()
    variante = fabriquer_image_jeu(origine)

    relue = decoder(variante)
    assert relue.shape[1] == LARGEUR_JEU
    assert relue.shape[0] == HAUTEUR_JEU
    assert len(variante) < len(origine) / 2, (
        f"variante {len(variante)} o contre {len(origine)} o d'origine : "
        "la variante doit alléger franchement, sinon elle ne sert à rien"
    )


def test_une_photo_hors_ratio_est_recadree_et_non_deformee():
    """Une carte étirée se repère au premier coup d'œil : on coupe, on ne déforme pas."""
    carree = np.full((800, 800, 3), 120, dtype=np.uint8)
    variante = fabriquer_image_jeu(cv2.imencode(".png", carree)[1].tobytes())
    relue = decoder(variante)
    assert (relue.shape[1], relue.shape[0]) == (LARGEUR_JEU, HAUTEUR_JEU)


def test_une_photo_plus_petite_que_la_cible_n_est_pas_agrandie():
    """Agrandir n'ajoute aucun détail et ferait croire à une qualité que la photo n'a pas."""
    petite = np.full((200, 143, 3), 120, dtype=np.uint8)
    relue = decoder(fabriquer_image_jeu(cv2.imencode(".png", petite)[1].tobytes()))
    assert relue.shape[1] <= LARGEUR_JEU
    assert relue.shape[1] < LARGEUR_JEU


def test_une_photo_illisible_est_nommee_pas_avalee():
    with pytest.raises(PhotoIndecodable):
        decoder(b"ceci n'est pas une image")


def test_la_cle_de_variante_est_rangee_sous_son_proprietaire():
    """Un préfixe par compte : effacer un compte n'oblige pas à balayer tout le bucket."""
    import uuid

    user_id, item_id = uuid.uuid4(), uuid.uuid4()
    cle = cle_image_jeu(user_id, item_id)
    assert cle == f"jeu/rendu/{user_id}/{item_id}.webp"
    assert str(user_id) in cle
