# Release — ce qui sort, quand, et sous quel nom

> **À lire avant d'annoncer une version.** Le geste de décision : quoi sort, qui tranche, comment
> ça se nomme, ce qu'on écrit à ceux qui l'utilisent.
> Ce qui n'est pas ici : **comment** on met en ligne (`docs/LIVRAISON.md`).
> La différence tient en une phrase : une **livraison** est technique et peut se refaire dix fois
> dans la journée ; une **release** est un état annoncé, et elle s'adresse à quelqu'un.

## Qui décide

**JF.** Le pilote propose, JF tranche — comme pour les décisions `D*` du plan. Ce qui sort, à qui,
et quand, n'est jamais décidé par un lot ni par une session Claude.

Les utilisateurs sont **nommés** : JF, Aymeric (`bibi`), et les comptes invités (D11). Une release
n'est donc pas un communiqué : c'est un message à trois personnes qui connaissent le produit.
Elle s'écrit dans leur langue, pas dans celle du dépôt — « les cartes se trient par valeur », pas
« ajout d'un index `pg_trgm` sur `card_names` ».

## L'état des lieux (à la date de cette fiche)

| | |
|---|---|
| Tags git | **aucun** |
| `CHANGELOG.md` | **aucun** |
| Gel (`meta.gel` de `roadmap.json`) | non posé |
| Ce qui existe | les **comptes rendus de lots** (`docs/roadmap/comptes-rendus/`, ou dans `etat.json`), écrits pour le dépôt, et les **jalons** du plan |

Autrement dit : le projet sait dire ce qu'un lot a fait, pas ce qu'une version apporte. C'est ce
trou que cette fiche ferme.

## La convention — défaut provisoire du pilote, à confirmer par JF

1. **Une release = un commit mis en PROD et annoncé.** Pas de branche de release, pas de
   cherry-pick : on livre `main`, qui est vert en CI.
2. **Nom : `vAAAA.MM.JJ`** (`v2026.09.20` pour la mise en ligne du MVP), suffixé `-2`, `-3` s'il y
   a plusieurs releases le même jour. Une date se comprend sans être expliquée ; un numéro
   sémantique n'a pas de sens pour un produit à trois utilisateurs qui n'ont pas d'API à casser.
3. **Le tag se pose sur le commit réellement livré**, après la preuve de mise en ligne — jamais
   avant. Un tag est ce qui rend le retour arrière trivial.
4. **`CHANGELOG.md` à la racine**, le plus récent en haut, trois rubriques au plus :
   *Nouveau* · *Corrigé* · *À savoir*. Cinq lignes suffisent. On y écrit ce que l'utilisateur voit.
5. **Ce qui a changé pour l'exploitation** (nouvelle variable d'environnement, migration
   destructive, nouveau service) se répète dans `docs/LIVRAISON.md` — le CHANGELOG est pour les
   gens, la fiche de livraison pour celui qui déploie à 2 h du matin.

### Gabarit d'entrée

```markdown
## v2026.09.20 — Le MVP est en ligne

**Nouveau.** Photographier ses cartes, les faire reconnaître par sa propre IA, les retrouver dans
sa collection filtrable, et voir la valeur de chacune dans le temps.
**À savoir.** Il faut déposer sa clé IA dans Profil → Mon IA pour que la reconnaissance marche.
```

## La check-list, dans l'ordre

1. La CI est verte sur le commit.
2. La revue de sécurité est à jour si le périmètre a bougé (`docs/SECURITE.md`).
3. La livraison est faite et **prouvée** (`docs/LIVRAISON.md` § « Conclure "déployé" »).
4. Le tag `vAAAA.MM.JJ` est posé et poussé.
5. L'entrée `CHANGELOG.md` est écrite — pour Aymeric, pas pour le dépôt.
6. Le plan est mis à jour : `python3 docs/roadmap/suivi.py statut <lot> livre`, puis
   `suivi.py build`, puis la page publiée est republiée.
7. Le graphe est reconstruit sur le commit livré : `graphify update .`.
8. JF est prévenu, en une phrase, avec ce qui a changé pour lui.

## Ce qu'on ne fait pas

- **Livrer un vendredi soir** ce qui touche aux données ou aux migrations.
- **Annoncer une release qu'on n'a pas vue tourner** : la preuve d'abord, l'annonce ensuite.
- **Livrer un périmètre réduit sans le dire.** Livrer moins n'est pas une faute ; le taire en est
  une. Ce qui manque se nomme, dans le CHANGELOG comme dans le message à JF.
- **Poser un gel** (`meta.gel`) sans le lever : un gel oublié bloque tous les lots suivants en
  silence.

