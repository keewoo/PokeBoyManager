"""Sonde du serveur S3 de dev/CI : ce que PokeBoyManager exige de lui (lot `h1-ci-stockage-s3`).

Écrite le 01/10/2026 quand MinIO a cessé d'être distribué en image : elle a servi à choisir son
remplaçant, et sert à revalider tout remplaçant futur AVANT de toucher à la CI. Elle rejoue ce que
font `pbm_api.s3.ObjectStorage`, `tests/test_uploads.py` et l'e2e d'envoi de photo :

- bucket absent → `ClientError` (c'est sur lui que `ensure_bucket` décide de créer) ;
- objets : écriture, lecture identique, taille par `HEAD`, codes `NoSuchKey`/`404` sur clé absente ;
- URL présignée (SigV2, telle que boto3 la produit ici) avec Content-Type signé : acceptée avec le
  bon type, **refusée (403) avec un autre** — un serveur qui accepte tout ne prouve plus rien ;
- CORS : le navigateur dépose la photo en direct, d'une autre origine — pré-vol `OPTIONS` et
  `PUT` doivent renvoyer `Access-Control-Allow-Origin`, sans configuration de bucket.

Résultat du 01/10/2026 (compte rendu du lot) : MinIO et SeaweedFS 4.48 conformes sur tous les
contrôles ; RustFS 1.0.0 sans CORS ; adobe/s3mock 5.2.3 sans vérification de signature.

Exemple (identifiants et endpoint par défaut : ceux de `pbm_api.config.settings`) :

    UV_PYTHON=3.12 uv run python scripts/sonde_s3.py http://localhost:59000

Code de sortie : 0 si tout est conforme, 1 sinon — chaque contrôle est imprimé, aucun n'est tu.
"""

import argparse
import sys
import uuid
from collections.abc import Callable

import boto3
import httpx
from botocore.exceptions import ClientError

from pbm_api.config import settings

ORIGIN = "http://localhost:3000"
DATA = b"\xff\xd8" + b"x" * 2_000_000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("endpoint", nargs="?", default=settings.s3_endpoint_url)
    parser.add_argument("--access-key", default=settings.s3_access_key)
    parser.add_argument("--secret-key", default=settings.s3_secret_key)
    args = parser.parse_args()

    client = boto3.client(
        "s3",
        endpoint_url=args.endpoint,
        aws_access_key_id=args.access_key,
        aws_secret_access_key=args.secret_key,
        region_name=settings.s3_region,
    )
    bucket = f"pbm-sonde-{uuid.uuid4().hex[:8]}"
    results: list[tuple[str, bool, str]] = []

    def check(name: str, probe: Callable[[], object]) -> None:
        try:
            detail = probe()
            results.append((name, True, "" if detail is None else str(detail)))
        except Exception as exc:  # la sonde rapporte l'échec, elle ne l'avale pas
            results.append((name, False, f"{type(exc).__name__}: {exc}"[:220]))

    def error_code_on_missing(operation: Callable[..., object]) -> str:
        try:
            operation(Bucket=bucket, Key="absent.jpg")
        except ClientError as exc:
            code = exc.response["Error"].get("Code")
            if code not in ("NoSuchKey", "404"):
                raise AssertionError(f"code inattendu {code}") from exc
            return code
        raise AssertionError("aucune erreur sur une clé absente")

    def head_missing_bucket() -> str:
        try:
            client.head_bucket(Bucket=bucket)
        except ClientError as exc:
            return f"ClientError {exc.response['Error'].get('Code')}"
        raise AssertionError("head_bucket sur un bucket absent n'a pas levé")

    def read_back() -> None:
        body = client.get_object(Bucket=bucket, Key="a.jpg")["Body"].read()
        if body != DATA:
            raise AssertionError("contenu relu différent")

    def content_length() -> int:
        length = client.head_object(Bucket=bucket, Key="a.jpg")["ContentLength"]
        if length != len(DATA):
            raise AssertionError(f"ContentLength {length} au lieu de {len(DATA)}")
        return length

    def presign(key: str) -> str:
        return client.generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": key, "ContentType": "image/jpeg"},
            ExpiresIn=900,
        )

    def presigned_put() -> str | None:
        response = httpx.put(presign("p.jpg"), content=DATA, headers={"Content-Type": "image/jpeg"})
        if response.status_code != 200:
            raise AssertionError(f"{response.status_code} {response.text[:150]}")
        stored = client.get_object(Bucket=bucket, Key="p.jpg")
        if stored["Body"].read() != DATA:
            raise AssertionError("contenu déposé différent")
        return stored.get("ContentType")

    def presigned_put_wrong_type() -> int:
        response = httpx.put(presign("w.jpg"), content=b"x", headers={"Content-Type": "text/plain"})
        if response.status_code != 403:
            raise AssertionError(f"accepté avec un autre Content-Type : {response.status_code}")
        return response.status_code

    def cors_preflight() -> str:
        response = httpx.options(
            presign("c.jpg"),
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        allowed = response.headers.get("Access-Control-Allow-Origin")
        if response.status_code not in (200, 204) or allowed not in ("*", ORIGIN):
            raise AssertionError(f"{response.status_code} Access-Control-Allow-Origin={allowed}")
        return f"{response.status_code} Access-Control-Allow-Origin={allowed}"

    def cors_put() -> str:
        response = httpx.put(
            presign("q.jpg"), content=DATA, headers={"Content-Type": "image/jpeg", "Origin": ORIGIN}
        )
        allowed = response.headers.get("Access-Control-Allow-Origin")
        if response.status_code != 200 or allowed not in ("*", ORIGIN):
            raise AssertionError(f"{response.status_code} Access-Control-Allow-Origin={allowed}")
        return f"Access-Control-Allow-Origin={allowed}"

    def delete_then_missing() -> str:
        client.delete_object(Bucket=bucket, Key="a.jpg")
        return error_code_on_missing(client.get_object)

    check("head_bucket sur bucket absent → ClientError", head_missing_bucket)
    check("create_bucket", lambda: client.create_bucket(Bucket=bucket) and None)
    check("head_bucket sur bucket présent", lambda: client.head_bucket(Bucket=bucket) and None)
    check(
        "put_object",
        lambda: (
            client.put_object(Bucket=bucket, Key="a.jpg", Body=DATA, ContentType="image/jpeg")
            and None
        ),
    )
    check("get_object relit le même contenu", read_back)
    check("head_object donne la taille", content_length)
    check("get_object, clé absente → 404", lambda: error_code_on_missing(client.get_object))
    check("head_object, clé absente → 404", lambda: error_code_on_missing(client.head_object))
    check("PUT présigné, Content-Type signé", presigned_put)
    check("PUT présigné, autre Content-Type → 403", presigned_put_wrong_type)
    check("CORS : pré-vol OPTIONS du navigateur", cors_preflight)
    check("CORS : PUT depuis une autre origine", cors_put)
    check("delete_object puis clé absente", delete_then_missing)

    for name, ok, detail in results:
        print(f"  {'OK' if ok else 'KO'}  {name}{' — ' + detail if detail else ''}")
    conforme = all(ok for _, ok, _ in results)
    print(f"{args.endpoint} : {'CONFORME' if conforme else 'NON CONFORME'}")
    return 0 if conforme else 1


if __name__ == "__main__":
    sys.exit(main())
