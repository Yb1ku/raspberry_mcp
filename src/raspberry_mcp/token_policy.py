"""Dependency-free validation for the shared runtime token."""

TOKEN_ENV_VAR = "RASPBERRY_MCP_TOKEN"
MIN_TOKEN_LENGTH = 32


def validate_token(token: str | None) -> str:
    """Validate a runtime token without including its value in any error."""
    if token is None or not token.strip():
        raise ValueError(
            f"{TOKEN_ENV_VAR} is required and must be a private random secret."
        )
    if token != token.strip() or any(character.isspace() for character in token):
        raise ValueError(f"{TOKEN_ENV_VAR} must not contain whitespace.")
    if len(token) < MIN_TOKEN_LENGTH:
        raise ValueError(
            f"{TOKEN_ENV_VAR} must contain at least {MIN_TOKEN_LENGTH} characters."
        )
    if len(set(token)) < 8 or len(set(token)) == 1:
        raise ValueError(f"{TOKEN_ENV_VAR} must be a random secret.")
    return token
