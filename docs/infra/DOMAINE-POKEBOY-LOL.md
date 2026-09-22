# Bascule sur `pokeboy.lol` — 22/09/2026

Domaine canonique de la PROD : **`https://pokeboy.lol`**. `pokeboy.acx-connect.com` et
`www.pokeboy.lol` y renvoient en **308**. Le serveur n'a pas changé : toujours `kailo-srv`
(5.22.213.226, UpCloud « sites-and-crons », partagé avec kailo.life et ACX).

## DNS (GoDaddy, `ns39/ns40.domaincontrol.com`)

| Nom | Type | Valeur |
|---|---|---|
| `pokeboy.lol` | A | 5.22.213.226 *(posé par JF le 22/09 — remplaçait le parking GoDaddy 3.33.130.190 / 15.197.148.33)* |
| `www.pokeboy.lol` | A | 5.22.213.226 |
| `resend._domainkey.pokeboy.lol` | TXT | clé DKIM Resend |
| `send.pokeboy.lol` | MX + TXT | `send.forge.rmta.net` (retour et SPF Resend) |

Aucune clé d'API GoDaddy n'existe sur la flotte : **toute modification DNS passe par JF**,
dans la console. Ne pas chercher à automatiser cette étape sans qu'une clé soit décidée.

## Caddy

`/etc/caddy/pokeboy-prod.caddy`, importé par le `Caddyfile` de l'hôte. Trois vhosts :
`pokeboy.lol` (application), `www.pokeboy.lol` et `pokeboy.acx-connect.com` (308 vers l'apex).
Certificats Let's Encrypt obtenus le 22/09 à 08:23 UTC pour l'apex et `www`.

La bascule s'est faite **en deux temps**, et c'est la seule façon sûre de la refaire :

1. les trois noms servent l'application à l'identique, le temps d'obtenir les certificats ;
2. l'ancien nom passe en 308 **une fois seulement** qu'un bundle construit sur `pokeboy.lol`
   est déployé.

L'ordre importe parce que `NEXT_PUBLIC_API_URL` est **figée dans le bundle Next.js à la
construction**. Rediriger l'ancien nom avant le redéploiement couperait l'API du navigateur :
les pages seraient servies depuis `pokeboy.lol` pendant que leur JavaScript appellerait
`pokeboy.acx-connect.com/api`, devenu une redirection — une origine que le CORS de l'API
(`allow_origins=[APP_PUBLIC_URL]`) n'autorise plus.

## Ce qui porte le nom de domaine, et où

| Réglage | Emplacement | Valeur |
|---|---|---|
| `APP_PUBLIC_URL` | `/srv/pokeboy/prod/config/.env` | `https://pokeboy.lol` — liens des e-mails **et** unique origine CORS |
| `API_PUBLIC_URL` | idem | `https://pokeboy.lol/api` — lien de téléchargement d'export RGPD |
| `NEXT_PUBLIC_API_URL` | **figée à la construction** : `pbm-build.sh` / `pbm-build-lol.sh` (chimera), `build-pbm.sh` (devAI) | `https://pokeboy.lol/api` |
| `metadataBase` | `apps/web/src/app/layout.tsx` | `https://pokeboy.lol`, surchargeable par `NEXT_PUBLIC_SITE_URL` |

> ⚠️ **Les trois scripts de construction portent l'URL en dur.** Ils ont tous été corrigés le
> 22/09. Si un jour le domaine rebouge, les corriger **ensemble** : un seul script oublié et le
> déploiement suivant réinstalle silencieusement l'ancien domaine dans le navigateur, sans que
> rien n'échoue — le site répond, l'API est simplement injoignable depuis les pages.

## E-mails transactionnels — Resend en SMTP

`SMTP_HOST=smtp.resend.com`, port **587** (STARTTLS), utilisateur `resend`, mot de passe = la
clé Resend (`~/.pokeboy-secrets/resend.key` sur devAI, portée « envoi » seule).
Expéditeur : `PokéBoy <no-reply@pokeboy.lol>`.

`pbm_api.email.SmtpEmailSender` fait STARTTLS + `login()` dès que `SMTP_USER` est renseigné —
aucun code n'a eu besoin de changer. Tant que `SMTP_HOST` restait vide, l'envoi était désactivé
proprement (`DisabledEmailSender`) : **l'inscription libre décidée en D8 ne pouvait pas
fonctionner**. Elle le peut depuis le 22/09.

Vérifié par un envoi réel accepté par Resend le 22/09 (`no-reply@pokeboy.lol` →
`jfonteray@gmail.com`). C'est le seul contrôle possible : la clé n'a pas la portée `/domains`,
`GET /domains` répond 401 — ce n'est pas une panne, c'est le bon réglage.

## Marque

Icône et logotype fournis par JF le 22/09, déclinés dans `apps/web` :

- `src/app/favicon.ico`, `src/app/icon.png`, `src/app/apple-icon.png`,
  `src/app/opengraph-image.jpg` — **conventions de fichiers Next.js** : détectées à la
  construction, aucune balise à écrire. Ne pas les redéclarer dans `metadata.icons`, cela
  produirait des balises concurrentes.
- `public/icons/` — `icon-192`, `icon-512`, `icon-maskable-512`, `favicon-32` : destinés au
  manifeste PWA du lot `v6-pwa`, qui n'a plus à fabriquer d'icônes.
- `public/brand/pokeboy-logotype.png` — logotype horizontal sur fond bleu nuit.

Couleurs de la charte : bleu nuit `#050A30` (fond), violet Master Ball `#9D00FF` (halos),
or `#FFD700` (titres, appels à l'action), rose fuchsia `#FF1493` (liserés), gris clair
`#E0E0E0` (texte).

> **Point ouvert.** Le nom affiché devient « PokéBoy » (icône, logotype, domaine), mais la
> décision **D8** fixe le nom public à « PokeBoyManager » et c'est ce nom qui figure dans les
> CGU, les mentions légales et le pied de page. À trancher par JF : aligner les textes légaux
> sur « PokéBoy », ou garder les deux (marque d'usage / raison sociale du service).
