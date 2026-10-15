"""Non-fuite des **scripts de cartes** — revue de sécurité du jeu, lot ``j-securite-jeu``.

La non-fuite du *moteur* était déjà prouvée (``test_sortie_projection`` : 1 000 états, aucun
identifiant caché dans la sortie d'un joueur). Ce fichier prouve l'autre moitié, celle que la fiche
du lot désignait comme le vrai risque : **ce qu'un script de carte peut faire publier au moteur**.

Trois raisons de ne pas se contenter d'énumérer les scripts livrés :

1. le corpus réel vit en base (``card_scripts``, 94 scripts au 14/10/2026), **pas dans le dépôt** :
   un test qui lirait une liste figée serait vert sur six scripts et muet sur les quatre-vingt-huit
   autres — une CI verte sur rien ;
2. le corpus **grandit** à chaque passe de génération : la garde doit couvrir le script n°95 sans
   qu'on y repense ;
3. une fuite ne vient pas d'un script en particulier, elle vient d'une **combinaison** primitive ×
   zone × propriétaire que personne n'avait exercée.

Donc la garde est **structurelle** : on balaie le produit cartésien des primitives du vocabulaire,
des neuf zones et des trois propriétaires, on exécute, et on projette chaque événement produit pour
**les deux** joueurs — en interdisant toute identité (``instance_id`` *et* ``ref``) d'une zone
cachée à son destinataire. Ce qui est refusé par l'audit de confidentialité est compté et nommé,
jamais sauté en silence.

Les deux fuites réelles trouvées par la revue ont leur test nommé en fin de fichier : elles
échouent sans le correctif (c'est le « test qui mord » exigé par ``docs/CODE.md``).
"""

from __future__ import annotations

import json

import pytest
from fabrique_dsl import carte, contexte, etat, joueur, pokemon, rng

from pbm_game.demandes.modele import CAT_CARTE, DemandeDecision, Reponse
from pbm_game.demandes.moteur import (
    EVT_DEMANDE_REPONDUE,
    demarrer_resolution,
    repondre,
)
from pbm_game.effets.dsl import charger_programme, executer_programme
from pbm_game.effets.dsl.audit import (
    PUBLICATION_PAR_OP,
    ZONES_CACHEES,
    _verifier_table_exhaustive,
    fuites,
    raison_de_refus,
)
from pbm_game.effets.dsl.chargement import ProgrammeInvalide
from pbm_game.effets.dsl.execution import ensemble_cache_pour, strategie_demande
from pbm_game.effets.dsl.selection import CibleCarte, CiblePokemon
from pbm_game.effets.dsl.vocabulaire import OPS, PROPRIETAIRES, ZONES
from pbm_game.effets.pile import EffetEnAttente, PileEffets, SourceEffet
from pbm_game.rng import Rng
from pbm_game.sortie import projeter_evenement

# Les cartes cachées portent des `ref` reconnaissables : si l'une apparaît dans une projection
# destinée à l'autre joueur, le test la nomme au lieu de dire « ça a fuité quelque part ».
_SECRET_MAIN = "secret-main"
_SECRET_PIOCHE = "secret-pioche"
_SECRET_RECOMPENSE = "secret-recompense"


def _joueur_garni(jid: str, marque: str):
    """Un joueur dont **chaque zone cachée** porte des cartes marquées, et les zones publiques non.

    Les zones publiques (défausse, zone perdue) reçoivent des cartes banales : une fuite ne doit pas
    être confondue avec la publication, légitime, d'une carte visible.
    """
    return joueur(
        jid,
        actif=pokemon(f"{jid}-actif"),
        banc=(pokemon(f"{jid}-banc"),),
        main=(
            carte(f"{jid}-m1", f"{_SECRET_MAIN}-{jid}-1"),
            carte(f"{jid}-m2", f"{_SECRET_MAIN}-{jid}-2"),
        ),
        pioche=tuple(
            carte(f"{jid}-p{i}", f"{_SECRET_PIOCHE}-{jid}-{i}") for i in range(4)
        ),
        recompenses=tuple(
            carte(f"{jid}-r{i}", f"{_SECRET_RECOMPENSE}-{jid}-{i}") for i in range(3)
        ),
        defausse=(carte(f"{jid}-d1", f"public-defausse-{jid}"),),
        zone_perdue=(carte(f"{jid}-z1", f"public-perdue-{jid}"),),
    )


