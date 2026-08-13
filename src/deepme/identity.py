from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from fastapi import Request, Response

from src.deepme.settings import DeepMeSettings


@dataclass(frozen=True)
class VisitorIdentity:
    owner_key: str
    is_new: bool


class VisitorIdentityService:
    COOKIE_NAME = "deepme_visitor"

    def __init__(self, settings: DeepMeSettings):
        self.settings = settings
        self.secret = settings.cookie_secret.encode("utf-8")

    def resolve(self, request: Request, response: Response) -> VisitorIdentity:
        visitor_id = self._verified_visitor_id(request.cookies.get(self.COOKIE_NAME))
        is_new = visitor_id is None
        if visitor_id is None:
            visitor_id = secrets.token_urlsafe(24)
            response.set_cookie(
                self.COOKIE_NAME,
                self._signed_value(visitor_id),
                max_age=self.settings.visitor_ttl_hours * 3600,
                httponly=True,
                secure=self.settings.cookie_secure,
                samesite="lax",
                path="/",
            )
        return VisitorIdentity(owner_key=self._owner_key(visitor_id), is_new=is_new)

    def existing_owner_key(self, request: Request) -> str | None:
        visitor_id = self._verified_visitor_id(request.cookies.get(self.COOKIE_NAME))
        if visitor_id is None:
            return None
        return self._owner_key(visitor_id)

    def _signed_value(self, visitor_id: str) -> str:
        issued_at = str(int(time.time()))
        payload = f"{visitor_id}.{issued_at}"
        signature = hmac.new(self.secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{payload}.{signature}"

    def _verified_visitor_id(self, value: str | None) -> str | None:
        if not value or value.count(".") != 2:
            return None
        visitor_id, issued_at_raw, signature = value.split(".", 2)
        if not visitor_id or not issued_at_raw or not signature:
            return None
        try:
            issued_at = int(issued_at_raw)
        except ValueError:
            return None
        now = int(time.time())
        ttl_seconds = self.settings.visitor_ttl_hours * 3600
        if issued_at > now + 300 or now - issued_at > ttl_seconds:
            return None
        payload = f"{visitor_id}.{issued_at_raw}"
        expected = hmac.new(
            self.secret,
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        return visitor_id

    def _owner_key(self, visitor_id: str) -> str:
        return hmac.new(self.secret, visitor_id.encode("utf-8"), hashlib.sha256).hexdigest()
