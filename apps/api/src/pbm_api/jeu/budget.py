"""Le **budget de poids** d'une partie : combien d'octets d'images un plateau peut coûter, au pire.

Le risque que ce module borne est écrit dans la fiche du lot ``j-assets-pipeline`` : *« une partie
affiche jusqu'à 120 cartes. Sans pré-calcul et sans budget, le plateau se charge pendant une minute
sur un téléphone en 4G, et le jeu meurt là. »*

**Pourquoi un budget calculé plutôt que mesuré.** On pourrait relever le poids d'une partie réelle
et le noter dans un compte rendu. Ce chiffre vieillirait en une semaine : il suffit qu'une variante
gagne 30 % de qualité pour que le plateau double, sans qu'aucun test ne bronche. Ici, le poids est
une **conséquence arithmétique** des plafonds déclarés par :mod:`pbm_api.jeu.rendu_image`, lesquels
sont garantis en sortie de :func:`~pbm_api.jeu.rendu_image.fabriquer_image_jeu`. Changer une
largeur, une qualité ou un plafond change le total, et la CI refuse le dépassement
(``tests/test_jeu_assets_pipeline.py``). C'est la seule forme de budget qui tienne dans le temps.

**Ce qui compose le pire cas d'une partie** (:func:`poids_pire_cas_partie`) :

* les 120 cartes des deux decks, chacune en variante **plateau** — le pire cas est qu'elles
  défilent toutes (pioche, défausse, zone perdue, consultations) au cours de la partie ;
* **une** variante de zoom : le joueur zoome une carte à la fois, et le navigateur ne garde pas
  les précédentes en mémoire vive mais dans son cache HTTP (d'où l'empreinte posée par
  :mod:`pbm_api.http_images` : un zoom déjà vu ne repasse pas sur le réseau).

Les dos de cartes (pioche, récompenses, main adverse) ne comptent pas : ils sont **dessinés** par
l'écran (``CardBack``), zéro octet réseau — et les décors d'arène non plus, peints en dégradés CSS
par le lot ``j-arene-decors``.

**Et le pire cas de la mise en place** (:func:`poids_pire_cas_mise_en_place`), qui est l'autre
critère du lot : ce que le joueur doit avoir chargé **avant** d'avoir fini de poser ses Pokémon.
"""

from __future__ import annotations

from dataclasses import dataclass

from pbm_api.jeu.rendu_image import VARIANTE_PLATEAU, VARIANTE_ZOOM

#: Cartes d'un deck construit (``docs/jeu/REGLES.md`` R-1.2 : un deck fait exactement 60 cartes).
CARTES_PAR_DECK = 60

#: Cartes traversées par une partie, les deux decks réunis — les « jusqu'à 120 cartes » de la fiche.
CARTES_PAR_PARTIE = 2 * CARTES_PAR_DECK

#: Cartes **visibles** au plus fort de la mise en place : de mon côté l'actif, cinq de banc et sept
#: en main (13) ; du côté adverse l'actif et cinq de banc (6) — sa main et ses récompenses restent
#: des dos, donc zéro octet. On arrondit à 24 pour la marge d'une carte retournée entre-temps.
CARTES_MISE_EN_PLACE = 24

#: Le plafond d'une partie. 2,25 Mio : au-delà, un téléphone en 4G (≈ 200 Ko/s mesurés) y passerait
#: plus de onze secondes rien qu'en images, et le jeu redeviendrait celui qu'on refuse de livrer.
PLAFOND_PARTIE_OCTETS = 2304 * 1024

#: Le plafond de la mise en place. 512 Kio : ≈ 2,6 s en 4G, tenu pendant que le joueur pose ses
#: cartes — c'est ce qui rend vraie la promesse « on n'attend jamais devant un écran muet ».
PLAFOND_MISE_EN_PLACE_OCTETS = 512 * 1024


@dataclass(frozen=True)
class Poste:
    """Une ligne du budget : ce qu'on charge, en combien d'exemplaires, et pour quel poids."""

    quoi: str
    nombre: int
    octets_unite: int

    @property
    def octets(self) -> int:
        """Le poids total du poste."""
        return self.nombre * self.octets_unite


def postes_partie() -> tuple[Poste, ...]:
    """La composition du pire cas d'une partie, poste par poste — lisible dans un compte rendu."""
    return (
        Poste("cartes en variante plateau", CARTES_PAR_PARTIE, VARIANTE_PLATEAU.plafond_octets),
        Poste("zoom ouvert (une carte à la fois)", 1, VARIANTE_ZOOM.plafond_octets),
    )


