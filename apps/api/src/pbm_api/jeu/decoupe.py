"""Détourage du Pokémon dans l'illustration de sa carte — la matière de l'apparition (DJ3).

Décision **DJ3** (JF, 15/10/2026) : *« l'apparition est fabriquée à partir de l'illustration de la
carte elle-même (découpe du Pokémon par segmentation, détourage, mise en volume, particules) :
aucune image nouvelle n'est introduite, ni sprite ni modèle officiel. »* Ce module est la première
moitié de cette décision — la découpe. La mise en volume et les particules vivent côté écran
(``apps/web/src/lib/game/anim-apparition.ts``), parce qu'elles ne coûtent rien à produire.

**Le module ne segmente pas lui-même : on lui passe un segmenteur.** C'est ce qui le garde pur —
ni réseau, ni modèle, ni fichier — donc testable en CI sans la dépendance de segmentation, qui est
optionnelle (:mod:`pbm_api.jeu.segmentation`). Les tests injectent un segmenteur déterministe ; la
chaîne de production injecte U²-Net.

⛔ **Une découpe douteuse est refusée, jamais publiée à moitié** (D9). Les six critères de
:class:`NoteDecoupe` sont nommés un par un : le message dit *lequel* a sauté, pas un score opaque.
Une carte sans découpe publiée n'a pas d'apparition, et son attaque joue l'effet de type générique
— c'est la dégradation prévue, et elle ne laisse aucun trou à l'écran.
"""

import io
from collections.abc import Callable
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from pbm_api.jeu.rendu_image import Variante

#: Type MIME d'une découpe. WebP **avec canal alpha** — c'est tout l'objet : un PNG pèserait trois
#: à cinq fois plus pour le même détourage, et le budget d'une partie ne le supporterait pas.
TYPE_MIME_APPARITION = "image/webp"

#: La découpe, telle qu'elle est servie. Plus étroite que le zoom (420 px) : à l'écran elle est
#: affichée au-dessus d'une carte d'arène, jamais en plein cadre, et son plafond doit tenir dans ce
#: qui reste du budget d'une partie (voir :mod:`pbm_api.jeu.budget`).
VARIANTE_APPARITION = Variante(nom="apparition", largeur=288, qualite=82, plafond_octets=40 * 1024)

#: Qualités de secours, dans l'ordre, quand la qualité nominale dépasse le plafond.
QUALITES_DE_SECOURS: tuple[int, ...] = (74, 66, 55)

#: La fenêtre d'illustration d'une carte, en fraction de sa largeur et de sa hauteur
#: ``(x0, y0, x1, y1)``. Volontairement **généreuse** en largeur : on ne cherche pas à détecter le
#: cadre (il change à chaque ère et un cadre mal détecté coupe une aile), on donne au segmenteur
#: une zone où le sujet est à coup sûr entier, et c'est lui qui tranche.
#:
#: ⚠️ Le bas est coupé à **52 %**, pas 57,5 %. La première version s'arrêtait plus bas « parce que
#: le texte des attaques commence encore en dessous » : c'était faux, et la planche de contrôle l'a
#: montré du premier coup. Sur les cartes du Base Set, la bande descriptive (« Pokémon Souris.
#: Taille : 0,8 m, poids : 30 kg ») tombe dans cette zone, et le segmenteur l'a trouvée plus
#: saillante que le Pokémon : la découpe de Raichu était **la ligne de texte**, proprement détourée.
FENETRE_ILLUSTRATION = (0.055, 0.075, 0.945, 0.52)

