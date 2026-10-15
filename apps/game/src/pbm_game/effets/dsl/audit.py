"""L'**audit de confidentialité** d'un script d'effet : ce programme peut-il faire fuir une carte ?

Module **pur** (aucune E/S), comme tout ``pbm_game``. Il ne joue rien : il *lit* un
:class:`~pbm_game.effets.dsl.modele.Programme` déjà chargé et répond à une question, une seule —
« en l'exécutant, le moteur publierait-il l'identité d'une carte qu'un joueur n'a pas le droit de
connaître ? »

**Pourquoi ce module existe.** La revue de sécurité du jeu (lot ``j-securite-jeu``) a trouvé la
fuite là où la fiche du lot annonçait qu'elle viendrait : non pas dans le moteur — dont la
projection par joueur est éprouvée sur mille états — mais dans ce qu'un **script de carte** peut
demander au moteur de faire. Le registre ``PROJECTEURS`` filtre par *type d'événement* ; il ne peut
pas filtrer ce qui, à l'intérieur d'un même type, dépend du **sélecteur** qu'un script a écrit. Deux
fuites de cette forme ont été corrigées dans le moteur (le ``choisir`` sur une zone cachée, le
``choix`` retenu d'une décision) ; il en reste une classe que le moteur **ne peut pas** projeter
correctement, et c'est celle-là qu'on refuse ici, au chargement, plutôt que de la jouer de travers.

**La classe refusée : ``chercher`` dans une zone cachée de l'adversaire.** ``chercher`` déplace les
cartes trouvées vers la **main** (zone cachée) *et* publie leurs ``ref`` — parce que le texte
imprimé des cartes de recherche dit « cherchez dans votre deck, **montrez-la** et ajoutez-la à votre
main » (R-5.2). La publication est donc juste pour la zone cachée de **son propre** propriétaire, et
fausse pour celle de l'adversaire : rien, dans « cherchez dans la main de votre adversaire », ne
donne le droit de montrer ces cartes au reste de la table.

**Pourquoi refuser plutôt que corriger.** Distinguer « déplacer » de « montrer » est une évolution
du *langage* d'effets (un paramètre ``montrer`` sur ``chercher``, et sa sémantique par carte) : une
décision de règles, qui appartient au lot des effets, pas à une revue de sécurité. Une revue qui
réécrirait la sémantique d'une primitive pour fermer une fuite ferait exactement ce que D9 interdit
— jouer une carte autrement que ce qu'elle dit. Alors on dit « je ne sais pas jouer cette carte
sans fuiter », on le dit **avant** la partie, et on nomme la raison.

**La table est exhaustive, et un test le prouve.** :data:`PUBLICATION_PAR_OP` classe **chaque**
primitive du vocabulaire selon ce qu'elle publie des identités qu'elle touche. Un ``op`` ajouté au
vocabulaire sans entrée ici fait casser ``test_audit_scripts`` — même garde que la parité des
projecteurs. C'est ce qui empêche la prochaine primitive d'arriver sans que personne ne se demande
ce qu'elle laisse voir.
"""

from __future__ import annotations

from dataclasses import dataclass

from .modele import Programme, Selecteur
from .vocabulaire import (
    OP_ANNULER,
    OP_ATTACHER,
    OP_CHANGER_ACTIF,
    OP_CHERCHER,
    OP_CHOISIR,
    OP_DEFAUSSER,
    OP_DEPLACER,
    OP_EMPECHER,
    OP_INFLIGER_DEGATS,
    OP_MELANGER,
    OP_PILE_OU_FACE,
    OP_PIOCHER,
    OP_POSER_COMPTEURS,
    OP_POSER_ETAT,
    OP_REGARDER,
    OP_RETIRER_ETAT,
    OP_REVELER,
    OP_SOIGNER,
    PROPRIO_MOI,
    ZONE_MAIN,
    ZONE_PIOCHE,
    ZONE_RECOMPENSES,
)

#: Les zones de cartes **cachées** (R-3.2, R-3.3, R-3.4) : main, pioche, récompenses. La défausse,
#: la zone perdue et le Stade sont face visible ; l'Actif et le banc sont en jeu, donc publics.
ZONES_CACHEES = frozenset({ZONE_MAIN, ZONE_PIOCHE, ZONE_RECOMPENSES})