def _interdits_pour(etat_partie, destinataire: str) -> set[str]:
    """``instance_id`` et ``ref`` que ``destinataire`` n'a **pas** le droit de lire.

    Même frontière que ``test_sortie_projection._ids_interdits``, et pour la même raison : les
    pioches et les récompenses des **deux** joueurs sont cachées (une récompense l'est même à son
    propriétaire, R-3.4), la main ne l'est qu'à l'autre (R-3.3).
    """
    interdits: set[str] = set()
    for j in etat_partie.joueurs:
        for c in j.pioche:
            interdits |= {c.instance_id, c.ref}
        for c in j.recompenses:
            interdits |= {c.instance_id, c.ref}
        if j.id != destinataire:
            for c in j.main:
                interdits |= {c.instance_id, c.ref}
    return interdits


def _reveles_a_bon_droit(evenements) -> set[str]:
    """Les ``ref`` qu'un effet avait le **droit** de publier — l'exemption, et elle est étroite.

    Un script qui a passé l'audit de confidentialité ne peut publier des ``ref`` que par trois
    chemins, tous sanctionnés par une règle : « cherchez dans votre deck, **montrez-la** » (R-5.2),
    « **montrez** … » (``reveler``, où montrer *est* l'effet) et « défaussez … » (la défausse est
    face visible, R-3.6). Ces cartes cessent d'être cachées **par l'effet lui-même**.

    Deux garde-fous à cette exemption, parce qu'une exemption trop large est exactement ce qui a
    laissé les trois fuites passer jusqu'ici :

    * elle ne porte que sur des ``ref``, **jamais** sur un ``instance_id`` — aucune des trois
      primitives n'en publie, et le test échoue si l'une s'y met (``assert`` ci-dessous) ;
    * elle ne s'applique qu'aux programmes **déjà jugés sûrs** par l'audit : un ``chercher`` dans la
      main de l'adversaire n'arrive jamais jusqu'ici, il est refusé en amont.
    """
    reveles: set[str] = set()
    for evenement in evenements:
        donnees = evenement.donnees
        if not isinstance(donnees, dict) or "refs" not in donnees:
            continue
        assert "instance_ids" not in donnees, (
            f"{evenement.type} publie des `instance_id` : l'exemption de révélation ne couvre "
            f"que des `ref` — {donnees}"
        )
        reveles |= set(donnees["refs"])
    return reveles


def _programmes_balayage() -> list[tuple[str, dict]]:
    """Le produit cartésien primitive × zone × propriétaire, en scripts d'une instruction.

    Chaque primitive est tentée avec un sélecteur sur chacune des neuf zones et chacun des trois
    propriétaires. Les paramètres annexes (``nombre``, ``etat``, ``verrou``, ``portee``) sont posés
    au plus large : on cherche à **exécuter**, pas à écrire une carte sensée.
    """
    annexes = {
        "poser_etat": {"etat": "empoisonne"},
        "retirer_etat": {"etat": "empoisonne"},
        "empecher": {"verrou": "ne_peut_attaquer", "portee": "ce_tour"},
    }
    cas: list[tuple[str, dict]] = []
    for op in sorted(OPS):
        for zone in sorted(ZONES):
            for proprietaire in sorted(PROPRIETAIRES):
                instr: dict = {
                    "op": op,
                    "nombre": 1,
                    "cible": {"zone": zone, "proprietaire": proprietaire, "nombre": 1},
                }
                instr.update(annexes.get(op, {}))
                if op == "choisir":  # un `choisir` sans corps ne produit rien d'observable
                    instr["alors"] = [{"op": "melanger"}]
                etiquette = f"{op}/{zone}/{proprietaire}"
                cas.append((etiquette, {"version": 1, "effets": [instr]}))
    return cas


def test_la_table_d_audit_couvre_tout_le_vocabulaire():
    """Une primitive ajoutée sans dire ce qu'elle publie fait **casser** ce test (parité).

    Même garde que ``test_parite_evenements_projecteurs`` pour les projecteurs : c'est ce qui
    empêche la prochaine primitive d'arriver sans que personne ne se demande ce qu'elle laisse voir.
    """
    _verifier_table_exhaustive()
    assert set(PUBLICATION_PAR_OP) >= OPS


