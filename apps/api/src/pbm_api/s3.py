"""Client S3 (MinIO en local, Object Storage en ligne — D7). Synchrone (boto3), délégué à un
thread pour ne pas bloquer la boucle asyncio, comme le reste de l'API attend des appels I/O non
bloquants.
"""

import asyncio
from functools import cached_property

import boto3
from botocore.exceptions import ClientError

from pbm_api.config import settings


class ObjectStorage:
    def __init__(
        self,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        region: str | None = None,
    ) -> None:
        self._endpoint_url = endpoint_url or settings.s3_endpoint_url
        self._access_key = access_key or settings.s3_access_key
        self._secret_key = secret_key or settings.s3_secret_key
        self.bucket = bucket or settings.s3_bucket
        self._region = region or settings.s3_region

    @cached_property
    def _client(self):
        return boto3.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
        )

    def _ensure_bucket_sync(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self.bucket)

    async def ensure_bucket(self) -> None:
        await asyncio.to_thread(self._ensure_bucket_sync)

    def _get_sync(self, key: str) -> bytes | None:
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise

    async def get(self, key: str) -> bytes | None:
        return await asyncio.to_thread(self._get_sync, key)

    def _put_sync(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(self._put_sync, key, data, content_type)

    def _presign_put_sync(self, key: str, content_type: str, expires_in: int) -> str:
        return self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_in,
        )

    async def presign_put(self, key: str, content_type: str, expires_in: int = 900) -> str:
        """URL présignée S3 : le navigateur envoie directement au stockage (lot `v3-upload`)."""
        return await asyncio.to_thread(self._presign_put_sync, key, content_type, expires_in)
