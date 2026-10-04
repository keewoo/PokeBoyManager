# Assistance IA — proposer le script d'une carte, jamais le valider seule

> Lot `j-effets-assistance-ia` (jalon J2), décision **DJ8**. Écrire à la main les scripts d'effet de
> dizaines de milliers de cartes n'arrivera jamais au bout. L'IA sait lire un texte de carte et
> proposer un script — **à condition que rien n'entre en jeu sans être prouvé**. Cette fiche décrit
> le garde-fou.

## La décision qui fait foi (DJ8)

L'IA propose le script d'effet d'une carte **ET** ses cas de test, à partir du texte. Le script
n'entre en jeu (`scripte`) **que si** :

1. **ses tests passent** — les essais proposés rejoués contre le moteur réel, **plus** une batterie
   de cohérence maison (l'effet ne crée ni ne détruit de carte, l'état reste valide) ; **et**
2. une **seconde IA, chargée de le contredire**, l'a **approuvé** — jamais une relecture humaine
   carte par carte.

Un **rapport par famille** d'effets est fait à JF, qui peut **retirer une famille d'un mot**. La clé
est la **clé plateforme** (jamais celle d'un utilisateur). Plafond cumulé **50 €**, coût journalisé
par carte, reprise après interruption. **Sans clé**, le lot livre son outillage, ses tests et une
**mesure sur un fournisseur factice**, sans dépense.

Le risque central, nommé dans la fiche : *un script plausible mais faux est plus dangereux qu'une
carte non supportée — il fait perdre des parties sans que personne ne comprenne.* Le vrai garde-fou
n'est donc **pas** la confiance annoncée par le modèle, mais l'**exécution réelle** (les tests et la
cohérence maison).

## La chaîne, bout à bout

| Étape | Où | Rôle |
|---|---|---|
| Sélection (priorité DJ2) | `assistance.runner.selectionner_effets` | les effets des cartes **possédées** d'abord, puis les plus **fréquents** ; jamais ceux déjà tranchés |
| Prompt de proposition | `assistance.gabarit.prompt_proposition` | texte (FR/EN), **grammaire dérivée du moteur**, exemples validés proches, format strict |
| Appel IA | `assistance.fournisseur` | réel (`AnthropicGenerateur`, API Messages synchrone) ou **factice** (`FournisseurFactice`) |
| Tests | `pbm_game.effets.dsl.essais.verifier_script` | charge le script (DSL), rejoue **chaque essai**, contrôle la **cohérence maison** |
| Contradiction | `assistance.gabarit.prompt_contradiction` | la 2ᵉ IA cherche la faille, rejette au doute, peut fournir un **contre-cas** |
| Porte | `assistance.verification.evaluer` | **pure** : `scripte` ssi tests verts ET contradicteur approuve ; sinon `non_supporte`/`a_revoir`, nommé |
| Écriture | `assistance.depot.enregistrer_script` | le registre `card_scripts`, avec les colonnes de revue (preuve de la porte) |
| Budget & reprise | `assistance.budget` (grand livre JSON) | dépense cumulée, coût par carte, effets déjà tranchés (reprise) |
| Rapport | `assistance.runner.rapport_texte` | par famille (ce que JF lit) + mesures de rendement |

Le cœur (`familles`, `gabarit`, `verification`) et les essais (`pbm_game`) sont **purs** ; seuls le
`runner` et le fournisseur réel touchent la base, le réseau et le grand livre.

## La porte est tenue par la base, pas par une consigne

La table `card_scripts` porte une contrainte CHECK `ck_card_scripts_scripte_gate` :

```
statut <> 'scripte' OR (script IS NOT NULL AND validated_at IS NOT NULL AND review_tests_ok IS TRUE)
```

Impossible donc de faire entrer un script en jeu sans la preuve de la porte, **même par un INSERT
direct** qui contournerait le code (critère d'acceptation n°1). Les colonnes de revue
(`review_tests_ok`, `review_contradicteur`, `famille`, `confidence`, `cost_eur`) gardent la trace de
la décision pour l'audit et le rapport. Un `scripte` écrit par un chemin d'avant DJ8
(import/validation humaine) **vouche** ses tests : `enregistrer_script` pose `review_tests_ok=True`
par défaut, ce qui préserve ces chemins sans affaiblir la contrainte.

## L'exploitation

```bash
cd apps/api

# Mesure sans dépense (clé absente) — fournisseur factice, DJ8 :
DATABASE_URL=... uv run python scripts/assistance_scripts_ia.py --factice --limite 20

# Passage réel — clé plateforme par fichier chmod 600 (plafond 50 € par défaut) :
DATABASE_URL=... uv run python scripts/assistance_scripts_ia.py \
    --fichier-cle ~/.pokeboy-secrets/platform-anthropic-key --limite 100

# ou la clé par l'entrée standard :
cat ~/.pokeboy-secrets/platform-anthropic-key | DATABASE_URL=... \
    uv run python scripts/assistance_scripts_ia.py --limite 100
```

- **La clé plateforme vit sur devAI** (`~/.pokeboy-secrets/platform-anthropic-key`), jamais dans le
  dépôt, un journal ou une sortie (DJ8). Le CLI la lit sans jamais l'afficher et ne la conserve pas
  au-delà de l'appel. **Jamais la clé d'Aymeric.**
- Le **plafond (50 €) est cumulatif** sur tous les passages (grand livre `var/assistance_scripts/
  ledger.json`). Le passage s'arrête net au plafond, sans redemander.
- Le coût d'un appel est au **tarif standard** (API synchrone, pas la remise Batch) :
  `assistance.pricing.cout_usd` = 2 × le tarif Batch de `insights_batch.pricing` (source unique à
  réviser au même endroit).
- **Reprise** : un effet déjà tranché (scripté, non supporté, ou à revoir) n'est ni re-proposé ni
  re-payé ; le grand livre est sauvé après **chaque** effet.

## Les mesures de rendement (mission point 5)

Chaque passage publie : part des propositions **acceptées sans retouche**
(`scriptes / (scriptes + a_revoir)`), part **rejetée** (`a_revoir / …`), **coût par script validé**
(dépense cumulée / scriptés), et la dépense totale. Les `non_supporte` sont des **refus** (l'IA dit
« hors langage »), pas des rejets : comptés à part.

## Ce qui n'est délibérément pas fait

- **Pas de texte EN séparé** par effet pour l'instant : le registre range un texte d'effet par
  empreinte (le catalogue stocke le texte dans une langue, fr avec repli en). Le prompt accepte un
  texte EN quand on en a un ; l'alimenter est une amélioration future.
- **Aucune dépense réelle dans ce lot** : il livre l'outillage, ses tests et la mesure sur
  fournisseur factice. Le passage réel (clé plateforme, 50 €) est une opération à lancer depuis
  devAI, où vit la clé — jamais depuis le Mac de JF, jamais sur la machine qui sert.
