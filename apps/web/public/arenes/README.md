# Décors d'arène

Quatre décors originaux pour le plateau de jeu (lots `v7-plateau` et `v7-effets-visuels`), en 1600 px de large :

| Fichier | Ambiance |
|---|---|
| `arene.jpg` | arène officielle, jour |
| `volcan.jpg` | volcan |
| `nuit.jpg` | arène de nuit |
| `mer.jpg` | bord de mer |

**Règle** : le décor ne dessine jamais les emplacements de cartes — ils sont produits en HTML/CSS par-dessus, sinon toute évolution (taille du deck, nombre de cartes au banc, disposition mobile) casse l'image. Le centre du terrain reste mat et peu contrasté ; les effets lumineux se cantonnent aux 15-20 % périphériques. Versions allégées embarquées dans la maquette (`docs/roadmap/ROADMAP.html`, onglet « Maquette du jeu »).
