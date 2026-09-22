# Compte rendu — lot `pbm-aide-cle-ia`

Session autonome sur **devAI**, 2026-09-22. Une page d'aide, dans l'espace connecté, qui explique
**où trouver sa clé IA, combien ça coûte, et ce que le site en fait** — le premier obstacle d'un
nouvel utilisateur, jusqu'ici sans réponse.

## Verdict

**FAIT.** Nouvelle route `/profil/aide-cle`, réservée aux utilisateurs connectés, atteignable depuis
l'onglet « Mon IA » du profil et depuis l'écran d'envoi de photos sans clé. Tests, type-check et lint
verts (le seul rouge local, `app-shell.test.tsx`, échoue déjà sur `main` propre — accès `localStorage`
incompatible avec le Node 26 du poste ; la CI GitHub tourne en Node 24). Responsive vérifié aux quatre
largeurs, garde d'accès vérifiée, chaque URL contrôlée par requête HTTP.

## Ce qui a été livré

- **`apps/web/src/app/profil/aide-cle/page.tsx`** — Server Component, six sections :
  1. À quoi sert la clé (deux phrases).
  2. Parcours par fournisseur (Claude, Gemini, ChatGPT) : étapes numérotées, courtes ; forme de la
     clé (`sk-ant-`, `sk-`), besoin d'un crédit, lien vers la console. Les libellés d'interface
     décrivent l'**action** plutôt qu'un bouton précis (les consoles renomment souvent).
  3. Coûts avec nos vrais chiffres : ≈ 0,05 € pour une photo de 9 cartes, 27,32 € pour les 22 169
     fiches du catalogue, **facturé sur le compte du fournisseur de l'utilisateur**, pas par PokéBoy.
  4. Ce que le site fait de la clé : chiffrée (AES-256-GCM, clé maître hors base), jamais réaffichée
     en entier, jamais journalisée, usage limité aux traitements de l'utilisateur, supprimable en un
     clic — renvoi vers `/confidentialite`.
  5. Si ça ne marche pas : le **message exact** que le site affiche, repris tel quel du code serveur
     (voir « Fidélité des messages »).
  6. Rappel honnête : sans clé, l'ajout manuel, la collection, les valeurs et les fiches restent
     disponibles ; seule la reconnaissance automatique est indisponible.
- **`apps/web/src/components/profile/ai-tab.tsx`** — lien « Où trouver une clé, combien ça coûte,
  que faire si ça ne marche pas ? » vers la page d'aide.
- **`apps/web/src/app/ajouter/upload-view.tsx`** — état « aucune clé » : lien « Où trouver une clé et
  combien ça coûte ? » vers la page d'aide, en second recours après le bouton de configuration.
- **`apps/web/src/components/profile/profile-tabs.tsx`** — `?onglet=ia` (et `securite`, `donnees`)
  ouvre directement le bon onglet, pour que le retour depuis la page d'aide tombe sur « Mon IA ».

## Réservée aux connectés

`/profil/aide-cle` tombe sous le préfixe `/profil` déjà gardé par `apps/web/src/middleware.ts`.
Vérifié sur le build de production local : sans cookie de session → **307** vers
`/connexion?next=/profil/aide-cle` ; avec cookie → **200**.

## Fidélité des messages d'erreur

Les messages de la section 5 sont **copiés du code serveur**, pas inventés :

| Cas | Message affiché | Source |
|---|---|---|
| Clé refusée (bouton « Tester ») | « Clé refusée par le fournisseur. » | `apps/api/src/pbm_api/ai/providers.py` |
| Clé invalide/révoquée (reconnaissance) | « Clé invalide ou révoquée par le fournisseur. » | `apps/api/src/pbm_api/ai/errors.py` |
| Quota / crédit épuisé | « Quota dépassé chez le fournisseur. » | `errors.py` |
| Fournisseur indisponible | « Fournisseur surchargé — réessayez plus tard. » / « … injoignable … » | `errors.py`, `providers.py` |

Un test statique (`aide-cle.test.tsx`) vérifie que ces chaînes exactes sont présentes dans la page :
si le message serveur change sans que la page suive, le test mord.

## Liens vérifiés par requête HTTP

| URL | Résultat |
|---|---|
| `https://console.anthropic.com/settings/keys` | 200 |
| `https://aistudio.google.com/app/apikey` | 200 |
| `https://platform.openai.com/api-keys` | 403 — **challenge Cloudflare**, pas un lien mort : l'hôte répond, l'URL est la page canonique d'OpenAI et celle déjà utilisée par l'onglet « Mon IA ». Confirmé aussi via WebFetch (même 403 anti-bot). |
| `/confidentialite` | route interne existante |

## Responsive et accessibilité

Mesure `document.documentElement.scrollWidth ≤ innerWidth` (la mesure de `e2e/responsive.spec.ts`),
sur le build de production, cookie de session posé :

| Largeur | scrollWidth | Débordement |
|---|---|---|
| 320 | 320 | non |
| 390 | 390 | non |
| 768 | 768 | non |
| 1280 | 1280 | non |

Un défaut a été trouvé et corrigé pendant la vérif : le bouton « Aller à Mon IA … », en
`whitespace-nowrap` (défaut du composant `Button`), débordait à 320/390px (399px de large) — même
piège que celui déjà documenté dans `upload-view.tsx`. Corrigé en autorisant le libellé à passer sur
deux lignes (`h-auto min-h-11 whitespace-normal`) et en raccourcissant le texte. La mise en page est en
`flex flex-col` plutôt qu'en `grid` : une piste de grille implicite est dimensionnée en `max-content`
et ne rétrécit pas sous 640px.

Titres hiérarchisés (un seul `h1`, `h2` par section, `h3` par fournisseur et par cas d'erreur), liens
et boutons natifs → navigables au clavier sans JS.

`/profil/aide-cle` a été ajoutée à la liste des pages privées de `e2e/responsive.spec.ts`.

Captures (build local, cookie factice — le middleware ne vérifie que la présence du cookie) :
`docs/roadmap/comptes-rendus/captures/pbm-aide-cle-390.png` (mobile) et `…-1280.png` (desktop).

## Tests

- `apps/web/src/__tests__/aide-cle.test.tsx` (nouveau, 7 tests) : titre, trois fournisseurs, liens de
  console + hrefs, vrais chiffres de coût, renvoi vers confidentialité, messages d'erreur exacts,
  rappel « sans clé ».
- `profil.test.tsx` : `?onglet=ia` ouvre directement l'onglet « Mon IA » (mock `useSearchParams`
  rendu mutable).
- `upload-view.test.tsx` : le bouton pointe désormais vers `/profil?onglet=ia`, et le lien d'aide vers
  `/profil/aide-cle`.

## Déploiement

Voir la section dédiée du rapport de session `~/dev/logs/pbm-aide-cle-rapport.md` (build chimera →
devAI → kailo-srv, release et preuve).