def test_balayage_des_scripts_ne_fuit_aucune_carte_cachee():
    """Toute combinaison primitive × zone × propriétaire : rien de caché n'atteint l'autre joueur.

    C'est la garde qui couvre les scripts **non versionnés** (les 94 de la base) et ceux à venir :
    elle ne juge pas des scripts, elle juge le *langage* dans lequel ils sont écrits.
    """
    executes = 0
    refuses_par_l_audit: list[str] = []
    refuses_par_le_langage: list[str] = []

    for etiquette, source in _programmes_balayage():
        try:
            programme = charger_programme(source)
        except ProgrammeInvalide:
            # Combinaison hors langage (zone incompatible avec la primitive) : le chargeur la refuse
            # déjà, elle ne peut donc pas être écrite dans un script. On la compte.
            refuses_par_le_langage.append(etiquette)
            continue
        if raison_de_refus(programme) is not None:
            # L'audit de confidentialité la refuse : un script qui la contient n'est jamais chargé
            # en partie (le chargeur de l'API en fait un refus nommé). On la compte aussi.
            refuses_par_l_audit.append(etiquette)
            continue

        alice, bob = _joueur_garni("alice", "a"), _joueur_garni("bob", "b")
        depart = etat(alice, bob)
        try:
            resultat = executer_programme(
                depart, programme, contexte("alice", "bob"), rng()
            )
        except ValueError:
            # Une primitive peut refuser l'état de départ (zone non gérée par la sélection) : c'est
            # un refus bruyant du moteur, pas un silence. Compté comme refus du langage.
            refuses_par_le_langage.append(etiquette)
            continue

        executes += 1
        reveles = _reveles_a_bon_droit(resultat.evenements)
        for destinataire in ("alice", "bob"):
            # Une carte **montrée** par le texte de la carte n'est plus cachée : on retire du jeu
            # d'identités interdites celles que l'effet avait le droit de publier, et **seulement**
            # celles-là. L'ancien test de non-fuite, lui, exemptait l'intégralité des événements
            # `chercher` (`"refs" not in ev.donnees or ev.donnees.get("op") == "chercher"`) : il
            # n'aurait donc attrapé aucune des trois fuites de cette revue.
            interdits = _interdits_pour(depart, destinataire) - reveles
            for evenement in resultat.evenements:
                projete = projeter_evenement(evenement, pour=destinataire)
                trace = json.dumps(
                    {"type": projete.type, "donnees": projete.donnees},
                    ensure_ascii=False,
                    default=str,
                )
                for interdit in sorted(interdits):
                    assert interdit not in trace, (
                        f"Fuite sur « {etiquette} », projection vers {destinataire} : "
                        f"« {interdit} » visible dans {projete.type} — {projete.donnees}"
                    )

    # Pas de plafond silencieux : la couverture réellement exercée est **affirmée**. Un changement
    # de schéma qui ferait tomber le balayage (tout refusé → zéro exécution → test vert et creux)
    # casse ici. Le plancher est bas à dessein : il garde le test, il ne le fige pas.
    assert executes >= 100, (
        f"Balayage trop maigre : {executes} combinaisons exécutées "
        f"({len(refuses_par_le_langage)} hors langage, {len(refuses_par_l_audit)} refusées par "
        f"l'audit) — la garde ne couvre plus le langage."
    )
    # L'audit doit refuser quelque chose : s'il ne refuse plus rien, c'est que la classe de fuite
    # qu'il garde a disparu (ou que la table a été vidée) — à constater, pas à supposer.
    assert refuses_par_l_audit, "L'audit de confidentialité ne refuse plus aucune combinaison."


@pytest.mark.parametrize("zone", sorted(ZONES_CACHEES))
def test_chercher_dans_une_zone_cachee_de_l_adversaire_est_refuse(zone: str):
    """``chercher`` chez l'adversaire publie des ``ref`` vers une main : refusé, en le disant.

    Pas corrigé « au mieux » : distinguer *déplacer* de *montrer* est une évolution du langage, pas
    une décision de revue de sécurité (D9). On refuse, et on nomme.
    """
    programme = charger_programme(
        {
            "version": 1,
            "effets": [
                {
                    "op": "chercher",
                    "nombre": 1,
                    "cible": {"zone": zone, "proprietaire": "adversaire"},
                }
            ],
        }
    )
    raison = raison_de_refus(programme)
    assert raison is not None
    assert zone in raison and "chercher" in raison
    assert [f.op for f in fuites(programme)] == ["chercher"]


