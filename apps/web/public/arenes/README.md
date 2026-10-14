# Décors d'arène (maquette uniquement)

> ⚠️ **Le jeu ne charge AUCUN de ces fichiers.** Depuis le lot `j-arene-decors`, les décors du
> plateau sont peints en **dégradés CSS** (`apps/web/src/app/globals.css`, bloc « Décors d'arène »,
> table dans `apps/web/src/lib/game/decors.ts`) : 1,24 Mo pour ces quatre JPG contre **zéro octet
> transféré**, et un contraste qu'on peut *calculer* au lieu de l'estimer. Ces images restent ici
> pour la maquette. Détail et raisons : `docs/jeu/DECORS.md`.


Quatre décors originaux pour le plateau de jeu (lots `v7-plateau` et `v7-effets-visuels`), en 1600 px de large :

| Fichier | Ambiance |
|---|---|
| `arene.jpg` | arène officielle, jour |
| `volcan.jpg` | volcan |
| `nuit.jpg` | arène de nuit |
| `mer.jpg` | bord de mer |

**Règle** : le décor ne dessine jamais les emplacements de cartes — ils sont produits en HTML/CSS par-dessus, sinon toute évolution (taille du deck, nombre de cartes au banc, disposition mobile) casse l'image. Le centre du terrain reste mat et peu contrasté ; les effets lumineux se cantonnent aux 15-20 % périphériques. Versions allégées embarquées dans la maquette (`docs/roadmap/ROADMAP.html`, onglet « Maquette du jeu »).
