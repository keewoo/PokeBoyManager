"""L'**orchestration** d'un passage d'assistance IA — proposer, tester, contredire, décider (DJ8).

Ce module touche la base, le fournisseur IA et le grand livre : c'est l'**adaptateur** du lot, par
opposition au cœur pur (:mod:`.verification`, :mod:`.familles`, :mod:`.gabarit`, et les essais du
moteur). Il ne prend **aucune** décision de jeu lui-même : la porte DJ8 vit dans
:func:`pbm_api.jeu.scripts.assistance.verification.evaluer`.

Un passage, dans l'ordre (mission points 1 à 5) :

1. **sélectionner** les effets à couvrir, dans l'ordre de priorité DJ2 — d'abord ceux des cartes
   **possédées** par les joueurs, puis les plus **fréquents** ; jamais ceux déjà tranchés ;
2. pour chaque effet, sous réserve du **budget restant** : construire le prompt (texte + langage +
   exemples validés proches), demander une **proposition**, exécuter ses **tests** (moteur pur),
   puis — seulement si les tests passent — demander au **contradicteur** son verdict ;
3. appliquer la **porte** et **écrire** le registre (``scripte`` seulement si tests verts ET
   contradicteur approuve ; sinon ``non_supporte`` ou ``a_revoir``, nommé) ;
4. journaliser le **coût par carte** et s'arrêter net au **plafond** (sans redemander) ;
5. produire le **rapport par famille** (ce que JF lit, et où il peut retirer une famille) et les
   **mesures** (part acceptée sans retouche, part rejetée, coût par script validé).

Une interruption en cours de route ne perd rien : le grand livre est sauvé après **chaque** effet,
et un effet déjà tranché n'est jamais repris (reprise au grain de l'empreinte).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.jeu.scripts.assistance import budget as budget_mod
from pbm_api.jeu.scripts.assistance import pricing, verification
from pbm_api.jeu.scripts.assistance.budget import GrandLivre
from pbm_api.jeu.scripts.assistance.familles import famille as _famille_de_texte
from pbm_api.jeu.scripts.assistance.fournisseur import (
    GenerateurScript,
    parser_proposition,
    parser_verdict,
)
from pbm_api.jeu.scripts.assistance.gabarit import (
    ExempleValide,
    prompt_contradiction,
    prompt_proposition,
)
from pbm_api.jeu.scripts.assistance.verification import ResultatPorte
from pbm_api.jeu.scripts.depot import enregistrer_script, tous_les_scripts
from pbm_api.jeu.scripts.empreinte import effets_scriptables
from pbm_api.models import (
    Card,
    CardScript,
    CollectionItem,
    Deck,
    DeckCard,
    User,
)
from pbm_api.models.card_scripts import (
    SCRIPT_STATUT_NON_SUPPORTE,
    SCRIPT_STATUT_SCRIPTE,
)
from pbm_api.pricing.exchange_rates import convert_to_eur

#: Nombre d'exemples validés proches joints à chaque prompt de proposition (ancrage de la forme).
_MAX_EXEMPLES = 3


@dataclass(frozen=True)
class EffetCandidat:
    """Un texte d'effet à couvrir, avec de quoi le prioriser (DJ2) et le présenter à l'IA."""

    empreinte: str
    source_text: str
    lang: str | None
    origine: str
    intitule: str
    carte_nom: str
    demandeurs: int  # joueurs distincts qui possèdent une carte portant cet effet
    frequence: int  # nombre de cartes possédées qui portent cet effet
    frequence_catalogue: int = 0  # nombre de cartes du CATALOGUE qui portent cet effet (DJ2 : le
    # critère de départage « puis les plus fréquentes du catalogue », nul quand on ne regarde que
    # l'univers possédé local)


@dataclass
class EffetTraite:
    """Le compte rendu du traitement d'un effet — pour le rapport et le débogage."""

    empreinte: str
    carte_nom: str
    resultat: str
    famille: str
    confiance: str
    raison: str
    cost_eur: str


@dataclass
class RapportPassage:
    """Le résultat d'un passage : statut, compteurs, coûts, rapport par famille et mesures."""

    status: str  # "termine" | "budget_epuise" | "aucun_effet"
    effets_examines: int = 0
    scriptes: int = 0
    a_revoir: int = 0
    non_supportes: int = 0
    deja_traites: int = 0
    cost_eur_passage: str = "0"
    budget_restant_eur: str = "0"
    par_famille: dict[str, dict[str, int]] = field(default_factory=dict)
    mesures: dict[str, str] = field(default_factory=dict)
    traites: list[EffetTraite] = field(default_factory=list)


