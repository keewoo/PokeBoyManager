# Aléatoire reproductible, vérifiable et journalisé — `pbm_game.rng`

> Livré par le lot `j-aleatoire-determinisme` (jalon J1). Le code vit dans
> `apps/game/src/pbm_game/rng/`. Cette fiche **documente la mécanique** pour qu'un
> vérificateur indépendant (y compris dans un autre langage) la réimplémente sans lire
> le code Python.

## Pourquoi

Une partie est « un état initial, une graine d'aléatoire et un journal d'actions
numéroté » (principe « tout est rejouable », jalon J1). Sans aléatoire **reproductible** :

- une partie ne se rejoue pas après un F5 ;
- un bug trouvé ne se reproduit pas ;
- rien ne prouve au perdant que le mélange n'a pas été rejoué en boucle jusqu'à un bon
  résultat.

Trois propriétés y répondent, chacune testée (`apps/game/tests/test_rng.py`).

## 1. Aléatoire encapsulé — aucun `random` global

Le hasard passe **uniquement** par un objet `Rng` reçu explicitement. Aucun appel à
`random` nulle part dans le moteur — un test de grep statique (AST) sur tout le paquet
`pbm_game` l'interdit pour toujours. Deux raisons : le module `random` de Python n'offre
aucune garantie de reproductibilité inter-langage, et un `random` global rend l'ordre des
tirages invisible et donc intruquable… et invérifiable.

## 2. Flux nommés indépendants

Chaque usage tire dans son propre **flux** (une simple chaîne) : le mélange de chaque
joueur, le pile ou face de début de partie, chaque effet aléatoire. Chaque flux a son
**compteur** indépendant. Conséquence voulue : **ajouter un tirage dans un flux ne décale
jamais la suite d'un autre flux** — le piège nommé dans la mission (un flux partagé casse
la reproductibilité dès qu'une carte ajoute un pile ou face) est écarté par construction.

Flux conventionnels fournis :

| Flux | Règle | Helper / constante |
|---|---|---|
| mélange du deck d'un joueur | R-4.1 | `flux_melange_deck(joueur_id)` → `melange:deck:<id>` |
| qui commence (pile ou face) | R-4.7 | `FLUX_QUI_COMMENCE` = `partie:qui-commence` |
| états spéciaux (Endormi/Brûlé/Confus) | R-11.3/4/5 | flux libre, ex. `etat:endormi:<joueur>` |

Un flux est **n'importe quelle chaîne** : les suivants (états spéciaux, effets de cartes)
nomment le leur, un par usage.

## 3. Engagement-révélation (commit-reveal)

- **Avant** la partie, on publie l'**engagement** : `engagement(graine)`.
- **À la fin**, on révèle la **graine**.
- Un **vérificateur indépendant** recalcule alors chaque tirage et confirme qu'il est
  *exactement* le i-ème tirage de son flux sous cette graine, dans l'ordre, sans trou.

On ne peut donc ni changer de graine en cours de route (l'engagement ne correspondrait
plus), ni « rejouer le mélange jusqu'à un bon résultat » (chaque flux doit être la suite
déterministe 0, 1, 2, … de la graine engagée).

## La mécanique, précisément (pour réimplémentation)

### Graine

Octets bruts, **≥ 16 octets** (128 bits). Le moteur ne la fabrique pas (il est pur) :
l'appelant la tire (`os.urandom(32)` côté serveur) et la passe à `Rng(graine)`.

### Bloc pseudo-aléatoire

Pour un flux `f`, un indice de tirage `i` (0-based) et un sous-bloc `s` (0-based) :

```
bloc(graine, f, i, s) = HMAC-SHA256(
    clé     = graine,
    message = b"pbm-rng-v1:flux" + utf8(f) + 0x00 + uint64_be(i) + uint64_be(s)
)
```

→ 32 octets. Le **flux d'octets** d'un tirage est la concaténation de
`bloc(…, s=0)`, `bloc(…, s=1)`, … : illimité, consommé octet par octet selon le besoin.
Un tirage consomme **une** incrémentation du compteur de son flux, quel que soit le
nombre d'octets lus (un mélange de 60 cartes comme un pile ou face).

### Entier sans biais dans `[0, n)`

Rejet : `k = ceil(bits(n)/8)` octets lus en big-endian donnent `v ∈ [0, 256^k)` ;
on **rejette** `v ≥ 256^k − (256^k mod n)` (on lit `k` octets de plus) et sinon on rend
`v mod n`. Pas de modulo brut : les petits restes seraient sur-représentés.

- **pile ou face** = entier dans `[0, 2)` : `0 → face`, `1 → pile`.
- **entier(n)** = entier dans `[0, n)`.

### Mélange (Fisher–Yates)

`perm = [0, 1, …, taille−1]` ; pour `i` de `taille−1` à `1`, tirer `j` sans biais dans
`[0, i]` (en consommant **le même flux d'octets** du tirage, à la suite) et échanger
`perm[i]` et `perm[j]`. Le mélange renvoie `[sequence[perm[0]], sequence[perm[1]], …]` et
journalise **la permutation `perm`**, jamais les cartes : le journal prouve *comment* une
zone cachée a été battue sans en révéler le contenu.

### Engagement

```
engagement(graine) = SHA-256( b"pbm-rng-v1:engagement:" + graine )  (hex)
```

La séparation de domaine (`:engagement:` vs `:flux`) garantit qu'une même graine ne
produit jamais par accident la même suite pour l'engagement et pour les tirages.

### Journal

Chaque tirage est journalisé, autosuffisant pour être revérifié :

| Champ | Sens |
|---|---|
| `flux` | le flux nommé |
| `indice` | rang dans ce flux (0, 1, 2, …, sans trou) |
| `motif` | pourquoi (ex. `R-4.7 qui commence`) |
| `genre` | `pile_ou_face` \| `entier` \| `melange` |
| `parametre` | domaine du tirage : 2 (pile ou face), `n` (entier), `taille` (mélange) |
| `resultat` | `face`/`pile`, un entier, ou la permutation (liste d'indices) |

## Vérifier a posteriori — une commande

L'enregistrement publié en fin de partie :

```json
{
  "engagement": "<empreinte publiée AVANT la partie>",
  "graine":     "<graine révélée À LA FIN, en hexadécimal>",
  "journal":    [ { "flux": "...", "indice": 0, "genre": "melange", "parametre": 60, "resultat": [ ... ] }, ... ]
}
```

```bash
cd apps/game
uv run python -m pbm_game.rng verifier <enregistrement.json>
```

Codes de sortie : `0` cohérent, `1` anomalie trouvée (détaillée, jamais tue), `2` entrée
illisible. La vérification confirme (a) la graine correspond à l'engagement, et (b) chaque
tirage est exactement le i-ème de son flux sous la graine — ce qui détecte une graine
changée, un pile ou face retourné, un mélange réordonné ou un tirage effacé.

## Limites volontaires (reste à faire des lots suivants)

- Le `Rng` n'est **pas** encore branché au journal d'actions (`j-journal-actions`) ni au
  lancement de partie (`j-lancement-partie`) : il fournit la brique, ces lots la câblent.
- La publication HTTP de l'engagement et la révélation de la graine sont du ressort de
  l'API (`apps/api`), hors du moteur pur — le moteur fournit `engagement`, `graine_hex`
  et `etat()`, l'API les expose.
