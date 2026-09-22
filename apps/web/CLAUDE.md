# apps/web — Next.js 15, React 19, TypeScript strict

Chargé automatiquement quand on travaille ici. Les règles du dépôt restent celles de `CLAUDE.md`
à la racine ; ce fichier ne fait qu'orienter.

| Avant de… | Lire |
|---|---|
| dessiner un écran, ajouter un composant, choisir une couleur | `docs/UI-UX.md` |
| écrire du code, lancer les tests | `docs/CODE.md` |
| savoir ce que rend l'API | `docs/ARCHITECTURE.md` |

**Avant de fouiller** (quel composant utilise quoi, d'où vient cette donnée) : demande au graphe `graphify`
(`query_graph`, `get_neighbors`) plutôt que d'enchaîner les `grep` — c'est du contexte économisé.
`graphify update .` après un gros changement.

Rappels qui coûtent cher quand on les oublie :

- **La charte PokéBoy fait foi** pour tout écran nouveau ou repris
  (https://claude.ai/artifact/M2GyeGw6T6FeW5anfq1op8) ; la maquette d'origine (onglet « Maquette du
  site » de `docs/roadmap/ROADMAP.html`) reste la référence de structure des écrans V1–V4. Un écart
  assumé se dit dans le compte rendu du lot.
- **La charte n'est pas dans `globals.css`** : les jetons y sont encore ceux d'origine. La reprise
  est un lot à part — ne pas repeindre le produit au passage d'un autre lot.
- Une couleur nouvelle se déclare en jeton dans `apps/web/src/app/globals.css`, jamais en dur.
  Le violet `#9D00FF` ne sert **jamais** de couleur de texte (2,8:1) : `#C77DFF` pour les titres.
- **L'icône et le logotype ne cohabitent jamais dans un même en-tête** : le logotype porte
  déjà son symbole. En-tête et connexion → le logotype ; barre d'application, onglet,
  avatar → l'icône.
- Identité propre : **aucun logo officiel Pokémon**. Les personnages de `public/personnages/`
  restent réservés aux **maquettes internes** tant que JF n'a pas tranché leur usage public.
- Le middleware ne lit que la **présence** du cookie de session : `NEXT_PUBLIC_SESSION_COOKIE_NAME`
  doit rester aligné avec `SESSION_COOKIE_NAME` côté API.
- La CSP `connect-src` doit inclure l'origine du stockage objet, sinon **tout envoi de photo
  échoue** — déjà payé une fois.