# --------------------------------------------------------------------- sélection des candidats


async def _univers_possede(
    db: AsyncSession,
) -> tuple[list[Card], dict[uuid.UUID, int], dict[uuid.UUID, int]]:
    """L'univers réel (cartes possédées par les joueurs du jeu + cartes de leurs decks), avec,
    par carte, le nombre de **joueurs** qui la possèdent et le nombre d'**exemplaires** — la base de
    la priorité DJ2 (possédées d'abord, puis fréquentes). Mesurer le catalogue entier serait
    flatteur et inutile, exactement comme pour la couverture (:mod:`.couverture`)."""
    joueur_ids = [
        uid
        for (uid,) in (
            await db.execute(select(User.id).where(User.game_access.is_(True)))
        ).all()
    ]
    joueurs_par_carte: dict[uuid.UUID, int] = {}
    exemplaires_par_carte: dict[uuid.UUID, int] = {}
    deck_card_ids: set[uuid.UUID] = set()
    if joueur_ids:
        for cid, n in (
            await db.execute(
                select(
                    CollectionItem.card_id,
                    func.count(func.distinct(CollectionItem.user_id)),
                )
                .where(CollectionItem.user_id.in_(joueur_ids))
                .group_by(CollectionItem.card_id)
            )
        ).all():
            joueurs_par_carte[cid] = n
        for cid, n in (
            await db.execute(
                select(CollectionItem.card_id, func.count())
                .where(CollectionItem.user_id.in_(joueur_ids))
                .group_by(CollectionItem.card_id)
            )
        ).all():
            exemplaires_par_carte[cid] = n
        for (cid,) in (
            await db.execute(
                select(func.distinct(DeckCard.card_id))
                .join(Deck, Deck.id == DeckCard.deck_id)
                .where(Deck.user_id.in_(joueur_ids))
            )
        ).all():
            deck_card_ids.add(cid)
    univers_ids = set(joueurs_par_carte) | deck_card_ids
    cartes: list[Card] = []
    if univers_ids:
        cartes = list(
            (await db.execute(select(Card).where(Card.id.in_(univers_ids)))).scalars()
        )
    return cartes, joueurs_par_carte, exemplaires_par_carte


def _nouvelle_entree(effet, card, *, demandeurs: int, frequence: int, freq_cat: int) -> dict:
    """Première rencontre d'une empreinte : son texte représentatif et ses compteurs DJ2."""
    return {
        "source_text": effet.texte,
        "origine": effet.origine,
        "intitule": effet.intitule,
        "carte_nom": getattr(card, "name", ""),
        "lang": getattr(card, "lang", None),
        "demandeurs": demandeurs,
        "frequence": frequence,
        "frequence_catalogue": freq_cat,
    }


async def _agreger_possedes(db: AsyncSession) -> dict[str, dict]:
    """Agrège les effets de l'**univers possédé local** (collections + decks des joueurs de CETTE
    base), avec les compteurs DJ2 locaux. C'est le chemin historique : une base de type PROD qui
    porte à la fois le catalogue et les collections (comme en test et comme le ferait un run direct
    sur la prod). ``frequence_catalogue`` reste 0 — on ne mesure pas le catalogue entier ici."""
    cartes, joueurs_par_carte, exemplaires_par_carte = await _univers_possede(db)
    agrege: dict[str, dict] = {}
    for card in cartes:
        joueurs = joueurs_par_carte.get(card.id, 0)
        exemplaires = exemplaires_par_carte.get(card.id, 0)
        for effet in effets_scriptables(card):
            entree = agrege.get(effet.empreinte)
            if entree is None:
                agrege[effet.empreinte] = _nouvelle_entree(
                    effet, card, demandeurs=joueurs, frequence=exemplaires, freq_cat=0
                )
            else:
                entree["demandeurs"] += joueurs
                entree["frequence"] += exemplaires
    return agrege


