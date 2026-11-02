import hashlib
import hmac
import secrets

from starlette.requests import HTTPConnection


def new_token() -> str:
    return secrets.token_urlsafe(32)


def keyed_hash(secret: str, value: str) -> str:
    """HMAC-SHA256 hex. Used for session tokens and IPs, so neither is stored in the clear."""
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def hash_token(secret: str, token: str) -> str:
    return keyed_hash(secret, f"token:{token}")


def hash_ip(secret: str, ip: str) -> str:
    return keyed_hash(secret, f"ip:{ip}")


def client_ip(conn: HTTPConnection) -> str:
    """Caller IP. Render and Vercel put the real client first in X-Forwarded-For."""
    forwarded = conn.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return conn.client.host if conn.client else "unknown"
