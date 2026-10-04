import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.main as main


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / 'smoke.db'
    monkeypatch.setattr(main, 'DATABASE_URL', 'postgresql://isolated-test.invalid/test')
    monkeypatch.setattr(main, 'SECRET', 'isolated-test-secret-value-at-least-32-chars')

    def connect_test_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(main, 'db', connect_test_db)
    with TestClient(main.app) as test_client:
        yield test_client


def test_login_and_logout_invalidate_token(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@pharmaai.local", "password": "admin123"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["token"]

    logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 200, logout.text

    protected = client.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert protected.status_code == 401, protected.text


def test_no_native_prompt_or_confirm_in_frontend():
    js = Path(__file__).resolve().parent.parent / "frontend" / "app.js"
    text = js.read_text(encoding="utf-8")
    assert "prompt(" not in text, "Native prompt() was used in the frontend"
    assert "confirm(" not in text, "Native confirm() was used in the frontend"