async def _agreger_catalogue(
    db: AsyncSession, priorite_tcgdex: Mapping[str, tuple[int, int]]
) -> dict[str, dict]:
    """Agrège les effets de **tout le catalogue** de CETTE base, en portant la priorité DJ2 par une
    table de possession extraite ailleurs (empreinte des comptes ``game_access`` de la PROD).

    C'est le chemin de la flotte : la base de travail est le **catalogue de référence**, qui porte
    les cartes mais **pas** les collections des joueurs (leurs UUID diffèrent d'ailleurs de ceux de
    la PROD). ``priorite_tcgdex`` fait le pont : une carte dont le ``tcgdex_id`` y figure reçoit ses
    compteurs de possession PROD (``demandeurs``/``frequence``), les autres ne comptent que par leur
    **fréquence catalogue** (nombre de cartes qui portent l'effet). L'ordre de tri réalise alors la
    priorité DJ2 à la lettre : possédées d'abord, **puis** les plus fréquentes du catalogue."""
    agrege: dict[str, dict] = {}
    for card in (await db.execute(select(Card))).scalars():
        tcgdex = getattr(card, "tcgdex_id", None) or ""
        demandeurs, exemplaires = priorite_tcgdex.get(tcgdex, (0, 0))
        for effet in effets_scriptables(card):
            entree = agrege.get(effet.empreinte)
            if entree is None:
                agrege[effet.empreinte] = _nouvelle_entree(
                    effet, card, demandeurs=demandeurs, frequence=exemplaires, freq_cat=1
                )
            else:
                entree["demandeurs"] += demandeurs
                entree["frequence"] += exemplaires
                entree["frequence_catalogue"] += 1
    return agrege


async def selectionner_effets(
    db: AsyncSession,
    *,
    limite: int,
    priorite_tcgdex: Mapping[str, tuple[int, int]] | None = None,
) -> list[EffetCandidat]:
    """Les textes d'effet à couvrir, ordonnés par priorité DJ2, hors effets déjà tranchés.

    Un effet déjà ``scripte`` ou ``non_supporte`` dans le registre est **décidé** : on ne le reprend
    pas (seuls ``a_revoir`` et les effets jamais vus restent candidats). Chaque empreinte n'apparaît
    qu'une fois (regroupement par texte), avec un texte représentatif et les compteurs DJ2 agrégés.

    Deux univers, selon ce que porte la base :

    * ``priorite_tcgdex`` fourni → univers = **catalogue entier** de la base, priorité de possession
      injectée depuis la PROD (chemin flotte, base = catalogue de référence) ;
    * ``priorite_tcgdex`` absent → univers = **possédé local** (chemin historique, base de type
      PROD portant collections et catalogue ; comportement et tests inchangés).
    """
    if priorite_tcgdex is not None:
        agrege = await _agreger_catalogue(db, priorite_tcgdex)
    else:
        agrege = await _agreger_possedes(db)

    registre = {
        emp: statut
        for emp, statut in (
            await db.execute(select(CardScript.text_fingerprint, CardScript.statut))
        ).all()
    }
    decides = {SCRIPT_STATUT_SCRIPTE, SCRIPT_STATUT_NON_SUPPORTE}

    candidats = [
        EffetCandidat(
            empreinte=emp,
            source_text=e["source_text"],
            lang=e["lang"],
            origine=e["origine"],
            intitule=e["intitule"],
            carte_nom=e["carte_nom"],
            demandeurs=e["demandeurs"],
            frequence=e["frequence"],
            frequence_catalogue=e["frequence_catalogue"],
        )
        for emp, e in agrege.items()
        if registre.get(emp) not in decides
    ]
    # Priorité DJ2 : d'abord les plus demandés (possédés par le plus de joueurs), puis les plus
    # fréquents parmi les possédées, puis les plus fréquents du **catalogue** ; le nom en dernier
    # pour un ordre stable (déterministe, donc reprise prévisible).
    candidats.sort(
        key=lambda c: (c.demandeurs, c.frequence, c.frequence_catalogue, c.carte_nom),
        reverse=True,
    )
    return candidats[:limite]


async def _exemples_proches(db: AsyncSession, candidat: EffetCandidat) -> list[ExempleValide]:
    """Quelques scripts déjà validés de la **même famille** que le candidat — pour ancrer la forme.

    Un exemple réel (texte + script accepté) vaut mieux qu'une grammaire seule : le modèle calque
    une forme qui marche. On n'en passe que de la même famille, pour rester pertinent.
    """
    famille_cible = _famille_de_texte(candidat.source_text, None)
    scriptes = [s for s in await tous_les_scripts(db) if s.statut == SCRIPT_STATUT_SCRIPTE]
    exemples: list[ExempleValide] = []
    for s in scriptes:
        if s.script is None:
            continue
        if _famille_de_texte(s.source_text, s.script) == famille_cible:
            exemples.append(ExempleValide(source_text=s.source_text, script=s.script))
        if len(exemples) >= _MAX_EXEMPLES:
            break
    return exemples


# ---------------------------------------------------------------------- traitement d'un effet


