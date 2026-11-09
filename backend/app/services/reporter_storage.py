"""Private reporter attachments, with local compatibility and Neon S3 storage."""
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

from fastapi.responses import FileResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import ApplicationError


HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}


class ReporterStorage:
    def __init__(self, settings):
        self.settings = settings

    def _client(self):
        import boto3
        from botocore.config import Config
        settings = self.settings
        return boto3.client("s3", endpoint_url=settings.aws_endpoint_url_s3,
            region_name=settings.aws_region, aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                connect_timeout=5, read_timeout=20, retries={"max_attempts": 2},
                request_checksum_calculation="when_required", response_checksum_validation="when_required"))

    def _key(self, reference):
        parsed = urlsplit(reference)
        key = parsed.path.lstrip("/")
        if (parsed.scheme != "s3" or parsed.netloc != self.settings.evidence_bucket
                or not re.fullmatch(r"(?:reporter-incidents/[1-9][0-9]*|marshal-assignments/[1-9][0-9]*)/[a-f0-9]{32}\.(jpg|png|mp4)", key)
                or parsed.query or parsed.fragment):
            raise ApplicationError("MEDIA_NOT_FOUND", "Evidence media is unavailable.", 404)
        return key

    def _local(self, reference):
        if not self.settings.evidence_root:
            raise ApplicationError("MEDIA_NOT_CONFIGURED", "Evidence storage is not configured.", 503)
        root = Path(self.settings.evidence_root).resolve()
        path = (root / reference).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ApplicationError("MEDIA_NOT_FOUND", "Evidence media is unavailable.", 404)
        return path

    async def _s3(self, method, **kwargs):
        if self.settings.evidence_storage != "s3":
            raise ApplicationError("MEDIA_NOT_CONFIGURED", "Cloud media storage is disabled. This media must be available on the host.", 503)
        from botocore.exceptions import BotoCoreError, ClientError
        try:
            def request():
                client = self._client()
                try:
                    result = getattr(client, method)(Bucket=self.settings.evidence_bucket, **kwargs)
                    if method == "get_object":
                        result["_client"] = client
                    else:
                        client.close()
                    return result
                except BaseException:
                    client.close()
                    raise
            return await run_in_threadpool(request)
        except ClientError as error:
            status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 404:
                raise ApplicationError("MEDIA_NOT_FOUND", "Evidence media is unavailable.", 404) from None
            if status == 416:
                raise ApplicationError("INVALID_RANGE", "The requested media range is unavailable.", 416) from None
            raise ApplicationError("MEDIA_UNAVAILABLE", "Evidence storage is temporarily unavailable.", 503) from None
        except BotoCoreError:
            raise ApplicationError("MEDIA_UNAVAILABLE", "Evidence storage is temporarily unavailable.", 503) from None

    async def put(self, key, content, media_type):
        if self.settings.evidence_storage == "s3":
            reference = f"s3://{self.settings.evidence_bucket}/{key}"
            self._key(reference)
            await self._s3("put_object", Key=key, Body=content, ContentType=media_type, CacheControl="private, no-store")
            return reference
        if not self.settings.evidence_root:
            raise ApplicationError("MEDIA_NOT_CONFIGURED", "Evidence storage is not configured.", 503)
        root = Path(self.settings.evidence_root).resolve()
        path = (root / key).resolve()
        if not path.is_relative_to(root):
            raise ApplicationError("MEDIA_NOT_FOUND", "Evidence media is unavailable.", 404)
        def write():
            path.parent.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(root).free - len(content) < self.settings.reporter_evidence_min_free_bytes:
                raise ApplicationError("HOST_STORAGE_LIMIT", "The host is low on disk space. Contact the property operator.", 507)
            path.write_bytes(content)
        await run_in_threadpool(write)
        return key

    async def ensure(self, reference):
        if reference.startswith("s3://"):
            await self._s3("head_object", Key=self._key(reference))
        else:
            self._local(reference)

    async def serve(self, reference, media_type, range_header=None):
        if not reference.startswith("s3://"):
            return FileResponse(self._local(reference), media_type=media_type, headers=HEADERS)
        if range_header and not re.fullmatch(r"bytes=(?:[0-9]+-[0-9]*|-[0-9]+)", range_header):
            raise ApplicationError("INVALID_RANGE", "Request one valid media byte range.", 416)
        result = await self._s3("get_object", Key=self._key(reference), **({"Range": range_header} if range_header else {}))
        body = result["Body"]
        async def chunks():
            try:
                while chunk := await run_in_threadpool(body.read, 65536):
                    yield chunk
            finally:
                await run_in_threadpool(body.close)
                await run_in_threadpool(result["_client"].close)
        headers = {**HEADERS, "Accept-Ranges": "bytes", "Content-Length": str(result["ContentLength"])}
        if result.get("ContentRange"):
            headers["Content-Range"] = result["ContentRange"]
        return StreamingResponse(chunks(), media_type=media_type,
            status_code=206 if "ContentRange" in result else 200, headers=headers)

    async def discard(self, reference):
        """Compensate only the new object if its database transaction failed."""
        if reference.startswith("s3://"):
            await self._s3("delete_object", Key=self._key(reference))
        else:
            await run_in_threadpool(self._local(reference).unlink)
