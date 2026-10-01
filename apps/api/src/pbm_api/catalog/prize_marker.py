"""Marqueur de règle **normalisé** d'une carte — la classification qui fait foi pour la règle
des Prix (R-13.3/R-13.7, R-15.1 à R-15.22).

**Le défaut qu'on corrige (lot `fix-marqueur-recompenses`, 01/10/2026).** Jusqu'ici, le nombre
de récompenses se déduisait du **suffixe du nom** (`pbm_api.ingame.rules.prize_rule_of`, ancienne
version). Or une **Méga-Évolution Pokémon ex** (série Méga-Évolution, 2025) finit par « ex » mais
donne **3** récompenses, et une **TAG TEAM** finit par « GX » mais en donne **3** : le suffixe du
nom ne classe pas une carte (R-13.7). On normalise donc une fois pour toutes, depuis les données du
catalogue, vers un **marqueur de règle** du vocabulaire du moteur (`pbm_game.combat.fin
.MARQUEUR_RECOMPENSES`).

**Ce que la fonction lit, et pourquoi ça suffit.** Mesuré sur `pbm_catalogue_ref` (22 169 cartes,
identique à la PROD) le 01/10/2026 : le `cards.rule_marker` (le `suffix` TCGdex — en **français** :
`ESCOUADE`=TAG TEAM, `TURBO`=BREAK, `Niveau Sup`=LV.X, `MÉGA`=M Pokémon-EX de l'ère XY, `LÉGENDE`,
`ex`/`EX`/`V`/`GX`/`VMAX`, ou `SP`/`Primo`/`Restauré`/`Bébé` pour des Pokémon **ordinaires**, sinon
`NULL`) combiné au **nom imprimé** (préfixe « Méga » vs « M », glyphes `◇`/`★`, `VSTAR`, `V-UNION`,
`Radieux`, et le suffixe de nom quand `rule_marker` manque) distingue **chaque** catégorie de R-15
sans ambiguïté. Aucune donnée TCGdex supplémentaire n'a eu besoin d'être stockée (la colonne `stage`
n'existe même pas dans la base de référence).

⚠️ Le `rule_marker` du catalogue est **lacunaire** (mesuré) : ~60 Pokémon à Rule Box ont un
`rule_marker` NULL alors que leur **nom** porte la désignation (`Sulfura ex`, `Mewtwo et Mew GX`,
`Zarbi V`…). Le nom est donc un **repli** nécessaire — mais jamais utilisé **seul** là où il
tromperait : une TAG TEAM finit par « GX » comme un Pokémon-GX ordinaire, on la reconnaît à son
**jointeur** (« et »/« & »/« and ») ; une Méga-Évolution ex finit par « ex » comme un ex ordinaire,
on la reconnaît à son **préfixe** « Méga ». C'est R-13.7 en acte : on **croise** les signaux.

**Elle refuse de deviner (R-13.4/R-15.22).** Une carte Pokémon dont le `rule_marker` est présent
mais **non reconnu** rend :data:`MARQUEUR_INCONNU` — jamais `ordinaire` par défaut. Une carte hors
Pokémon (Dresseur, Énergie) rend ``None`` : la règle des Prix ne la concerne pas.
"""

import re

#: Catégories TCGdex (`category`, localisée) qui désignent un Pokémon — la règle des Prix ne
#: concerne que les Pokémon. « Pokémon » (français, le cas du catalogue) et « Pokemon » (anglais,
#: repli de langue de l'import) sont tous deux acceptés.
POKEMON_SUPERTYPES = frozenset({"Pokemon", "Pokémon"})

#: Marqueur rendu pour une carte à Rule Box **que la classification ne sait pas ranger** : elle
#: échoue bruyamment plus loin (R-13.4/R-15.22), jamais « par défaut 1 ».
MARQUEUR_INCONNU = "inconnu"

#: `rule_marker` (suffixe TCGdex) de Pokémon **ordinaires** — ils portent une désignation
#: historique (Pokémon SP, Prime, Restauré/fossile, Bébé) mais **pas** de Rule Box et prennent
#: **1** récompense. Comparés sans tenir compte de la casse. Listés explicitement : tout autre
#: suffixe non reconnu rend :data:`MARQUEUR_INCONNU` (on ne devine pas).
_ORDINARY_MARKERS_CF = frozenset(
    {"sp", "primo", "restauré", "bébé", "prime", "baby", "restored"}
)

#: Stades d'évolution **ordinaires** (TCGdex `stage`), sous forme **normalisée** : sans casse, et
#: sans espaces ni tirets. Un stade ordinaire n'est JAMAIS un marqueur de règle — ni recopié dans
#: `cards.rule_marker` à l'import, ni classé en Rule Box ici. Le défaut corrigé (lot
#: `fix-marqueur-stades`, 02/10/2026) : la PROD portait 564 cartes dont `rule_marker` valait
#: `Stage1`/`Stage2` (sans espace) — l'import ne reconnaissait que `stage 1`/`stage 2` —, classées
#: `inconnu` faute d'une normalisation commune des stades à l'import et ici.
_ORDINARY_STAGES_NORM = frozenset(
    {"base", "basic", "niveau1", "niveau2", "stage1", "stage2"}
)
#: Sépare un libellé de stade pour le normaliser : « Stage 1 », « Stage-1 » et « Stage1 » sont un.
_RE_STAGE_SEP = re.compile(r"[\s-]+")


