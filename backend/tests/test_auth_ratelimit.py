"""Login throttling is per email *and* per IP; register is per IP only.

The old single per-IP limit (10 / 15 min shared by register and login) locked
out a whole classroom behind one NAT after a handful of typos. Password
guessing is now blunted where it belongs - on the email being guessed.
"""

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import deps
from app.core.config import settings
from app.core.ratelimit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture(autouse=True)
def fresh_limiter(monkeypatch, clock):
    limiter = RateLimiter(clock=clock)
    monkeypatch.setattr(deps, "limiter", limiter)
    monkeypatch.setattr(settings, "rate_limit_auth_per_15min", 5)
    monkeypatch.setattr(settings, "rate_limit_login_per_email_per_15min", 3)
    return limiter


def request_from(ip: str) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/login",
        "headers": [(b"x-forwarded-for", ip.encode())],
        "client": ("10.0.0.1", 1234),
        "query_string": b"",
    }
    return Request(scope)


def login(ip: str, email: str) -> None:
    deps.rate_limit_login(request_from(ip), email)


def assert_429(fn):
    with pytest.raises(HTTPException) as excinfo:
        fn()
    assert excinfo.value.status_code == 429
    assert "Retry-After" in excinfo.value.headers
    return excinfo.value


# --- per-email -------------------------------------------------------------


def test_one_email_is_blocked_while_others_on_the_same_ip_continue():
    for _ in range(3):
        login("203.0.113.5", "victim@example.com")
    exc = assert_429(lambda: login("203.0.113.5", "victim@example.com"))
    assert "อีเมลนี้" in exc.detail

    # a classmate on the same NAT is unaffected
    login("203.0.113.5", "classmate@example.com")


def test_email_key_is_case_insensitive():
    for _ in range(3):
        login("203.0.113.5", "Victim@Example.com")
    assert_429(lambda: login("203.0.113.5", "victim@example.com"))
    assert deps.login_email_key("  Foo@Bar.COM ") == "auth:email:foo@bar.com"


def test_email_limit_follows_the_email_across_ips():
    """That is the point: a guesser rotating addresses still hits the cap."""
    for ip in ("203.0.113.1", "203.0.113.2", "203.0.113.3"):
        login(ip, "victim@example.com")
    assert_429(lambda: login("203.0.113.4", "victim@example.com"))


def test_email_window_slides(clock):
    for _ in range(3):
        login("203.0.113.5", "victim@example.com")
    assert_429(lambda: login("203.0.113.5", "victim@example.com"))
    clock.advance(15 * 60 + 1)
    login("203.0.113.5", "victim@example.com")


# --- per-IP ------------------------------------------------------------------


def test_ip_limit_still_caps_a_flood_of_distinct_emails():
    for i in range(5):
        login("203.0.113.5", f"user{i}@example.com")
    exc = assert_429(lambda: login("203.0.113.5", "user99@example.com"))
    assert "อีเมลนี้" not in exc.detail


def test_register_shares_the_ip_bucket_with_login(fresh_limiter):
    for i in range(4):
        login("203.0.113.5", f"user{i}@example.com")
    deps.rate_limit_auth(request_from("203.0.113.5"))  # fifth and last
    assert_429(lambda: deps.rate_limit_auth(request_from("203.0.113.5")))
    assert fresh_limiter.count("auth:203.0.113.5", deps.auth_ip_limit()) == 5


# --- counting semantics -------------------------------------------------------


def test_rejected_attempt_counts_against_neither_bucket(fresh_limiter):
    """Same rule as chat: check every limit, then count once. A blocked login
    must not also burn the IP's allowance or push the email window forward."""
    for _ in range(3):
        login("203.0.113.5", "victim@example.com")
    for _ in range(10):
        assert_429(lambda: login("203.0.113.5", "victim@example.com"))
    assert fresh_limiter.count("auth:email:victim@example.com", deps.login_email_limit()) == 3
    assert fresh_limiter.count("auth:203.0.113.5", deps.auth_ip_limit()) == 3


def test_ip_block_does_not_count_against_the_email(fresh_limiter):
    for i in range(5):
        login("203.0.113.5", f"user{i}@example.com")
    assert_429(lambda: login("203.0.113.5", "fresh@example.com"))
    assert fresh_limiter.count("auth:email:fresh@example.com", deps.login_email_limit()) == 0
