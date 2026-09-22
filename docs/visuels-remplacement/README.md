# Visuels de remplacement

**3 827 cartes du catalogue n'ont aucune image officielle** (surtout de vieilles extensions et des
promos : Méga-Ascension 331, Promo SM 248, Sagesse Entre Ciel et Mer 241…). Aucun import ne les
rapportera : les sources publiques ne les ont pas.

La carte affichée est alors **composée** : le cadre est dessiné à partir des vraies données du
catalogue (nom, PV, type, extension, numéro, rareté) et seule la zone d'illustration reçoit un
**fond générique**, choisi de façon déterministe d'après l'identifiant de la carte — la même carte
garde donc toujours le même visuel. Une mention « visuel non disponible » reste affichée : un
remplacement ne se fait jamais passer pour l'image officielle.

Le même mécanisme sert de repli quand une image officielle est temporairement injoignable, et
pendant une partie, où une carte sans image ne doit pas casser le plateau.

## Les planches

Un fichier de prompt par type, dans `prompts/`, nommé avec le code de type du jeu :

| Code | Type | Code | Type |
|---|---|---|---|
| `grass` | Plante | `darkness` | Obscurité |
| `fire` | Feu | `metal` | Métal |
| `water` | Eau | `dragon` | Dragon |
| `lightning` | Électrique | `fairy` | Fée |
| `psychic` | Psy | `colorless` | Incolore |
| `fighting` | Combat | | |

Chaque prompt produit **une planche de 9 vignettes** (1536 × 1536, grille 3 × 3, gouttières
magenta `#FF00FF` de 24 px). Onze planches = **99 fonds**.

Pourquoi des planches plutôt qu'une seule grande image : à 100 vignettes dans une image, chaque
case tomberait sous 150 px et serait inutilisable. Pourquoi des gouttières magenta : la découpe
détecte les bandes au lieu de couper à l'aveugle sur une grille supposée.

## Le circuit

1. Générer chaque planche avec le prompt correspondant → `planches/<code>.png`.
2. Découper : `python3 decouper.py planches/<code>.png` → `fonds/<code>-01.webp` … `-09.webp`
   (512 px, WebP qualité 80). Le script vérifie les gouttières et **refuse** une planche mal
   alignée plutôt que de produire des vignettes décalées.
3. Les fonds sont servis par le site ; le choix pour une carte est `hash(card_id) % 9`.
