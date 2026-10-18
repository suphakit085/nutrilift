"""App-level wiring that is easy to break silently: CORS, lifespan, DB scope.

Uses the real ``app`` object but never opens a database connection - the engine
is lazy, ``/health`` touches nothing, and the startup check is stubbed.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError, ProgrammingError

import app.main as main_module
from app.core.config import settings
from app.db.session import get_db
from app.main import app


def test_retry_after_is_exposed_cross_origin():
    """A 429's Retry-After is not CORS-safelisted; without expose_headers the
    frontend on Vercel reads ``null`` and cannot show the wait time."""
    origin = settings.cors_origin_list[0]
    response = TestClient(app).get("/health", headers={"Origin": origin})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    exposed = response.headers.get("access-control-expose-headers", "")
    assert "retry-after" in exposed.lower()


def test_startup_runs_the_production_secret_check(monkeypatch):
    """The guard only protects anything if the lifespan actually calls it."""
    calls: list[object] = []
    monkeypatch.setattr(main_module, "check_production_settings", calls.append)
    with TestClient(app):
        pass
    assert calls == [settings]


def test_database_outage_is_a_retryable_503_with_cors(monkeypatch):
    def unavailable():
        raise OperationalError("SELECT private", {}, Exception("private-host password-secret"))

    app.dependency_overrides[get_db] = unavailable
    try:
        origin = settings.cors_origin_list[0]
        response = TestClient(app).get("/auth/me", headers={"Origin": origin})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 503
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["retry-after"] == "10"
    assert "password-secret" not in response.text and "private-host" not in response.text


def test_readiness_requires_all_dependencies_while_health_is_liveness(monkeypatch):
    client = TestClient(app)
    for available in (False, True):
        monkeypatch.setattr(
            main_module,
            "readiness_checks",
            lambda available=available: {
                "database": available,
                "knowledge": available,
                "email_configured": True,
            },
        )
        assert client.get("/ready").status_code == (200 if available else 503)
        assert client.get("/health").status_code == 200


@pytest.mark.parametrize("error", [OperationalError, ProgrammingError])
def test_readiness_handles_connection_failure_and_unmigrated_schema(monkeypatch, error):
    engine = MagicMock()
    engine.dialect.name = "sqlite"
    failure = error("private sql", {}, Exception("private details"))
    if error is OperationalError:
        engine.connect.side_effect = failure
    else:
        engine.connect.return_value.__enter__.return_value.scalar.side_effect = failure
    monkeypatch.setattr(main_module, "engine", engine)
    checks = main_module.readiness_checks()
    assert checks["database"] is (error is ProgrammingError)
    assert checks["knowledge"] is False


def _walk(dependant):
    yield dependant
    for sub in dependant.dependencies:
        yield from _walk(sub)


def _api_routes(router):
    """FastAPI >= 0.141 mounts ``include_router`` results as a wrapper whose
    real routes live on ``original_router``; recurse into those."""
    for route in router.routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _api_routes(inner)
        else:
            yield route


def test_every_route_uses_function_scoped_db_sessions():
    """Regression for the SSE endpoint holding a request-scoped session (with
    an open transaction) for the whole LLM stream.

    FastAPI keys its per-request dependency cache on ``(callable, scope)``, so
    one route mixing ``Depends(get_db)`` with the function-scoped alias would
    open a *second* session per request. Enforce a single scope everywhere.
    """
    seen_routes = 0
    for route in _api_routes(app):
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        db_deps = [d for d in _walk(dependant) if d.call is get_db]
        if not db_deps:
            continue
        seen_routes += 1
        scopes = {d.scope for d in db_deps}
        assert scopes == {"function"}, f"{route.path}: get_db scopes {scopes}"
    assert seen_routes >= 10, "expected the API routes to be discovered"
