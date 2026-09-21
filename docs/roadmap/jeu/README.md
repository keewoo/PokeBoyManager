# Section « Jeu » — mode d'emploi

Le jeu a son propre plan, à côté du plan daté du produit (`docs/roadmap/roadmap.json`).
**Il n'a pas de dates** : l'ordre vient des dépendances entre lots, et l'avancement se lit
en cinq jalons fonctionnels. C'est un choix, pas un oubli — mettre une date sur un moteur
de règles qu'on n'a pas encore écrit revient à inventer un chiffre que personne ne tiendra.

## Les fichiers

| Fichier | Rôle |
|---|---|
| `plan/meta.json` | Objet, principes, pistes, couloirs, jalons, décisions `DJ*`, correspondance avec le plan daté. **Source.** |
| `plan/10-regles.json` … `plan/70-qualite.json` | Les lots, un fichier par piste. **Source.** |
| `build-jeu.py` | Vérifie l'ordonnancement (dépendances, cycles) et génère les deux fichiers ci-dessous. |
| `BACKLOG-JEU.md` | Le backlog lisible. **Généré — ne pas éditer à la main.** |
| `jeu.json` | Le même plan à plat, palier calculé, pour l'outillage. **Généré.** |

## Les commandes

```bash
python3 docs/roadmap/jeu/build-jeu.py --verifier   # contrôle seul (code 1 si le plan est incohérent)
python3 docs/roadmap/jeu/build-jeu.py              # contrôle puis génère BACKLOG-JEU.md et jeu.json
```

Le contrôle refuse : un identifiant en double, une dépendance vers un lot inexistant,
un cycle de dépendances, une piste / un couloir / un jalon / une décision inconnus,
un champ obligatoire vide, une décision qui débloque un lot qui n'existe pas.

## Ajouter ou modifier un lot

1. Éditer le fichier de plan de la piste concernée (`plan/*.json`).
2. Renseigner tous les champs : `id`, `titre`, `piste`, `couloir`, `jalon`, `priorite`,
   `taille`, `gain`, `fonctionnalites`, `mission`, `acceptation`, `livrables`, `risques`,
   `apres` (liste, éventuellement vide), et `decision` si le lot en attend une.
3. Dans `apres`, ne mettre que les **vraies** dépendances — ce sans quoi le lot ne peut pas
   être écrit. Le fait que deux lots soient portés par le même couloir n'est pas une
   dépendance : c'est une contrainte de ressource, et le tableau des paliers la rend visible.
4. Relancer `build-jeu.py` et committer **les sources et les fichiers générés ensemble**.

## Ce que ce plan ne contient pas

- **Le gestionnaire de decks** (`v7-decks-*`) : il reste dans le plan daté, il est utilisable
  sans moteur de règles, et il est un préalable à la file d'attente.
- **Des dates.** Si JF en veut, elles se posent au moment où un couloir prend un lot,
  dans l'état du plan daté — pas ici.
- **Les prompts de lots.** Ils s'écrivent lot par lot, à partir de la fiche du backlog,
  quand le lot est sur le point d'être lancé.