#: En dessous, le sujet est trop petit pour que l'apparition se voie : la segmentation a raté.
AIRE_MIN = 0.06
#: Au-dessus, c'est le fond qui a été gardé — mesuré à 0,62-0,68 sur les fonds holographiques du
#: Base Set quand on segmente par modèle de couleur (voir le compte rendu du lot).
AIRE_MAX = 0.55
#: Un détourage réussi suit une silhouette, donc un contour long : sa compacité est basse. Au-delà,
#: la « découpe » est un rectangle — c'est-à-dire la fenêtre d'illustration recopiée.
COMPACITE_MAX = 0.62
#: Part moyenne des quatre bords de la fenêtre occupée par le masque. Un sujet détouré ne touche
#: pas le cadre ; s'il le touche, c'est que du fond est resté accroché.
BORDS_MAX = 0.12
#: Une composante annexe qui pèse au moins ce quart de la principale compte comme un morceau à
#: part : une découpe en deux blocs (le sujet, et une traînée de fond) est refusée.
PART_MORCEAU = 0.15
#: Part de pixels d'alpha intermédiaire. Au-delà, le bord est vaporeux : la découpe « bave » sur le
#: fond et se verra comme un halo sale au-dessus de la carte.
FLOU_MAX = 0.22
#: Rapport largeur/hauteur au-delà duquel la découpe n'est plus une silhouette mais un **bandeau**.
#: Ce critère est né d'un vrai raté : avec une fenêtre trop basse, la découpe de Raichu était la
#: ligne « Pokémon Souris. Taille : 0,8 m, poids : 30 kg » — bien détourée, compacte, d'un seul
#: tenant, donc acceptée par tous les autres critères. Aucun Pokémon n'est quatre fois plus large
#: que haut, ni l'inverse.
ALLONGEMENT_MAX = 4.0

#: Rayon du lissage du bord alpha. Deux pixels suffisent à retirer l'escalier du masque sans
#: fabriquer le halo que :data:`FLOU_MAX` refuse.
LISSAGE_BORD = 5
#: Sous ce niveau, l'alpha est ramené à zéro : les queues de probabilité du segmenteur sont du
#: fond, et les garder revient à coller un voile translucide sur toute la fenêtre.
SEUIL_ALPHA = 40

#: Un segmenteur prend la fenêtre d'illustration en RGB et rend un alpha ``uint8`` de même taille.
Segmenteur = Callable[[np.ndarray], np.ndarray]


class IllustrationIndecodable(Exception):
    """L'illustration officielle ne se décode pas : on le dit, on ne découpe pas du vide."""


class ApparitionTropLourde(Exception):
    """Même à la qualité plancher, la découpe dépasse son plafond — donc elle n'est pas publiée."""


class DecoupeRefusee(Exception):
    """La découpe n'a pas passé les critères : la carte n'aura pas d'apparition, et on dit pourquoi.

    Porte la :class:`NoteDecoupe` complète : un refus doit être lisible sans relancer la chaîne.
    """

    def __init__(self, note: "NoteDecoupe") -> None:
        super().__init__(" ; ".join(note.refus))
        self.note = note


@dataclass(frozen=True)
class NoteDecoupe:
    """Ce que vaut une découpe, critère par critère — jamais un score unique qui noie un défaut.

    ``score`` existe pour **classer** des découpes entre elles (quelle vedette revoir en premier),
    pas pour les accepter : l'acceptation est ``exploitable``, et elle est la conjonction des six
    critères nommés. Une moyenne aurait laissé passer une découpe en deux morceaux au prétexte que
    son aire et son contour étaient bons.
    """

    moteur: str
    aire: float
    compacite: float
    bords: float
    morceaux: int
    flou: float
    allongement: float
    refus: tuple[str, ...]

    @property
    def exploitable(self) -> bool:
        """Vrai si aucun critère n'a sauté — la seule condition de publication."""
        return not self.refus

    @property
    def score(self) -> float:
        """Un repère de 0 à 1 pour trier les découpes acceptées, arrondi au centième.

        Récompense un contour détaillé (compacité basse), une silhouette d'un seul tenant et un
        bord net. N'entre **jamais** dans la décision d'accepter.
        """
        marge_compacite = max(0.0, (COMPACITE_MAX - self.compacite) / COMPACITE_MAX)
        marge_bord = max(0.0, (FLOU_MAX - self.flou) / FLOU_MAX)
        unite = 1.0 if self.morceaux <= 1 else 0.5
        return round(min(1.0, 0.5 * marge_compacite + 0.3 * marge_bord + 0.2 * unite), 2)

    def en_json(self) -> dict:
        """La note telle qu'elle est inscrite au registre des apparitions."""
        return {
            "moteur": self.moteur,
            "aire": round(self.aire, 3),
            "compacite": round(self.compacite, 3),
            "bords": round(self.bords, 3),
            "morceaux": self.morceaux,
            "flou": round(self.flou, 3),
            "allongement": round(self.allongement, 2),
            "score": self.score,
            "refus": list(self.refus),
        }