def test_chercher_dans_sa_propre_pioche_reste_autorise():
    """« Cherchez dans votre deck, montrez-la » (R-5.2) est la carte la plus banale du jeu.

    La garde ne doit pas rendre les Super Ball injouables : c'est le contre-test du précédent.
    """
    programme = charger_programme(
        {
            "version": 1,
            "effets": [
                {"op": "chercher", "nombre": 1, "cible": {"zone": "pioche", "proprietaire": "moi"}}
            ],
        }
    )
    assert raison_de_refus(programme) is None


def test_l_audit_descend_dans_les_branches_d_un_si():
    """Un ``chercher`` fautif niché dans un ``si``/``alors`` est trouvé — pas seulement en surface.

    Un audit qui ne lirait que la liste de premier niveau serait rassurant et faux.
    """
    programme = charger_programme(
        {
            "version": 1,
            "effets": [
                {
                    "op": "si",
                    "condition": {"type": "resultat_pile", "attendu": "face"},
                    "alors": [
                        {
                            "op": "chercher",
                            "nombre": 1,
                            "cible": {"zone": "main", "proprietaire": "adversaire"},
                        }
                    ],
                }
            ],
        }
    )
    assert raison_de_refus(programme) is not None


# ================================================================================================
# Les deux fuites réelles trouvées par la revue — chacune échoue sans son correctif.
# ================================================================================================
def test_un_choisir_dans_la_main_adverse_ne_livre_pas_les_identites():
    """FUITE n°1 : ``choisir`` sur une zone cachée livrait les ``instance_id`` au destinataire.

    ``DemandeDecision.ensemble_cache`` existait, la projection l'honorait, le journal l'honorait —
    et **aucun appelant ne le posait**. Un script « choisissez une carte de la main de votre
    adversaire » donnait donc les identités, que ``enrichir_demande`` résolvait ensuite en
    ``ref``/``nom``. Sans ``ensemble_cache_pour``, ce test échoue.
    """
    cachee = [
        CibleCarte(joueur="bob", zone="main", instance_id="bob-m1", ref="secret-1"),
        CibleCarte(joueur="bob", zone="main", instance_id="bob-m2", ref="secret-2"),
    ]
    assert ensemble_cache_pour(cachee, destinataire="alice") is True
    # Sa propre main, elle, reste visible à son propriétaire (sans quoi il ne pourrait pas choisir).
    assert ensemble_cache_pour(cachee, destinataire="bob") is False


def test_un_choisir_sur_la_main_adverse_ne_projette_que_le_nombre_d_options():
    """La même fuite, prouvée **bout en bout** : du script à la vue du joueur qui décide.

    C'est l'assertion qui échoue sur le code d'avant : la demande partait avec
    ``ensemble_cache=False``, donc ``_demande_vue`` posait ``options`` — les ``instance_id`` de la
    main de bob — dans la vue d'alice, et ``enrichir_demande`` les résolvait ensuite en ``ref``/
    ``nom``/``type``. Alice voyait la main de son adversaire.
    """
    from dataclasses import replace

    from pbm_game.demandes.gestionnaire import Gestionnaire, SuspensionDemande
    from pbm_game.demandes.moteur import ResolutionEnCours
    from pbm_game.state.projection import vue

    depart = etat(_joueur_garni("alice", "a"), _joueur_garni("bob", "b"))
    programme = charger_programme(
        {
            "version": 1,
            "effets": [
                {
                    "op": "choisir",
                    "nombre": 1,
                    "cible": {"zone": "main", "proprietaire": "adversaire", "nombre": 1},
                    "alors": [{"op": "defausser", "nombre": 1}],
                }
            ],
        }
    )
    strategie = strategie_demande(
        Gestionnaire(), destinataire="alice", regle="R-9.3", libelle="Choisis une carte"
    )
    with pytest.raises(SuspensionDemande) as leve:
        executer_programme(
            depart, programme, contexte("alice", "bob"), rng(), strategie=strategie
        )
    demande = leve.value.demande
    assert demande.ensemble_cache is True
    # Les options existent côté moteur (il doit bien savoir parmi quoi trancher) ; c'est la
    # **projection** qui ne les livre pas.
    assert set(demande.options) == {"bob-m1", "bob-m2"}

    avec_demande = replace(
        depart,
        resolution=ResolutionEnCours(
            pile=PileEffets(), demande=replace(demande, id="d0"), reponses=()
        ),
    )
    vue_alice = vue(avec_demande, "alice")["demande"]
    assert "options" not in vue_alice
    assert vue_alice["options_nombre"] == 2
    assert "bob-m1" not in json.dumps(vue_alice)