def is_ordinary_stage(value: str | None) -> bool:
    """Vrai si ``value`` désigne un **stade d'évolution ordinaire** (Base, Basic, Niveau 1/2,
    Stage 1/2), quelles que soient la casse et la présence d'espaces ou de tirets : ``Stage1`` =
    ``stage 1`` = ``Stage-1``.

    Définition **unique** de « stade ordinaire », partagée par l'import
    (`catalog.import_service._rule_marker`, qui ne recopie donc jamais un stade dans
    `rule_marker`) et par :func:`normalized_prize_marker` (qui ne le prend donc jamais pour une
    Rule Box). Fonction pure.
    """
    if not value:
        return False
    return _RE_STAGE_SEP.sub("", value.strip()).casefold() in _ORDINARY_STAGES_NORM


def corrected_stage_row(
    *, name: str | None, supertype: str | None, rule_marker: str | None
) -> tuple[None, str | None] | None:
    """Décision de correction d'UNE ligne ``cards`` par la migration `fix-marqueur-stades`.

    Rend ``None`` quand la ligne n'est **pas** concernée : son `rule_marker` n'est pas un stade
    ordinaire, donc on n'y touche pas (une vraie Rule Box — ``VMAX``, ``ex``… — reste intacte).
    Sinon rend le couple corrigé ``(nouveau_rule_marker, nouveau_prize_marker)`` : ``rule_marker``
    remis à ``None`` (un stade n'est pas un marqueur de règle, R-13.3) et ``prize_marker``
    **recalculé** par :func:`normalized_prize_marker` sur le `rule_marker` vidé. Fonction pure — la
    migration ne fait que l'appliquer ligne par ligne, et le test la vérifie sans base.
    """
    if not is_ordinary_stage(rule_marker):
        return None
    return (None, normalized_prize_marker(name=name, supertype=supertype, rule_marker=None))

# Motifs de nom. On ne s'en sert qu'en croisement d'un autre signal (jamais le suffixe de nom
# seul là où il tromperait : cf. R-13.7 et la docstring du module).
_RE_V_UNION = re.compile(r"\bV[\s-]?UNION\b", re.IGNORECASE)
_RE_VMAX = re.compile(r"\bVMAX\b", re.IGNORECASE)
_RE_VSTAR = re.compile(r"\bVSTAR\b", re.IGNORECASE)
_RE_RADIANT = re.compile(r"radieux|radieuse|radiant", re.IGNORECASE)
# Préfixe « Méga »/« Mega » (série Méga-Évolution 2025) : au moins deux lettres puis séparateur —
# distinct du « M »/« M- » seul des M Pokémon-EX de l'ère XY.
_RE_MEGA_PREFIX = re.compile(r"^(méga|mega)[\s-]", re.IGNORECASE)
_RE_M_PREFIX = re.compile(r"^m[\s-]", re.IGNORECASE)
# Jointeur de deux Pokémon → TAG TEAM (« Pikachu et Zekrom GX », « Pikachu & Zekrom-GX »). Aucun
# nom d'espèce ne contient « et »/« & »/« and » isolé : le jointeur est propre aux TAG TEAM.
_RE_TAG_JOINER = re.compile(r"\s(et|&|and)\s|&", re.IGNORECASE)
# Suffixes de nom (repli quand `rule_marker` est NULL) — « ex »/« EX » minuscule vs majuscule
# distinguent Pokémon ex (R-15.16/R-15.1) et Pokémon-EX (R-15.14) ; les deux donnent 2.
_RE_NAME_EX_LOWER = re.compile(r"[\s-]ex$")
_RE_NAME_EX_UPPER = re.compile(r"[\s-]EX$")
_RE_NAME_GX = re.compile(r"[\s-]GX$", re.IGNORECASE)
_RE_NAME_V = re.compile(r"[\s-]V$")