# --- Ce que chaque primitive publie des identités qu'elle touche ---------------
#: La primitive ne publie **aucune** identité — au plus un nombre (``piocher``, ``regarder``), ou
#: elle n'agit que sur des cartes en jeu, donc déjà publiques.
PUBLIE_RIEN = "rien"
#: La primitive publie les ``ref`` des cartes touchées, et c'est **juste** : soit la zone de
#: destination est publique (``defausser`` → la défausse), soit montrer est l'effet lui-même
#: (``reveler``).
PUBLIE_A_BON_DROIT = "a_bon_droit"
#: La primitive publie les ``ref`` des cartes touchées **alors que** la destination est cachée : la
#: publication n'est légitime que pour la zone cachée de son propre propriétaire (le texte imprimé
#: de la carte dit « montrez-la »). Sur une zone cachée de l'adversaire, c'est une fuite.
PUBLIE_SI_CHEZ_SOI = "si_chez_soi"
#: La primitive ouvre une **décision** : les identités partent au destinataire, et le moteur les
#: cache quand l'ensemble lui est caché (``ensemble_cache_pour``). Rien à auditer ici — la garde est
#: dans le moteur, et elle est testée.
PUBLIE_PAR_DEMANDE = "par_demande"

#: Chaque primitive du vocabulaire et ce qu'elle publie. **Exhaustive** : un ``op`` de
#: :data:`~pbm_game.effets.dsl.vocabulaire.OPS` absent d'ici fait casser le test de parité,
#: pour qu'une primitive neuve n'arrive jamais sans qu'on ait tranché ce qu'elle laisse voir.
PUBLICATION_PAR_OP: dict[str, str] = {
    OP_PIOCHER: PUBLIE_RIEN,  # ne journalise que le nombre
    OP_REGARDER: PUBLIE_RIEN,  # ne journalise que le nombre regardé
    OP_MELANGER: PUBLIE_RIEN,
    OP_CHERCHER: PUBLIE_SI_CHEZ_SOI,  # publie les `ref`, destination = la main (cachée)
    OP_DEFAUSSER: PUBLIE_A_BON_DROIT,  # destination = la défausse, publique (R-3.6)
    OP_REVELER: PUBLIE_A_BON_DROIT,  # « montrez … » : publier EST l'effet
    OP_CHOISIR: PUBLIE_PAR_DEMANDE,
    OP_ATTACHER: PUBLIE_RIEN,  # énergies/Outils attachés : en jeu, donc publics
    OP_DEPLACER: PUBLIE_RIEN,
    OP_SOIGNER: PUBLIE_RIEN,
    OP_POSER_COMPTEURS: PUBLIE_RIEN,
    OP_INFLIGER_DEGATS: PUBLIE_RIEN,
    OP_PILE_OU_FACE: PUBLIE_RIEN,
    OP_CHANGER_ACTIF: PUBLIE_RIEN,  # Actif et banc sont publics
    OP_POSER_ETAT: PUBLIE_RIEN,
    OP_RETIRER_ETAT: PUBLIE_RIEN,
    OP_EMPECHER: PUBLIE_RIEN,
    OP_ANNULER: PUBLIE_RIEN,
}


@dataclass(frozen=True)
class Fuite:
    """Une fuite possible, nommée : l'``op`` fautif, la zone visée, et la raison en français."""

    op: str
    zone: str
    proprietaire: str
    raison: str


def _instructions(programme: Programme):
    """Toutes les instructions du programme, **coût compris**, en descendant dans les branches.

    Un ``si``/``repeter`` porte ses instructions en grappe : auditer la seule liste de surface
    laisserait passer un ``chercher`` niché dans une branche — le genre d'angle mort qui rend un
    audit rassurant et faux.
    """
    pile = list(programme.cout) + list(programme.effets)
    while pile:
        instr = pile.pop()
        yield instr
        pile.extend(instr.alors)
        pile.extend(instr.sinon)