def test_les_recompenses_sont_cachees_meme_a_leur_proprietaire():
    """Une récompense est face cachée pour les **deux** joueurs (R-3.4).

    Projeter ses identités à son propriétaire lui dirait laquelle prendre : c'est l'anti-triche le
    plus élémentaire du jeu, et c'est le cas que la frontière « main » seule aurait manqué.
    """
    recompenses = [
        CibleCarte(joueur="alice", zone="recompenses", instance_id="alice-r1", ref="secret-r1")
    ]
    assert ensemble_cache_pour(recompenses, destinataire="alice") is True


def test_un_pokemon_en_jeu_n_est_jamais_un_ensemble_cache():
    """Actif et banc sont publics (R-3.1) : un ``choisir`` dessus garde ses options visibles.

    Sinon le correctif rendrait injouable l'appât (type Pokémon Catcher), qui choisit sur le banc.
    """
    banc = [
        CiblePokemon(joueur="bob", emplacement="banc", identite="bob-banc", ref="ref-banc")
    ]
    assert ensemble_cache_pour(banc, destinataire="alice") is False


def _resolveur_choix_cache(etat_courant, effet, rng_, gestionnaire):
    """Résolveur **jouet** qui pose une demande sur un ensemble caché, et rend l'état inchangé.

    Même forme que les résolveurs jouets de ``test_demandes_moteur`` : ce qu'on éprouve ici est le
    **projecteur** de l'événement de réponse, pas un effet de carte réel (D9 — on ne scripte pas
    une carte pour les besoins d'un test).
    """
    demande = DemandeDecision(
        destinataire=effet.params["destinataire"],
        categorie=CAT_CARTE,
        source=effet.source,
        regle="R-9.3",
        libelle=effet.libelle,
        options=tuple(effet.params["options"]),
        ensemble_cache=True,  # « choisis dans la main de ton adversaire »
    )
    gestionnaire.demander(demande)
    return (etat_courant, [], [])


def test_le_choix_retenu_d_une_decision_ne_part_pas_a_l_adversaire():
    """FUITE n°2 : ``demande_repondue`` diffusait le ``choix`` — une identité cachée — aux deux.

    Le projecteur valait ``_public``, au motif (écrit en commentaire, jamais imposé) que ces
    événements « ne portent jamais une carte d'une zone cachée ». Dès que le DSL a su poser de
    vraies demandes, c'est devenu faux. Sans ``_demande_tranchee``, ce test échoue.
    """
    depart = etat(_joueur_garni("alice", "a"), _joueur_garni("bob", "b"))
    cachee = "bob-m1"  # une carte de la main de bob : cachée à alice
    registre = {"choix_cache": _resolveur_choix_cache}
    pile = PileEffets().empiler(
        EffetEnAttente(
            type_effet="choix_cache",
            source=SourceEffet("carte Perturbation", ref="r-perturbation", instance_id="i-p"),
            regle="R-9.3",
            libelle="Choisis une carte de la main adverse",
            params={"destinataire": "alice", "options": [cachee]},
        )
    )
    moteur_rng = Rng(b"seed-0123456789a")
    en_attente, _ = demarrer_resolution(depart, pile, moteur_rng, registre=registre)
    assert en_attente.resolution is not None

    _apres, evenements = repondre(
        en_attente, Reponse("d0", (cachee,)), moteur_rng, registre=registre
    )
    evenement = next(e for e in evenements if e.type == EVT_DEMANDE_REPONDUE)
    # Le journal moteur garde tout : c'est ce qui fait tenir la rejouabilité et le support.
    assert cachee in json.dumps(evenement.donnees)

    vu_par_alice = projeter_evenement(evenement, pour="alice")
    vu_par_bob = projeter_evenement(evenement, pour="bob")
    assert vu_par_alice.donnees.get("choix") == [cachee]  # elle a tranché : elle revoit son choix
    assert "choix" not in vu_par_bob.donnees
    assert vu_par_bob.donnees["choix_nombre"] == 1
    assert cachee not in json.dumps(vu_par_bob.donnees)
