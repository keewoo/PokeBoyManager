"""Le segmenteur qui détoure un Pokémon : U²-Net, exécuté par ONNX Runtime.

Ce module est **l'unique endroit** où le projet dépend d'un modèle appris, et cette dépendance est
**optionnelle** : elle n'est pas installée en CI et ne doit jamais l'être. Le module de découpe
(:mod:`pbm_api.jeu.decoupe`) reçoit un segmenteur en paramètre, donc il se teste sans rien de tout
ça ; seule la chaîne de production (``scripts/decouper_apparitions.py``) vient ici.

    uv sync --extra decoupe        # installe onnxruntime
    uv run python scripts/decouper_apparitions.py --telecharger-modele

**Pourquoi un modèle appris, et pas une segmentation par couleur.** La question a été tranchée par
la mesure, pas par principe. GrabCut (OpenCV, déjà présent, zéro dépendance) a été éprouvé sur six
illustrations réelles, en initialisation par rectangle puis par masque : sur les fonds
holographiques du Base Set il **garde le fond entier** — aire 0,62 à 0,68 de la fenêtre et
compacité 0,76 à 0,79, c'est-à-dire un rectangle. Le fond d'une illustration peinte est aussi
coloré et aussi texturé que le Pokémon : un modèle de mélange de couleurs ne peut pas les séparer.
U²-Net, sur les mêmes six images, ramène l'aire à 0,12-0,44 et la compacité à 0,14-0,42.

⛔ **GrabCut n'a donc pas été gardé comme repli.** Un repli qui produit des découpes qu'on sait
mauvaises est un repli silencieux : les vedettes seraient publiées avec un carré de fond collé
au-dessus de la carte. Sans modèle, la chaîne **s'arrête et le dit** ; les cartes restent sans
apparition et jouent l'effet de type générique, ce qui est la dégradation prévue (D9).

Le modèle retenu est **u2netp**, la variante légère (4,6 Mo) : elle tient dans un cache local, se
télécharge en quelques secondes même sur le lien bridé de chimera, et sa qualité sur ces
illustrations est suffisante — le juge final reste la note de :mod:`pbm_api.jeu.decoupe`, qui
refuse ce que le modèle a raté.
"""

import hashlib
import os
from pathlib import Path

import cv2
import numpy as np

#: D'où vient le modèle. Dépôt public du projet rembg, qui publie les poids U²-Net originaux.
URL_MODELE = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx"

#: Empreinte SHA-256 des poids attendus. Vérifiée à chaque chargement : un modèle qui change sous
#: nos pieds changerait les découpes sans que rien ne le dise, et le registre des apparitions
#: cesserait de décrire ce qui est réellement servi.
EMPREINTE_MODELE = "309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8"

#: Nom du moteur, inscrit dans la note de chaque découpe et dans le registre.
NOM_MOTEUR = "u2netp"

#: Côté de l'entrée du réseau. Imposé par le modèle, pas un réglage.
COTE_ENTREE = 320

#: Normalisation ImageNet, celle avec laquelle U²-Net a été entraîné.
MOYENNE = (0.485, 0.456, 0.406)
ECART_TYPE = (0.229, 0.224, 0.225)


class ModeleIndisponible(Exception):
    """Le modèle ou son moteur d'exécution manque : la chaîne s'arrête en nommant ce qu'il faut."""


def chemin_modele() -> Path:
    """Où le modèle est attendu : ``PBM_MODELE_SEGMENTATION`` prime, sinon le cache utilisateur."""
    depuis_env = os.environ.get("PBM_MODELE_SEGMENTATION")
    if depuis_env:
        return Path(depuis_env)
    return Path.home() / ".cache" / "pbm" / "u2netp.onnx"


def verifier_empreinte(chemin: Path) -> None:
    """Refuse un modèle dont les poids ne sont pas ceux attendus."""
    empreinte = hashlib.sha256(chemin.read_bytes()).hexdigest()
    if empreinte != EMPREINTE_MODELE:
        raise ModeleIndisponible(
            f"empreinte inattendue pour {chemin} : {empreinte} au lieu de {EMPREINTE_MODELE}. "
            "Le fichier n'est pas le modèle avec lequel les découpes publiées ont été produites."
        )


def charger_segmenteur(chemin: Path | None = None):
    """Rend un segmenteur prêt pour :func:`pbm_api.jeu.decoupe.decouper`.

    L'import d'``onnxruntime`` est **paresseux** : importer ce module ne doit jamais imposer la
    dépendance optionnelle à qui ne segmente pas. Toute absence lève
    :class:`ModeleIndisponible` avec la commande qui la répare — jamais un repli muet.
    """
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise ModeleIndisponible(
            "onnxruntime n'est pas installé — `uv sync --extra decoupe` dans apps/api. "
            "La chaîne de découpe ne se replie pas sur une segmentation dégradée (D9)."
        ) from exc

    cible = chemin or chemin_modele()
    if not cible.exists():
        raise ModeleIndisponible(
            f"modèle absent de {cible} — "
            "`uv run python scripts/decouper_apparitions.py --telecharger-modele`"
        )
    verifier_empreinte(cible)

    session = ort.InferenceSession(str(cible), providers=["CPUExecutionProvider"])
    nom_entree = session.get_inputs()[0].name

    def segmenter(rgb: np.ndarray) -> np.ndarray:
        """L'alpha brut du sujet, à la taille de ``rgb`` — le seuillage revient à l'appelant."""
        reduit = cv2.resize(rgb, (COTE_ENTREE, COTE_ENTREE), interpolation=cv2.INTER_AREA)
        normalise = (reduit.astype(np.float32) / 255.0 - np.array(MOYENNE, np.float32)) / np.array(
            ECART_TYPE, np.float32
        )
        entree = normalise.transpose(2, 0, 1)[None]
        sortie = session.run(None, {nom_entree: entree})[0][0, 0]
        # U²-Net rend une saillance non bornée : on la ramène sur [0, 1] image par image, sinon une
        # illustration très contrastée et une illustration pâle n'auraient pas le même seuil.
        etendue = float(sortie.max() - sortie.min())
        saillance = (sortie - sortie.min()) / (etendue if etendue > 1e-6 else 1.0)
        return cv2.resize(
            (saillance * 255).astype(np.uint8),
            (rgb.shape[1], rgb.shape[0]),
            interpolation=cv2.INTER_LINEAR,
        )

    return segmenter


def telecharger_modele(destination: Path | None = None) -> Path:
    """Télécharge les poids et vérifie leur empreinte avant de les garder.

    Écrit d'abord à côté puis renomme : un téléchargement coupé ne doit pas laisser un modèle
    tronqué que le prochain passage prendrait pour valide.
    """
    import httpx

    cible = destination or chemin_modele()
    cible.parent.mkdir(parents=True, exist_ok=True)
    partiel = cible.with_suffix(".partiel")
    with httpx.stream("GET", URL_MODELE, follow_redirects=True, timeout=120.0) as reponse:
        reponse.raise_for_status()
        with partiel.open("wb") as sortie:
            for morceau in reponse.iter_bytes():
                sortie.write(morceau)
    try:
        verifier_empreinte(partiel)
    except ModeleIndisponible:
        partiel.unlink(missing_ok=True)
        raise
    partiel.replace(cible)
    return cible


__all__ = [
    "COTE_ENTREE",
    "EMPREINTE_MODELE",
    "NOM_MOTEUR",
    "URL_MODELE",
    "ModeleIndisponible",
    "charger_segmenteur",
    "chemin_modele",
    "telecharger_modele",
    "verifier_empreinte",
]
