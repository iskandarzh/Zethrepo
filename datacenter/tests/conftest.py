import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dcam import create_app  # noqa: E402


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "CSRF_ENABLED": False, "DATABASE": str(tmp_path / "test.db"), "SECRET_KEY": "test"})


@pytest.fixture
def anon(app):
    return app.test_client()


@pytest.fixture
def admin(app):
    c = app.test_client()
    r = c.post("/setup", data={"username": "admin", "nama": "Admin DC", "password": "rahasia123", "konfirmasi": "rahasia123"})
    assert r.status_code == 302
    return c


def login_as(app, admin, username, peran):
    r = admin.post("/pengguna", data={"username": username, "peran": peran, "password": "rahasia123", "konfirmasi": "rahasia123"})
    assert r.status_code == 302
    c = app.test_client()
    r = c.post("/login", data={"username": username, "password": "rahasia123"})
    assert r.status_code == 302
    return c


@pytest.fixture
def operator(app, admin):
    return login_as(app, admin, "op1", "operator")


@pytest.fixture
def viewer(app, admin):
    return login_as(app, admin, "view1", "viewer")
