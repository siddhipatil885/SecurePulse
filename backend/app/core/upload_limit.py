"""Bound multipart uploads before the parser can spool a large video to disk."""
import re

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app.core.config import get_settings


class EvidenceUploadLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope['type'] != 'http' or scope.get('method') != 'POST'
                or not re.fullmatch(r'/api/v1/(reporter/incidents/[1-9][0-9]*/evidence|marshal/onboarding)/?', scope.get('path', ''))):
            return await self.app(scope, receive, send)
        limit = (9_000_000 if scope.get('path', '').rstrip('/').endswith('/marshal/onboarding')
                 else get_settings().reporter_evidence_max_bytes) + 65536
        headers = dict(scope.get('headers', []))
        try:
            length = int(headers.get(b'content-length', b'0'))
        except ValueError:
            length = limit + 1
        if length < 0 or length > limit:
            return await JSONResponse({'error': {'code': 'EVIDENCE_TOO_LARGE',
                'message': 'Evidence exceeds the configured size limit.'}}, status_code=413)(scope, receive, send)
        received = 0
        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get('body', b''))
            if received > limit:
                raise HTTPException(413, 'Evidence exceeds the configured size limit.')
            return message
        return await self.app(scope, bounded_receive, send)
