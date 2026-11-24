"""HTTP authentication middleware for the MCP endpoint."""

import hmac
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from raspberry_mcp.token_policy import (
    MIN_TOKEN_LENGTH,
    TOKEN_ENV_VAR,
    validate_token,
)


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """Require a shared bearer token for every HTTP request."""

    def __init__(self, app: Callable, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        authorization = request.headers.get("authorization", "")
        scheme, separator, supplied_token = authorization.partition(" ")

        if (
            not separator
            or scheme.lower() != "bearer"
            or not hmac.compare_digest(
                supplied_token.encode("utf-8"), self._token.encode("utf-8")
            )
        ):
            return JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="raspberry-mcp"'},
            )

        return await call_next(request)
