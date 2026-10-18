"""Bound photo HTTP bodies before Starlette can parse or spool multipart content."""

import re

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class PhotoBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if not (
            scope["type"] == "http"
            and scope["method"] == "POST"
            and re.fullmatch(r"/api/v1/inventory/items/[^/]+/photos", scope["path"])
        ):
            await self.app(scope, receive, send)
            return

        async def reject():
            response = JSONResponse(
                {
                    "detail": {
                        "code": "photo_too_large",
                        "message": "Размер загрузки слишком велик.",
                    }
                },
                status_code=413,
                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
            )
            await response(scope, receive, send)

        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    if int(value) > self.max_body_bytes:
                        await reject()
                        return
                except ValueError:
                    await reject()
                    return
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.max_body_bytes:
                await reject()
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        delivered = False

        async def replay():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, replay, send)