@dataclass(frozen=True)
class Apparition:
    """Une découpe publiable : ses octets WebP, sa taille affichée et sa note."""

    image: bytes
    largeur: int
    hauteur: int
    note: NoteDecoupe


def decoder(illustration: bytes) -> np.ndarray:
    """L'illustration officielle en RGB. Lève plutôt que de rendre un tableau vide."""
    try:
        with Image.open(io.BytesIO(illustration)) as source:
            return np.array(source.convert("RGB"))
    except Exception as exc:  # noqa: BLE001 — toute lecture ratée est le même incident
        raise IllustrationIndecodable(f"illustration illisible : {exc}") from exc


def fenetre_illustration(rgb: np.ndarray) -> np.ndarray:
    """La zone où se trouve le Pokémon, découpée dans la carte entière.

    Le cadrage est celui de :data:`FENETRE_ILLUSTRATION`.
    """
    hauteur, largeur = rgb.shape[:2]
    x0, y0, x1, y1 = FENETRE_ILLUSTRATION
    return rgb[int(y0 * hauteur) : int(y1 * hauteur), int(x0 * largeur) : int(x1 * largeur)]


def _plus_grande_composante(alpha: np.ndarray) -> tuple[np.ndarray, int]:
    """Ne garde que la silhouette principale, et dit combien de morceaux comptaient vraiment.

    Rend ``(alpha nettoyé, morceaux)``. Un morceau est une composante qui pèse au moins
    :data:`PART_MORCEAU` de la principale — en dessous, c'est du grain, pas un second sujet.
    """
    binaire = (alpha > 127).astype(np.uint8)
    nombre, etiquettes, stats, _ = cv2.connectedComponentsWithStats(binaire, 8)
    if nombre <= 1:
        return np.zeros_like(alpha), 0
    aires = stats[1:, cv2.CC_STAT_AREA]
    principale = 1 + int(np.argmax(aires))
    morceaux = int((aires >= PART_MORCEAU * aires.max()).sum())
    return np.where(etiquettes == principale, alpha, 0).astype(np.uint8), morceaux


