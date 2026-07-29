import asyncio

from app import main


class _FakeConnection:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.executed = False

    async def __aenter__(self):
        if self.fail:
            raise ConnectionError("database unavailable")
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, statement):
        self.executed = True


class _FakeEngine:
    def __init__(self, *, fail: bool = False):
        self.connection = _FakeConnection(fail=fail)

    def connect(self):
        return self.connection


def test_health_is_uncached_and_does_not_touch_database():
    response = asyncio.run(main.health())

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert b'"status":"ok"' in response.body


def test_readiness_checks_database(monkeypatch):
    fake_engine = _FakeEngine()
    monkeypatch.setattr(main, "engine", fake_engine)

    response = asyncio.run(main.readiness())

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert fake_engine.connection.executed is True
    assert b'"status":"ready"' in response.body


def test_readiness_returns_503_when_database_is_unavailable(monkeypatch):
    monkeypatch.setattr(main, "engine", _FakeEngine(fail=True))

    response = asyncio.run(main.readiness())

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert b'"status":"unavailable"' in response.body
