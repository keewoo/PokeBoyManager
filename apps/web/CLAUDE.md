# apps/web — Next.js 15, React 19, TypeScript strict

Chargé automatiquement quand on travaille ici. Les règles du dépôt restent celles de `CLAUDE.md`
à la racine ; ce fichier ne fait qu'orienter.

| Avant de… | Lire |
|---|---|
| dessiner un écran, ajouter un composant, choisir une couleur | `docs/UI-UX.md` |
| écrire du code, lancer les tests | `docs/CODE.md` |
| savoir ce que rend l'API | `docs/ARCHITECTURE.md` |

Rappels qui coûtent cher quand on les oublie :

- **La maquette fait foi** (onglet « Maquette du site » de `docs/roadmap/ROADMAP.html`) ; un écart
  assumé se dit dans le compte rendu du lot.
- Une couleur nouvelle se déclare en jeton dans `apps/web/src/app/globals.css`, jamais en dur.
- Identité propre : **aucun logo officiel Pokémon**.
- Le middleware ne lit que la **présence** du cookie de session : `NEXT_PUBLIC_SESSION_COOKIE_NAME`
  doit rester aligné avec `SESSION_COOKIE_NAME` côté API.
- La CSP `connect-src` doit inclure l'origine du stockage objet, sinon **tout envoi de photo
  échoue** — déjà payé une fois.
