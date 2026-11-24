"""Authentication configuration must fail closed without leaking secrets."""

import unittest

from starlette.testclient import TestClient

from raspberry_mcp.auth import MIN_TOKEN_LENGTH, validate_token
from raspberry_mcp.server import create_app


VALID_TOKEN = "correct-horse-battery-staple-raspberry-2026"


class TokenValidationTests(unittest.TestCase):
    def test_accepts_a_long_random_token(self):
        self.assertEqual(validate_token(VALID_TOKEN), VALID_TOKEN)

    def test_application_constructor_rejects_weak_token(self):
        from raspberry_mcp.server import create_app

        with self.assertRaisesRegex(ValueError, "at least 32 characters"):
            create_app("weak", "127.0.0.1")

    def test_rejects_missing_blank_and_short_tokens_without_value(self):
        for token in (None, "", "   ", "short"):
            with self.subTest(token=token), self.assertRaises(ValueError) as error:
                validate_token(token)
            if token:
                self.assertNotIn(token, str(error.exception))
            self.assertIn("RASPBERRY_MCP_TOKEN", str(error.exception))

    def test_rejects_whitespace_and_repetitive_tokens(self):
        for token in ("x" * MIN_TOKEN_LENGTH, f"{VALID_TOKEN} "):
            with self.subTest(token=token), self.assertRaises(ValueError) as error:
                validate_token(token)
            self.assertNotIn(token, str(error.exception))


class AuthenticationResponseTests(unittest.TestCase):
    def test_invalid_authorization_does_not_echo_a_secret(self):
        app = create_app(VALID_TOKEN, "127.0.0.1")
        secret = "wrong-private-token-that-must-not-appear"
        client = TestClient(app)
        response = client.get("/mcp", headers={"Authorization": f"Bearer {secret}"})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn(secret, response.text)
        self.assertEqual(response.json(), {"error": "unauthorized"})


if __name__ == "__main__":
    unittest.main()
