# apps/api — FastAPI, Python 3.12

Chargé automatiquement quand on travaille ici. Les règles du dépôt restent celles de `CLAUDE.md`
à la racine ; ce fichier ne fait qu'orienter.

| Avant de… | Lire |
|---|---|
| écrire du code, lancer les tests | `docs/CODE.md` |
| changer un comportement, une table, une route | `docs/ARCHITECTURE.md` |
| appeler un service extérieur ou toucher à une clé | `docs/PLUGINS.md` |
| toucher à l'authentification, aux sessions, aux envois de fichiers | `docs/SECURITE.md` |
| ajouter une variable d'environnement | `docs/LIVRAISON.md` |

Rappels qui coûtent cher quand on les oublie :

- **Toute route utilisateur filtre par `user_id`** issu de la session, et son test d'accès croisé
  est obligatoire.
- Une clé IA ne sort **jamais** : ni en réponse, ni en journal, ni dans une erreur 422.
- `uv sync`, `uv run pytest -q`, `uv run ruff check .` — Python **3.12**, la CI fait foi.
- Après tout changement de schéma d'API : `pnpm gen:api` à la racine, sinon le client TypeScript
  ment.
