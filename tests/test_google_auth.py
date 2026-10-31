import asyncio

import httpx
from bson import ObjectId
from fastapi import FastAPI

from app.api.v1.endpoints.auth import router
from app.core.exceptions import UnauthorizedException
from app.crud import crud_user
from app.services import google_auth_service
from tests.fake_mongo import FakeCollection

CLAIMS = {"email": "me@gmail.com", "email_verified": True, "sub": "google-123", "name": "Google Name"}


class FakeDb:
    def __init__(self, users=None):
        self.users = FakeCollection(users)


def setup(monkeypatch, users=None, claims=CLAIMS):
    db = FakeDb(users)
    monkeypatch.setattr(crud_user, "get_database", lambda: db)

    async def verify(token):
        if token != "good":
            raise UnauthorizedException(detail="Invalid Google ID token")
        return claims
    monkeypatch.setattr(google_auth_service, "verify_google_id_token", verify)
    app = FastAPI()
    app.include_router(router, prefix="/auth")
    return app, db


def post(app, path, body):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return await c.post(path, json=body)
    return asyncio.run(go())


def _existing(**extra):
    return {"_id": ObjectId(), "email": "me@gmail.com", "name": "Me", "profile_completed": True, **extra}


def test_login_without_create_is_404_and_creates_nothing(monkeypatch):
    app, db = setup(monkeypatch)
    r = post(app, "/auth/google", {"id_token": "good", "create_if_missing": False})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "account_not_found"
    assert db.users.docs == []


def test_login_without_create_logs_in_an_existing_account(monkeypatch):
    app, db = setup(monkeypatch, users=[_existing()])
    r = post(app, "/auth/google", {"id_token": "good", "create_if_missing": False})
    assert r.status_code == 200 and r.json()["access_token"]
    assert r.json()["is_new_user"] is False and r.json()["profile_completed"] is True
    assert len(db.users.docs) == 1


def test_legacy_login_still_creates_an_incomplete_account(monkeypatch):
    app, db = setup(monkeypatch)
    r = post(app, "/auth/google", {"id_token": "good"})                    # old app: no create_if_missing
    assert r.status_code == 200
    assert r.json()["is_new_user"] is True and r.json()["profile_completed"] is False
    assert db.users.docs[0]["name"] == "Google Name"


def test_signup_creates_a_completed_account_with_the_confirmed_profile(monkeypatch):
    app, db = setup(monkeypatch)
    r = post(app, "/auth/google/signup", {"id_token": "good", "name": "  Real Name ", "photo_url": "https://p/x.jpg"})
    assert r.status_code == 200 and r.json()["access_token"]
    assert r.json()["is_new_user"] is True and r.json()["profile_completed"] is True
    [user] = db.users.docs
    assert (user["email"], user["name"], user["photo_url"], user["google_id"]) == \
        ("me@gmail.com", "Real Name", "https://p/x.jpg", "google-123")


def test_signup_repeated_logs_in_without_a_duplicate_or_overwrite(monkeypatch):
    app, db = setup(monkeypatch)
    post(app, "/auth/google/signup", {"id_token": "good", "name": "First"})
    r = post(app, "/auth/google/signup", {"id_token": "good", "name": "Second"})
    assert r.status_code == 200 and r.json()["is_new_user"] is False
    assert [u["name"] for u in db.users.docs] == ["First"]


def test_signup_rejects_a_blank_name_and_a_bad_token(monkeypatch):
    app, db = setup(monkeypatch)
    assert post(app, "/auth/google/signup", {"id_token": "good", "name": "   "}).status_code == 422
    assert post(app, "/auth/google/signup", {"id_token": "bad", "name": "Me"}).status_code == 401
    assert db.users.docs == []
