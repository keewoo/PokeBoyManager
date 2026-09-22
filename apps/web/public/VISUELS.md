# Visuels de marque — icônes et personnages

Fournis par JF le 22/09/2026 sous forme de deux planches, découpés ici en éléments
réutilisables, fond transparent, prêts à poser sur le bleu nuit `#050A30`.

## `icons/ui/` — 12 icônes, 256 × 256 PNG

| Fichier | Emploi prévu |
|---|---|
| `masterball.png` | marque, écran de lancement, état « en cours » |
| `classeur.png` | collection, classeur |
| `coffre.png` | valeur de la collection, tableau de bord |
| `echange.png` | échanges (vague V8) |
| `scan.png` | ajouter une carte, reconnaissance, recherche |
| `duel.png` | parties et decks (vague V7) |
| `dresseur.png` | profil, compte, coffre de clés IA |
| `favoris.png` | liste de souhaits, cartes suivies |
| `nouveaute.png` | derniers ajouts, badge « nouveau » |
| `actualites.png` | anecdotes et histoire de la carte |
| `communaute.png` | vitrine des échanges, réputation |
| `reglages.png` | préférences, import/export, administration |

## `personnages/` — 9 personnages, 512 × 512 PNG

`amphinobi`, `ronflex`, `palkia`, `magicarpe`, `evoli`, `salameche`, `rayquaza`,
`groudon`, `kyurem`.

Ils servent de **présence**, jamais de décor : un état vide qui serait une phrase seule,
une réussite qu'on veut fêter, un écran d'attente. Un seul personnage par écran — deux
et l'interface devient une vitrine de peluches.

Emplois retenus dans la maquette : `evoli` sur les états vides et l'accueil connecté,
`magicarpe` sur les échecs et les collections qui démarrent, `salameche` sur l'ajout,
`ronflex` sur les chargements longs, `rayquaza` / `groudon` / `palkia` / `kyurem` sur les
paliers et les cartes légendaires, `amphinobi` sur les duels.

## Découpe

Les deux planches sources sont conservées hors dépôt. Le détourage a été fait par
modélisation du fond (surface quadratique ajustée sur l'anneau de bord) puis conservation
de la plus grande tache s'en écartant, trous rebouchés — un simple remplissage depuis les
bords échouait sur les icônes, dont le halo bleu se confond avec le fond bleu.

**Le halo d'origine n'a pas été conservé** : l'interface pose le sien en CSS
(`box-shadow` / `filter: drop-shadow`), ce qui le rend teintable et cohérent d'un écran
à l'autre.

> Ces visuels représentent des créatures et des objets de l'univers Pokémon, propriété de
> Nintendo / The Pokémon Company. Le produit affiche déjà la mention « non affilié » (D8) ;
> leur usage en marque propre reste à valider avant toute diffusion publique.