def noter(alpha: np.ndarray, morceaux: int, *, moteur: str) -> NoteDecoupe:
    """Mesure les six critères et nomme ceux qui ont sauté.

    Chaque refus est une phrase complète : elle part telle quelle dans le journal de la chaîne et
    dans le registre, pour qu'on sache quoi regarder sans rouvrir l'image.
    """
    hauteur, largeur = alpha.shape[:2]
    plein = alpha > 127
    surface = float(plein.sum())
    aire = surface / float(hauteur * largeur)

    contours, _ = cv2.findContours(
        plein.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    perimetre = sum(cv2.arcLength(c, True) for c in contours) or 1.0
    compacite = float(4.0 * np.pi * surface / (perimetre * perimetre))

    bords = float(
        np.mean([plein[0, :].mean(), plein[-1, :].mean(), plein[:, 0].mean(), plein[:, -1].mean()])
    )
    intermediaires = float(((alpha > 64) & (alpha < 192)).sum())
    flou = intermediaires / surface if surface else 1.0

    lignes, colonnes = np.where(plein)
    if len(lignes):
        boite_h = float(lignes.max() - lignes.min() + 1)
        boite_l = float(colonnes.max() - colonnes.min() + 1)
        allongement = max(boite_l / boite_h, boite_h / boite_l)
    else:
        allongement = 0.0

    refus: list[str] = []
    if aire < AIRE_MIN:
        refus.append(f"sujet trop petit ({aire:.2f} de la fenêtre, minimum {AIRE_MIN})")
    if aire > AIRE_MAX:
        refus.append(f"le fond a été gardé ({aire:.2f} de la fenêtre, maximum {AIRE_MAX})")
    if compacite > COMPACITE_MAX:
        refus.append(f"découpe rectangulaire (compacité {compacite:.2f} > {COMPACITE_MAX})")
    if bords > BORDS_MAX:
        refus.append(f"la découpe touche le cadre ({bords:.2f} des bords > {BORDS_MAX})")
    if morceaux > 1:
        refus.append(f"découpe éclatée en {morceaux} morceaux")
    if flou > FLOU_MAX:
        refus.append(f"bord vaporeux ({flou:.2f} de pixels à demi transparents > {FLOU_MAX})")
    if allongement > ALLONGEMENT_MAX:
        refus.append(
            f"découpe en bandeau ({allongement:.1f}× plus longue que large, "
            f"maximum {ALLONGEMENT_MAX}) — c'est du texte, pas un Pokémon"
        )

    return NoteDecoupe(
        moteur=moteur,
        aire=aire,
        compacite=compacite,
        bords=bords,
        morceaux=morceaux,
        flou=flou,
        allongement=allongement,
        refus=tuple(refus),
    )


def encoder(rgba: Image.Image) -> bytes:
    """Encode la découpe en WebP alpha, **garantie sous le plafond** de la variante.

    Même mécanique que :func:`pbm_api.jeu.rendu_image.fabriquer_image_jeu`, et pour la même
    raison : c'est le plafond qui rend le poids d'une partie calculable, pas une moyenne constatée.
    Lève :class:`ApparitionTropLourde` si aucune qualité n'y suffit — la carte n'est alors pas
    publiée, et le journal le dit.
    """
    plafond = VARIANTE_APPARITION.plafond_octets
    dernier = b""
    for qualite in (VARIANTE_APPARITION.qualite, *QUALITES_DE_SECOURS):
        sortie = io.BytesIO()
        # `exact=False` laisse l'encodeur réutiliser les couleurs sous les pixels transparents :
        # elles sont invisibles, et les conserver coûterait des octets pour rien.
        rgba.save(sortie, format="WEBP", quality=qualite, method=4, exact=False)
        dernier = sortie.getvalue()
        if len(dernier) <= plafond:
            return dernier
    raise ApparitionTropLourde(
        f"découpe : {len(dernier)} o même à la qualité {QUALITES_DE_SECOURS[-1]}, "
        f"plafond {plafond} o"
    )


def decouper(illustration: bytes, segmenter: Segmenteur, *, moteur: str) -> Apparition:
    """Produit la découpe publiable du Pokémon de ``illustration``.

    Enchaîne : fenêtre d'illustration → segmentation → silhouette principale → note → cadrage au
    plus juste → encodage sous plafond. Lève :class:`DecoupeRefusee` si un critère a sauté, et
    :class:`ApparitionTropLourde` si la découpe ne rentre pas dans son budget. Dans les deux cas
    rien n'est publié : c'est la dégradation prévue (D9), pas une panne.
    """
    crop = fenetre_illustration(decoder(illustration))
    alpha = segmenter(crop)
    if alpha.shape[:2] != crop.shape[:2]:
        raise DecoupeRefusee(
            noter(np.zeros(crop.shape[:2], np.uint8), 0, moteur=moteur)
        )
    alpha = np.where(alpha < SEUIL_ALPHA, 0, alpha).astype(np.uint8)
    alpha, morceaux = _plus_grande_composante(alpha)
    note = noter(alpha, morceaux, moteur=moteur)
    if not note.exploitable:
        raise DecoupeRefusee(note)

    # Lissage APRÈS la note : la note juge la segmentation, pas le soin qu'on met à l'habiller.
    alpha = cv2.GaussianBlur(alpha, (LISSAGE_BORD, LISSAGE_BORD), 0)
    lignes, colonnes = np.where(alpha > 127)
    rgba = np.dstack([crop, alpha])[
        lignes.min() : lignes.max() + 1, colonnes.min() : colonnes.max() + 1
    ]
    image = Image.fromarray(rgba, "RGBA")
    if image.width > VARIANTE_APPARITION.largeur:
        hauteur = max(1, round(image.height * VARIANTE_APPARITION.largeur / image.width))
        image = image.resize((VARIANTE_APPARITION.largeur, hauteur), Image.LANCZOS)
    return Apparition(image=encoder(image), largeur=image.width, hauteur=image.height, note=note)


__all__ = [
    "AIRE_MAX",
    "AIRE_MIN",
    "BORDS_MAX",
    "COMPACITE_MAX",
    "FENETRE_ILLUSTRATION",
    "FLOU_MAX",
    "TYPE_MIME_APPARITION",
    "VARIANTE_APPARITION",
    "Apparition",
    "ApparitionTropLourde",
    "DecoupeRefusee",
    "IllustrationIndecodable",
    "NoteDecoupe",
    "Segmenteur",
    "decoder",
    "decouper",
    "encoder",
    "fenetre_illustration",
    "noter",
]