async def traiter_effet(
    db: AsyncSession,
    candidat: EffetCandidat,
    *,
    generateur: GenerateurScript,
    model: str,
    rate_usd_eur: Decimal | None,
) -> tuple[ResultatPorte, Decimal, Decimal, str]:
    """Traite un effet : propose → teste → (si vert) contredit → décide → écrit. Rend l'issue et
    le coût (USD, EUR) de ce qui a réellement été dépensé en jetons.

    Le contradicteur n'est appelé **que** si les tests sont verts : on ne paie pas une contradiction
    sur un script déjà faux (économie de budget, mission point 4). Le coût agrège les deux appels
    réellement faits, depuis l'usage facturé — jamais une estimation.
    """
    exemples = await _exemples_proches(db, candidat)
    prompt = prompt_proposition(
        texte_fr=candidat.source_text, texte_en=None, exemples=exemples
    )
    reponse, usage_prop = await generateur.generer(prompt)
    proposition = parser_proposition(reponse)

    cost_usd = pricing.cout_usd(
        model, input_tokens=usage_prop.input_tokens, output_tokens=usage_prop.output_tokens
    )

    # Premier passage de la porte : sans verdict (pour savoir si les tests sont verts).
    pre = verification.evaluer(
        texte_fr=candidat.source_text, proposition=proposition, verdict=None
    )
    verdict = None
    if pre.tests_ok and not proposition.non_supporte:
        prompt_c = prompt_contradiction(
            texte_fr=candidat.source_text,
            script=proposition.script,
            essais=proposition.essais,
        )
        reponse_c, usage_c = await generateur.generer(prompt_c)
        verdict = parser_verdict(reponse_c)
        cost_usd += pricing.cout_usd(
            model, input_tokens=usage_c.input_tokens, output_tokens=usage_c.output_tokens
        )

    porte = verification.evaluer(
        texte_fr=candidat.source_text, proposition=proposition, verdict=verdict
    )

    cost_eur = (
        convert_to_eur(cost_usd, rate_usd_eur)
        if (rate_usd_eur is not None and cost_usd > 0)
        else Decimal("0")
    )

    # Écriture du registre : scripté seulement si la porte le dit ; sinon nommé (non supporté / à
    # revoir), jamais joué « au mieux ». Les colonnes de revue (DJ8) portent la preuve de la porte.
    contradicteur_marque = (
        "approuve"
        if porte.contradicteur_ok is True
        else "rejete"
        if porte.contradicteur_ok is False
        else None
    )
    await enregistrer_script(
        db,
        source_text=candidat.source_text,
        statut=porte.resultat,
        dsl_version=(proposition.script or {}).get("version", 1),
        # On conserve le script proposé même en « à revoir » (pour la relecture) ; il est NULL
        # quand l'IA a déclaré l'effet non supporté (D9 : aucun programme deviné).
        script=proposition.script,
        lang=candidat.lang,
        author=f"assistance-ia:{model}",
        tests=proposition.essais if proposition.script else None,
        notes=porte.raison,
        review_tests_ok=porte.tests_ok,
        review_contradicteur=contradicteur_marque,
        famille=porte.famille,
        confidence=proposition.confiance,
        cost_eur=cost_eur,
    )
    return porte, cost_usd, cost_eur, proposition.confiance


# ---------------------------------------------------------------------------------- passage


