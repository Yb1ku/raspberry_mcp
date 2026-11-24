"""HTTP authentication middleware for the MCP endpoint."""

import hmac
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


TOKEN_ENV_VAR = "RASPBERRY_MCP_TOKEN"
MIN_TOKEN_LENGTH = 32


def validate_token(token: str | None) -> str:
    """Validate a runtime token without including its value in any error."""
    if token is None or not token.strip():
        raise ValueError(
            f"{TOKEN_ENV_VAR} is required and must be a private random secret."
        )
    if token != token.strip() or any(character.isspace() for character in token):
        raise ValueError(
            f"{TOKEN_ENV_VAR} must not contain whitespace."
        )
    if len(token) < MIN_TOKEN_LENGTH:
        raise ValueError(
            f"{TOKEN_ENV_VAR} must contain at least {MIN_TOKEN_LENGTH} characters."
        )
    if len(set(token)) < 8 or len(set(token)) == 1:
        raise ValueError(f"{TOKEN_ENV_VAR} must be a random secret.")
    return token


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