def _publication_fuitante(selecteur: Selecteur | None) -> bool:
    """Publier les ``ref`` des cartes de ce sélecteur ferait-il fuir une information cachée ?

    Une zone **publique** (défausse, zone perdue, Stade, Actif, banc) ne fuite rien : ses cartes
    sont déjà sur la table. Restent les trois zones cachées, dont **une** admet la publication :

    * **sa propre pioche** — « Cherchez dans votre deck, **montrez-la** et ajoutez-la à votre
      main » (R-5.2) : montrer est écrit sur la carte, c'est donc l'effet, pas une fuite. C'est la
      forme de toutes les cartes de recherche du jeu (type Super Ball), et la garde ne doit pas les
      rendre injouables ;
    * **tout le reste** — sa propre main, ses propres récompenses, et les trois zones cachées de
      l'adversaire : rien, dans ces textes, ne donne le droit de montrer ces cartes à la table.

    ⚠️ Le cas « sa propre **main** » n'est pas un cas d'école : c'est le **balayage génératif** de
    ``test_securite_scripts_fuite`` qui l'a sorti, à la première exécution, alors que la règle
    écrite à la main ne regardait que le propriétaire (« chez l'adversaire »). Un ``chercher`` sur
    sa propre main publiait les ``ref`` de sa main à son adversaire. D'où la forme de cette
    fonction : on nomme ce qui est **autorisé**, et tout le reste fuite — l'inverse laisse toujours
    passer le cas qu'on n'avait pas imaginé.
    """
    if selecteur is None:
        return False
    if selecteur.zone not in ZONES_CACHEES:
        return False
    chez_soi = selecteur.proprietaire == PROPRIO_MOI
    return not (chez_soi and selecteur.zone == ZONE_PIOCHE)


def fuites(programme: Programme) -> list[Fuite]:
    """Les fuites d'information cachée que ``programme`` provoquerait — vide s'il est sûr.

    Ne lève pas : l'appelant décide quoi faire du verdict (le chargeur de l'API en fait un refus
    nommé, l'outil d'audit en fait une ligne de rapport).
    """
    trouvees: list[Fuite] = []
    for instr in _instructions(programme):
        publication = PUBLICATION_PAR_OP.get(instr.op)
        if publication != PUBLIE_SI_CHEZ_SOI:
            continue
        for selecteur in (instr.cible, instr.source):
            if not _publication_fuitante(selecteur):
                continue
            trouvees.append(
                Fuite(
                    op=instr.op,
                    zone=selecteur.zone,
                    proprietaire=selecteur.proprietaire,
                    raison=(
                        f"« {instr.op} » publie les `ref` des cartes touchées alors qu'il les "
                        f"déplace vers une zone cachée : sur la zone « {selecteur.zone} » de "
                        f"« {selecteur.proprietaire} », cela révélerait des cartes que personne "
                        f"n'a le droit de montrer (R-3.2/R-3.3/R-3.4). Seule « cherchez dans "
                        f"votre deck, montrez-la » est publiable, parce que la carte le dit"
                    ),
                )
            )
    return trouvees


def raison_de_refus(programme: Programme) -> str | None:
    """La raison, en une phrase, de refuser ``programme`` — ou ``None`` s'il ne fuit pas.

    Rédigée pour être lue par un joueur dans le constat « cette carte n'est pas jouable » : elle
    nomme la primitive et la zone, jamais un code interne.
    """
    trouvees = fuites(programme)
    if not trouvees:
        return None
    return (
        "script refusé par l'audit de confidentialité — "
        + " ; ".join(f.raison for f in trouvees)
        + " (jamais joué de travers, jamais joué en fuitant : D9)"
    )


def _verifier_table_exhaustive() -> None:
    """Garde d'import : la table couvre-t-elle tout le vocabulaire ?

    Appelée par le test de parité (pas à l'import, pour que le module reste sans effet de bord).
    """
    from .vocabulaire import OPS

    manquants = sorted(OPS - set(PUBLICATION_PAR_OP))
    if manquants:
        raise ValueError(
            f"Primitives non classées par l'audit de confidentialité : {manquants}. "
            f"Chaque `op` doit dire ce qu'il publie des identités qu'il touche."
        )


__all__ = [
    "PUBLICATION_PAR_OP",
    "PUBLIE_A_BON_DROIT",
    "PUBLIE_PAR_DEMANDE",
    "PUBLIE_RIEN",
    "PUBLIE_SI_CHEZ_SOI",
    "ZONES_CACHEES",
    "Fuite",
    "fuites",
    "raison_de_refus",
]
