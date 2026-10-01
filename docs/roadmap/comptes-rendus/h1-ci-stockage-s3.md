# Compte rendu — `h1-ci-stockage-s3` — La CI retrouve son stockage S3 : MinIO remplacé par SeaweedFS

**Statut : CI verte sur la branche (`1c16540`), fusion dans `main` en avance rapide.**
Piste Fondations & livraison · couloir DA2 (devAI) · aucune dépendance · 01/10/2026.

## Ce qui s'est passé

Le 01/10, le push de `a97a6c1` sur `main` a rougi `api` et `e2e` — `web` restait vert. Ce n'était
pas le code : les deux jobs mouraient à l'étape *Start MinIO*, avant le premier test.

```
Unable to find image 'quay.io/minio/minio:latest' locally
docker: Error response from daemon: unauthorized: access to the requested resource is not authorized
```

Vérifié avant de conclure à une panne durable : `quay.io/api/v1/repository/minio/minio` répond
**401** en anonyme, `hub.docker.com/v2/repositories/minio/minio/` répond **404** et le manifeste
`docker.io/minio/minio:latest` **401**. MinIO n'est plus distribué en image. Le commit précédent
(`5308dc2`, 23/09) était vert : à partir du 01/10, **toute** CI du dépôt aurait été rouge.

La PROD n'est pas concernée : elle stocke les photos sur disque (`STORAGE_BACKEND=local`, D7).

## Le choix : mesuré, pas supposé

Une sonde (`apps/api/scripts/sonde_s3.py`) rejoue ce que le produit exige d'un serveur S3 :
`ObjectStorage` (bucket absent → `ClientError`, objets, `NoSuchKey`/`404`), `test_uploads.py`
(URL présignée **SigV2** — c'est ce que boto3 produit ici — avec Content-Type signé, et **refusée
en 403 avec un autre type**), et l'e2e d'envoi de photo (**CORS** : pré-vol `OPTIONS` et `PUT`
cross-origin, sans configuration de bucket). Chaque candidat a tourné dans un conteneur sur devAI,
la sonde dans un conteneur voisin sur le même réseau Docker.

| Candidat | Verdict | Détail |
|---|---|---|
| MinIO (référence — image restée en cache sur devAI) | conforme | sert d'étalon : la sonde décrit bien ce qui marchait |
| **SeaweedFS 4.48** (`chrislusf/seaweedfs`) | **conforme — retenu** | pré-vol 200, `Access-Control-Allow-Origin` renvoie l'origine |
| RustFS 1.0.0 | non conforme | **aucun** en-tête CORS : l'envoi depuis le navigateur échouerait en e2e |
| adobe/s3mock 5.2.3 | non conforme | accepte une URL signée avec **un autre** Content-Type : les signatures ne sont pas vérifiées — des tests verts n'y prouveraient plus rien |

Contrôles complémentaires sur SeaweedFS : mauvais secret → `SignatureDoesNotMatch`, clé inconnue →
`InvalidAccessKeyId` (l'authentification est bien active) ; `GET /healthz` → 200 ; sain en **6 s**.

## Livrables

- `.github/workflows/ci.yml` : étape *Start SeaweedFS (S3)* dans les jobs `api` et `e2e`, image
  épinglée `chrislusf/seaweedfs:4.48`, publiée sur le port 9000 (aucune variable `S3_*` ne change),
  attente sur `/healthz`, journaux du conteneur imprimés en cas d'échec.
- `docker-compose.yml` : service `s3` (plus `minio`), mêmes identifiants que l'API
  (`S3_ACCESS_KEY`/`S3_SECRET_KEY`), port `S3_API_PORT` (59000 par défaut), healthcheck `wget`
  sur `/healthz`, volume `pbm_s3_data`. `.env.example` suit (`MINIO_*` retirées).
- `apps/api/scripts/sonde_s3.py` : la sonde, gardée pour revalider tout remplaçant futur.
- Fiches : `docs/CODE.md` § « Stockage S3 de dev/CI » (verdicts, règles, piège `-ip.bind`) ;
  `ARCHITECTURE`, `PLUGINS`, `SECURITE`, `LIVRAISON`, `README` et les commentaires de code qui
  nommaient MinIO comme serveur courant.

## Preuves

- **CI GitHub Actions verte sur `1c16540`** (branche `roadmap/h1-ci-stockage-s3`) :
  `api` — ruff propre, **823 tests passés** ; `e2e` — **16 passés**, dont l'envoi réel d'une photo
  par le navigateur (`parcours-complet.spec.ts`) ; `web` vert.
- Sonde du dépôt contre SeaweedFS **lancé par le nouveau `docker-compose.yml`** (devAI) :
  conforme sur ses 13 contrôles, code de sortie 0.
- `docker compose config -q` valide ; healthcheck du compose `healthy` en 6 s.

## Écarts au plan / pièges

- **`-ip.bind=0.0.0.0` obligatoire.** Sans lui, SeaweedFS n'écoute que l'IP du conteneur au
  démarrage : le healthcheck du compose (`wget localhost`) restait `unhealthy` indéfiniment, et
  un réseau Docker branché après coup recevait `Connection refused`. La CI aurait marché sans (la
  redirection de port vise l'IP du conteneur) ; posé des deux côtés pour qu'ils restent identiques.
- **Colima de devAI ne publie plus les ports vers macOS** (`curl localhost:19000` → 000, y
  compris sur le MinIO de `wt-v6-import-export` en 59000) : d'où la sonde lancée dans un conteneur
  voisin. À regarder séparément — ce n'est pas le lot.
- Mentions de MinIO laissées volontairement : paragraphe daté « État au 19/09 » du README, analyse
  d'options de `docs/infra/SERVEUR-POKEBOY.md`, texte du lot `v0-monorepo` — ce sont des archives.

## Reste à faire

- **Clones existants** : le service change de nom → `docker compose up -d --remove-orphans`. Les
  objets de l'ancien MinIO ne sont pas repris (données de dev) ; plus de console web sur 59001.
- `axllent/mailpit:latest` reste une image flottante, contraire à la règle des tags fixes
  (`docs/CODE.md` § Versions) : même risque, pas encore réalisé.