def poids_pire_cas_partie() -> int:
    """Le poids d'images, en octets, qu'une partie peut coûter **au pire** à un joueur."""
    return sum(poste.octets for poste in postes_partie())


def poids_pire_cas_mise_en_place() -> int:
    """Le poids d'images à charger **avant la fin de la mise en place** — le jeu de pré-chargement.

    Toutes en variante plateau : la mise en place n'ouvre aucun zoom.
    """
    return CARTES_MISE_EN_PLACE * VARIANTE_PLATEAU.plafond_octets


def secondes_en_4g(octets: int, *, debit_octets_par_seconde: int = 200 * 1024) -> float:
    """Le temps de chargement de ``octets`` sur un lien 4G ordinaire, pour rendre un poids parlant.

    200 Ko/s est le débit utile retenu pour la 4G dans les conditions de test du lot (≈ 1,6 Mbit/s,
    le profil « Fast 4G » des outils de navigateur) : pas le débit d'affiche d'un opérateur, celui
    qu'on constate dans un train.
    """
    return octets / debit_octets_par_seconde


def depassements() -> tuple[str, ...]:
    """Les plafonds dépassés, en clair. Tuple vide = le budget est tenu.

    Rendu comme des phrases et non comme un booléen : c'est ce texte que la CI affiche quand elle
    refuse le dépassement, et un « assert False » n'aurait jamais dit lequel des deux plafonds a
    sauté ni de combien.
    """
    constats: list[str] = []
    partie = poids_pire_cas_partie()
    if partie > PLAFOND_PARTIE_OCTETS:
        constats.append(
            f"une partie coûte au pire {partie} o ({partie / 1024:.0f} Kio), "
            f"plafond {PLAFOND_PARTIE_OCTETS} o — dépassement de "
            f"{(partie - PLAFOND_PARTIE_OCTETS) / 1024:.0f} Kio"
        )
    mise_en_place = poids_pire_cas_mise_en_place()
    if mise_en_place > PLAFOND_MISE_EN_PLACE_OCTETS:
        constats.append(
            f"la mise en place coûte au pire {mise_en_place} o "
            f"({mise_en_place / 1024:.0f} Kio), plafond {PLAFOND_MISE_EN_PLACE_OCTETS} o — "
            f"dépassement de {(mise_en_place - PLAFOND_MISE_EN_PLACE_OCTETS) / 1024:.0f} Kio"
        )
    return tuple(constats)


def rapport() -> str:
    """Le budget en quelques lignes, pour un journal de CI ou un compte rendu de lot."""
    lignes = ["Budget de poids d'une partie (pire cas, borné par les plafonds de variantes) :"]
    for poste in postes_partie():
        lignes.append(
            f"  {poste.nombre:>4} × {poste.octets_unite / 1024:>5.1f} Kio  {poste.quoi}"
            f"  = {poste.octets / 1024:>7.1f} Kio"
        )
    partie = poids_pire_cas_partie()
    mise_en_place = poids_pire_cas_mise_en_place()
    lignes.append(
        f"  total partie       {partie / 1024:>7.1f} Kio "
        f"(plafond {PLAFOND_PARTIE_OCTETS / 1024:.0f} Kio, "
        f"{secondes_en_4g(partie):.1f} s en 4G)"
    )
    lignes.append(
        f"  dont mise en place {mise_en_place / 1024:>7.1f} Kio "
        f"(plafond {PLAFOND_MISE_EN_PLACE_OCTETS / 1024:.0f} Kio, "
        f"{secondes_en_4g(mise_en_place):.1f} s en 4G)"
    )
    for constat in depassements():
        lignes.append(f"  ⛔ {constat}")
    return "\n".join(lignes)


__all__ = [
    "CARTES_MISE_EN_PLACE",
    "CARTES_PAR_DECK",
    "CARTES_PAR_PARTIE",
    "PLAFOND_MISE_EN_PLACE_OCTETS",
    "PLAFOND_PARTIE_OCTETS",
    "Poste",
    "depassements",
    "poids_pire_cas_mise_en_place",
    "poids_pire_cas_partie",
    "postes_partie",
    "rapport",
    "secondes_en_4g",
]
