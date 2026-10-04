"""Le **modèle** du langage d'effets — les structures figées d'un script compilé.

Module **pur** (aucune E/S). Un *script d'effet* est une donnée, pas du code : ces dataclasses
en sont la forme en mémoire, une fois **chargée et validée** (``chargement.charger_programme``).
Elles sont ``frozen`` et sérialisables en valeurs JSON natives (:meth:`Programme.en_json`) — ce
qui permet à un effet DSL de voyager dans :class:`~pbm_game.effets.pile.EffetEnAttente.params`
et d'être repris à l'identique après un F5 (lot ``j-effets-choix``).

**Ce module ne valide pas** : il *porte* la structure. La validation (op connu, cible cohérente,
version lisible, refus au chargement) vit dans ``chargement.py``, pour que la forme et sa police
restent séparées — on relit le modèle sans relire tout le validateur, et inversement.

Quatre briques :

* :class:`Selecteur` — *quelles* cartes/Pokémon une instruction vise (« mon Actif », « un
  Pokémon de base de ma pioche », « une carte Objet de ma défausse ») ;
* :class:`Condition` — ce qu'un ``si`` (ou un coût) teste (« si c'est face », « si l'adversaire
  a des cartes en main ») ;
* :class:`Instruction` — une **primitive** (:data:`~pbm_game.effets.dsl.vocabulaire.OPS`) ou une
  **structure de contrôle** (:data:`~pbm_game.effets.dsl.vocabulaire.CONTROLES`) ;
* :class:`Programme` — la **version**, un **coût** optionnel (payé d'abord, atomiquement) et la
  liste des effets.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Selecteur:
    """*Quelles* cartes/Pokémon une instruction vise, dans *quelle* zone et *de qui*.

    * ``zone`` — une des :data:`~pbm_game.effets.dsl.vocabulaire.ZONES` ;
    * ``proprietaire`` — ``moi`` / ``adversaire`` / ``les_deux`` (par rapport au joueur qui joue
      l'effet) ;
    * ``categorie`` — filtre de catégorie de carte (``pokemon``/``energie``/``dresseur``/``outil``),
      ``None`` = toutes ;
    * ``stade`` — filtre de stade des Pokémon (``base``/``stade1``/``stade2``), ``None`` = tous ;
    * ``nombre`` — combien en prendre (``None`` = **toutes** celles qui correspondent) ;
    * ``position`` — dans une zone **ordonnée** (pioche, défausse), d'où prendre : ``dessus``,
      ``dessous`` ou ``au_choix`` (le joueur / la stratégie décide).
    """

    zone: str
    proprietaire: str = "moi"
    categorie: str | None = None
    stade: str | None = None
    nombre: int | None = None
    position: str = "au_choix"

    def en_json(self) -> dict:
        """Le sélecteur en valeurs JSON natives (ne sérialise que les champs non défaut)."""
        donnees: dict = {"zone": self.zone, "proprietaire": self.proprietaire}
        if self.categorie is not None:
            donnees["categorie"] = self.categorie
        if self.stade is not None:
            donnees["stade"] = self.stade
        if self.nombre is not None:
            donnees["nombre"] = self.nombre
        if self.position != "au_choix":
            donnees["position"] = self.position
        return donnees


@dataclass(frozen=True)
class Condition:
    """Ce qu'un ``si`` (ou un coût) teste — un prédicat **pur** sur l'état et le contexte.

    * ``type`` — une des :data:`~pbm_game.effets.dsl.vocabulaire.CONDITIONS` ;
    * ``cible`` — le sélecteur sur lequel porte le test (``None`` pour un test sans cible, p. ex.
      ``resultat_pile``) ;
    * ``etat`` — l'état spécial attendu (pour ``a_etat``) ;
    * ``attendu`` — la face attendue ``face``/``pile`` (pour ``resultat_pile``) ;
    * ``minimum`` — le seuil (pour ``a_degats`` : au moins ``minimum`` compteurs) ;
    * ``type_pokemon`` — le **type** attendu de la cible (pour ``type_cible`` : « si le Défenseur
      est de type Eau… ») ; comparé aux métadonnées de catalogue du contexte, jamais deviné (D9).
    """

    type: str
    cible: Selecteur | None = None
    etat: str | None = None
    attendu: str | None = None
    minimum: int | None = None
    type_pokemon: str | None = None

    def en_json(self) -> dict:
        donnees: dict = {"type": self.type}
        if self.cible is not None:
            donnees["cible"] = self.cible.en_json()
        if self.etat is not None:
            donnees["etat"] = self.etat
        if self.attendu is not None:
            donnees["attendu"] = self.attendu
        if self.minimum is not None:
            donnees["minimum"] = self.minimum
        if self.type_pokemon is not None:
            donnees["type_pokemon"] = self.type_pokemon
        return donnees


@dataclass(frozen=True)
class Instruction:
    """Une **primitive** ou une **structure de contrôle** — l'unité d'un script.

    Un seul type porte les deux, parce qu'ils vivent dans la même liste d'instructions et se
    sérialisent pareil. Les champs non pertinents pour un ``op`` donné restent à leur défaut
    (le chargement refuse ceux qui n'ont pas de sens pour l'``op``, jamais un silence).

    * ``op`` — une des :data:`~pbm_game.effets.dsl.vocabulaire.INSTRUCTIONS` ;
    * ``cible`` — la cible principale (destination pour ``attacher``/``deplacer``) ;
    * ``source`` — l'origine pour ``deplacer`` (« de … vers … ») et ``attacher`` (d'où vient la
      carte attachée) ; sert aussi de **compteur dérivé** à ``repeter`` (« pour chaque … ») ;
    * ``nombre`` — un entier : cartes à piocher, compteurs à poser, dégâts à infliger, pièces à
      lancer, répétitions fixes ;
    * ``etat`` — l'état spécial pour ``poser_etat``/``retirer_etat`` ;
    * ``verrou`` / ``portee`` — le nom et la portée d'un ``empecher`` (cf.
      :mod:`pbm_game.effets.verrous`) ;
    * ``condition`` — le test d'un ``si`` ;
    * ``alors`` — le corps d'un ``repeter``, la branche « si vrai » d'un ``si``, ou la branche
      « **si face** » d'un ``pile_ou_face`` ;
    * ``sinon`` — la branche « si faux » d'un ``si``, ou la branche « **si pile** » d'un
      ``pile_ou_face`` ;
    * ``jusqu_a_echec`` — pour ``pile_ou_face`` : lancer une pièce **jusqu'au premier pile**
      (« lancez jusqu'à obtenir pile »), ``alors`` jouée une fois **par face** obtenue avant
      l'échec. Exclusif de ``nombre`` (qui fixe un nombre de pièces) ;
    * ``regle`` — l'identifiant ``R-x.y`` que l'instruction sert (facultatif, pour le journal).
    """

    op: str
    cible: Selecteur | None = None
    source: Selecteur | None = None
    nombre: int | None = None
    etat: str | None = None
    verrou: str | None = None
    portee: str | None = None
    condition: Condition | None = None
    alors: tuple[Instruction, ...] = ()
    sinon: tuple[Instruction, ...] = ()
    jusqu_a_echec: bool = False
    regle: str = ""

    def en_json(self) -> dict:
        donnees: dict = {"op": self.op}
        if self.cible is not None:
            donnees["cible"] = self.cible.en_json()
        if self.source is not None:
            donnees["source"] = self.source.en_json()
        if self.nombre is not None:
            donnees["nombre"] = self.nombre
        if self.etat is not None:
            donnees["etat"] = self.etat
        if self.verrou is not None:
            donnees["verrou"] = self.verrou
        if self.portee is not None:
            donnees["portee"] = self.portee
        if self.condition is not None:
            donnees["condition"] = self.condition.en_json()
        if self.alors:
            donnees["alors"] = [i.en_json() for i in self.alors]
        if self.sinon:
            donnees["sinon"] = [i.en_json() for i in self.sinon]
        if self.jusqu_a_echec:
            donnees["jusqu_a_echec"] = True
        if self.regle:
            donnees["regle"] = self.regle
        return donnees


@dataclass(frozen=True)
class Programme:
    """Un script d'effet **chargé et validé** : version, coût optionnel, liste d'effets.

    * ``version`` — la version du langage sous laquelle le script est écrit (``1`` …
      :data:`~pbm_game.effets.dsl.vocabulaire.DSL_VERSION`) ; l'interprète la connaît, donc un
      script v1 reste lisible quand v2 sort ;
    * ``cout`` — des instructions **payées d'abord**, de façon **atomique** : si le coût ne peut
      pas être payé (p. ex. défausser 2 cartes quand il n'y en a qu'une), le programme ne fait
      **rien** et le **dit** (jamais un demi-effet gratuit) ;
    * ``effets`` — la séquence d'instructions du corps de l'effet.
    """

    version: int
    effets: tuple[Instruction, ...]
    cout: tuple[Instruction, ...] = field(default_factory=tuple)

    def en_json(self) -> dict:
        """Le programme en valeurs JSON natives — l'inverse exact de ``charger_programme``."""
        donnees: dict = {"version": self.version, "effets": [i.en_json() for i in self.effets]}
        if self.cout:
            donnees["cout"] = [i.en_json() for i in self.cout]
        return donnees


__all__ = ["Selecteur", "Condition", "Instruction", "Programme"]
