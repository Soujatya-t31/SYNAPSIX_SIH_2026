"""
Minimal, dependency-free auth helpers.

- Passwords: PBKDF2-HMAC-SHA256 with a random per-user salt (stdlib hashlib only).
- Sessions: a signed, stateless bearer token — base64(payload) + HMAC-SHA256 signature,
  keyed by SECRET_KEY. No external JWT library required, but the same idea (a signed,
  tamper-evident token the client holds and sends back on each request).

This is intentionally simple for a hackathon-scale app; a production deployment would
swap this for a vetted library (passlib + PyJWT) and a real secret-management story.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

SECRET_KEY = os.environ.get("CIVICVOICE_SECRET_KEY", "civicvoice-dev-secret-change-me")
TOKEN_TTL_SECONDS = 30 * 24 * 3600  # 30 days
PBKDF2_ITERATIONS = 260_000


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS)
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    check, _ = hash_password(password, salt)
    return hmac.compare_digest(check, password_hash)


# ---------------------------------------------------------------------------
# Session tokens
# ---------------------------------------------------------------------------
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _unb64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(user_id: str, email: str, role: str = "citizen", **extra) -> str:
    payload_dict = {"uid": user_id, "email": email, "role": role, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    payload_dict.update({k: v for k, v in extra.items() if v is not None})
    payload = json.dumps(payload_dict).encode("utf-8")
    payload_b64 = _b64(payload)
    sig = hmac.new(SECRET_KEY.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_token(token: str) -> dict | None:
    try:
        payload_b64, sig = token.split(".", 1)
        expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload = json.loads(_unb64(payload_b64))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def new_reset_token() -> str:
    return secrets.token_urlsafe(24)