def normalized_prize_marker(
    *, name: str | None, supertype: str | None, rule_marker: str | None
) -> str | None:
    """Rend le marqueur de règle normalisé d'une carte, ou ``None`` si elle n'est pas un Pokémon.

    Les entrées sont les colonnes du catalogue : ``name`` (nom imprimé, langue d'import),
    ``supertype`` (`cards.supertype`), ``rule_marker`` (`cards.rule_marker`, le suffixe TCGdex ou
    un stade spécial). Le marqueur rendu est une **clé** de ``MARQUEUR_RECOMPENSES`` du moteur,
    ou :data:`MARQUEUR_INCONNU` pour une carte à Rule Box non classable (R-13.4). Fonction **pure**
    et déterministe : même code à l'import (`catalog.import_service`) et dans la migration de
    remplissage, pour une seule logique de classification.
    """
    if supertype not in POKEMON_SUPERTYPES:
        return None

    n = (name or "").strip()
    nf = n.casefold()
    rm = (rule_marker or "").strip()
    rmf = rm.casefold()

    ends_gx = bool(_RE_NAME_GX.search(n))

    # --- 3 récompenses (R-13.3) : les pièges du suffixe du nom (R-13.7) + VMAX ------------
    # V-UNION : le nom porte « V-UNION », le suffixe reste « V » — AVANT le V simple.
    if _RE_V_UNION.search(n):
        return "v_union"
    # Méga-Évolution Pokémon ex (2025, R-15.13) : préfixe « Méga » et finit par « ex » (le
    # suffixe est tantôt « ex », tantôt « EX », tantôt NULL selon la carte — mesuré au catalogue).
    if _RE_MEGA_PREFIX.match(n) and nf.endswith("ex"):
        return "mega_ex"
    # VMAX (R-15.5) : suffixe « VMAX » ou le nom.
    if rm == "VMAX" or _RE_VMAX.search(n):
        return "vmax"
    # TAG TEAM (R-15.7) : suffixe français « ESCOUADE » (anglais « TAG TEAM »), OU — quand le
    # suffixe manque — deux Pokémon joints (« et »/« & ») dont le nom finit par « GX ». AVANT le
    # Pokémon-GX ordinaire : une TAG TEAM finit par « GX » mais donne 3 (R-13.7).
    if rmf in ("escouade", "tag team") or (ends_gx and _RE_TAG_JOINER.search(n)):
        return "tag_team"

    # --- 2 récompenses (R-13.3) ------------------------------------------------------------
    # M Pokémon-EX, ère XY (R-15.15) : suffixe « MÉGA », ou préfixe « M »/« M- » seul sur une
    # carte EX/ex. 2 récompenses (à distinguer de la Méga-Évolution ex de 2025, déjà traitée).
    if rmf == "méga" or (
        _RE_M_PREFIX.match(n) and (rm in ("ex", "EX") or nf.endswith("ex"))
    ):
        return "m_pokemon_ex"
    # VSTAR (R-15.6) : suffixe « VSTAR » ou le nom (au catalogue, `rule_marker` est NULL).
    if rm == "VSTAR" or _RE_VSTAR.search(n):
        return "vstar"
    # Pokémon ex, minuscules — ère EX (R-15.16) & série actuelle (R-15.1). Inclut Tera ex
    # (R-15.2) : même nombre de récompenses, indistinct dans les données du catalogue. Repli sur
    # le suffixe de nom « ex » quand `rule_marker` manque (jamais « Complex » : il faut un
    # séparateur devant « ex »).
    if rm == "ex" or _RE_NAME_EX_LOWER.search(n):
        return "ex"
    # Pokémon-EX, majuscules & tiret — ères Noir & Blanc / XY (R-15.14).
    if rm == "EX" or _RE_NAME_EX_UPPER.search(n):
        return "pokemon_ex"
    # Pokémon-GX (R-15.3) — la TAG TEAM a déjà été écartée ci-dessus.
    if rm == "GX" or ends_gx:
        return "gx"
    # Pokémon V (R-15.4) — le V-UNION a déjà été écarté.
    if rm == "V" or _RE_NAME_V.search(n):
        return "v"
    if rmf in ("légende", "legende", "legend"):  # LÉGENDE (R-15.19).
        return "legende"

    # --- 1 récompense : cartes à Rule Box qui n'en donnent qu'une (R-13.3) -----------------
    if rmf in ("turbo", "break"):  # Pokémon BREAK, suffixe français « TURBO » (R-15.17).
        return "break"
    if rmf in ("niveau sup", "niveau x", "lv.x", "lv x", "level-up", "lvx"):  # LV.X (R-15.20).
        return "lv_x"
    if _RE_RADIANT.search(n):  # Radiant / Radieux (R-15.9).
        return "radiant"
    if "◇" in n:  # Prisme Étoile (R-15.18).
        return "prisme_etoile"
    if "★" in n or "☆" in n:  # Pokémon ★ Étoile (R-15.21).
        return "etoile"

    # --- Pokémon ordinaire (R-13.3) OU refus de deviner (R-13.4/R-15.22) -------------------
    # Un stade ordinaire (`Stage1`, `Niveau 1`, `Basic`…) écrit par erreur dans `rule_marker`
    # n'est PAS une Rule Box : il donne 1 récompense comme tout Pokémon ordinaire (R-13.3).
    if rm == "" or rmf in _ORDINARY_MARKERS_CF or is_ordinary_stage(rm):
        return "ordinaire"
    # `rule_marker` présent mais non reconnu : carte à Rule Box non classable → on ne devine pas.
    return MARQUEUR_INCONNU