async def run(
    db: AsyncSession,
    *,
    generateur: GenerateurScript,
    plafond_eur: Decimal,
    rate_usd_eur: Decimal | None,
    model: str,
    ledger_path: Path = budget_mod.DEFAULT_LEDGER_PATH,
    limite: int = 100,
    priorite_tcgdex: Mapping[str, tuple[int, int]] | None = None,
) -> RapportPassage:
    """Un passage complet, plafonné et reprenable. Voir la docstring du module pour le déroulé.

    S'arrête **net** au plafond, sans redemander (DJ8) : dès que le budget restant est épuisé, le
    passage se termine en ``budget_epuise`` avec ce qui a déjà été fait. Le grand livre est sauvé
    après chaque effet — une interruption reprend à l'exact endroit, sans rien retraiter.

    ``priorite_tcgdex`` (facultatif) : la priorité de possession extraite de la PROD, passée à
    :func:`selectionner_effets` (chemin flotte, base = catalogue de référence). Absent : univers
    possédé local (chemin historique).
    """
    livre = budget_mod.charger(ledger_path)
    candidats = await selectionner_effets(db, limite=limite, priorite_tcgdex=priorite_tcgdex)
    rapport = RapportPassage(status="termine")

    if not candidats:
        rapport.status = "aucun_effet"
        rapport.budget_restant_eur = str(livre.reste_eur(plafond_eur))
        _finaliser_mesures(rapport, livre)
        return rapport

    cost_passage = Decimal("0")
    for candidat in candidats:
        if livre.deja_traitee(candidat.empreinte):
            rapport.deja_traites += 1
            continue
        if livre.reste_eur(plafond_eur) <= 0:
            rapport.status = "budget_epuise"
            break

        porte, cost_usd, cost_eur, confiance = await traiter_effet(
            db, candidat, generateur=generateur, model=model, rate_usd_eur=rate_usd_eur
        )
        livre.enregistrer(
            empreinte=candidat.empreinte,
            resultat=porte.resultat,
            cost_usd=cost_usd,
            cost_eur=cost_eur,
            confiance=confiance,
            famille=porte.famille,
        )
        budget_mod.sauver(livre, ledger_path)

        cost_passage += cost_eur
        rapport.effets_examines += 1
        _compter(rapport, porte.resultat)
        _par_famille(rapport, porte.famille, porte.resultat)
        rapport.traites.append(
            EffetTraite(
                empreinte=candidat.empreinte,
                carte_nom=candidat.carte_nom,
                resultat=porte.resultat,
                famille=porte.famille,
                confiance=confiance,
                raison=porte.raison,
                cost_eur=str(cost_eur),
            )
        )

    rapport.cost_eur_passage = str(cost_passage)
    rapport.budget_restant_eur = str(livre.reste_eur(plafond_eur))
    _finaliser_mesures(rapport, livre)
    return rapport


def _compter(rapport: RapportPassage, resultat: str) -> None:
    if resultat == verification.GATE_SCRIPTE:
        rapport.scriptes += 1
    elif resultat == verification.GATE_NON_SUPPORTE:
        rapport.non_supportes += 1
    else:
        rapport.a_revoir += 1


def _par_famille(rapport: RapportPassage, famille: str, resultat: str) -> None:
    cle = (
        "scripte"
        if resultat == verification.GATE_SCRIPTE
        else "non_supporte"
        if resultat == verification.GATE_NON_SUPPORTE
        else "a_revoir"
    )
    ligne = rapport.par_famille.setdefault(
        famille, {"scripte": 0, "a_revoir": 0, "non_supporte": 0}
    )
    ligne[cle] += 1


def _finaliser_mesures(rapport: RapportPassage, livre: GrandLivre) -> None:
    """Les mesures de rendement (mission point 5), en pourcentages honnêtes (jamais arrondis pour
    flatter) : part acceptée sans retouche, part rejetée, coût par script validé."""
    avec_script = rapport.scriptes + rapport.a_revoir
    acceptees = (rapport.scriptes / avec_script * 100.0) if avec_script else 0.0
    rejetees = (rapport.a_revoir / avec_script * 100.0) if avec_script else 0.0
    rapport.mesures = {
        "acceptees_sans_retouche_pct": f"{acceptees:.2f}",
        "rejetees_pct": f"{rejetees:.2f}",
        "cout_par_script_valide_eur": str(livre.cout_par_carte_validee()),
        "total_depense_eur": livre.total_spent_eur,
    }


def rapport_texte(rapport: RapportPassage) -> str:
    """Rend le passage en texte lisible — le rapport par famille que JF lit (DJ8), + les mesures."""
    lignes: list[str] = []
    a = lignes.append
    a(f"=== Assistance IA — passage {rapport.status} ===")
    a(
        f"Effets examinés : {rapport.effets_examines} "
        f"(déjà traités, sautés : {rapport.deja_traites})"
    )
    a(
        f"  scriptés {rapport.scriptes} · à revoir {rapport.a_revoir} · "
        f"non supportés {rapport.non_supportes}"
    )
    a(f"Coût de ce passage : {rapport.cost_eur_passage} € · budget restant : "
      f"{rapport.budget_restant_eur} €")
    a("")
    a("-- Mesures de rendement --")
    for cle, val in rapport.mesures.items():
        a(f"  {cle} : {val}")
    a("")
    a("-- Rapport par famille (JF peut retirer une famille d'un mot) --")
    for famille in sorted(rapport.par_famille):
        c = rapport.par_famille[famille]
        a(f"  {famille:<16} scriptés {c['scripte']:>4} · à revoir {c['a_revoir']:>4} · "
          f"non supportés {c['non_supporte']:>4}")
    return "\n".join(lignes)


__all__ = [
    "EffetCandidat",
    "EffetTraite",
    "RapportPassage",
    "selectionner_effets",
    "traiter_effet",
    "run",
    "rapport_texte",
]
