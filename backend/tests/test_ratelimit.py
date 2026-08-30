"""Tests for the sliding-window rate limiter.

The chat limits are a spend ceiling as much as an abuse control, so the
behaviour that matters is: a rejected request must not consume allowance, the
window must actually slide, and two limits on the same user must not interfere.
Time is injected, so none of this sleeps.
"""

import pytest

from app.core.ratelimit import Limit, RateLimiter, RateLimitExceeded, enforce


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


@pytest.fixture
def limiter(clock: FakeClock) -> RateLimiter:
    return RateLimiter(clock=clock)


PER_MINUTE = Limit(3, 60)


# --- basic window behaviour ------------------------------------------------


def test_allows_up_to_the_limit(limiter):
    for _ in range(3):
        assert limiter.retry_after("u1", PER_MINUTE) is None
        limiter.hit("u1", PER_MINUTE)
    assert limiter.retry_after("u1", PER_MINUTE) is not None


def test_window_slides(limiter, clock):
    for _ in range(3):
        limiter.hit("u1", PER_MINUTE)
    assert limiter.retry_after("u1", PER_MINUTE) is not None

    clock.advance(61)
    assert limiter.retry_after("u1", PER_MINUTE) is None


def test_partial_expiry_frees_exactly_one_slot(limiter, clock):
    limiter.hit("u1", PER_MINUTE)
    clock.advance(30)
    limiter.hit("u1", PER_MINUTE)
    limiter.hit("u1", PER_MINUTE)
    assert limiter.retry_after("u1", PER_MINUTE) is not None

    clock.advance(31)  # only the first event has aged out
    assert limiter.retry_after("u1", PER_MINUTE) is None
    limiter.hit("u1", PER_MINUTE)
    assert limiter.retry_after("u1", PER_MINUTE) is not None


def test_keys_are_independent(limiter):
    for _ in range(3):
        limiter.hit("u1", PER_MINUTE)
    assert limiter.retry_after("u1", PER_MINUTE) is not None
    assert limiter.retry_after("u2", PER_MINUTE) is None


def test_retry_after_is_a_positive_whole_number(limiter, clock):
    for _ in range(3):
        limiter.hit("u1", PER_MINUTE)
    clock.advance(10)
    wait = limiter.retry_after("u1", PER_MINUTE)
    assert isinstance(wait, int)
    assert 1 <= wait <= 61


def test_count_reflects_only_the_live_window(limiter, clock):
    limiter.hit("u1", PER_MINUTE)
    limiter.hit("u1", PER_MINUTE)
    assert limiter.count("u1", PER_MINUTE) == 2
    clock.advance(61)
    assert limiter.count("u1", PER_MINUTE) == 0


def test_reset_clears(limiter):
    limiter.hit("u1", PER_MINUTE)
    limiter.reset("u1")
    assert limiter.count("u1", PER_MINUTE) == 0


# --- enforce() -------------------------------------------------------------


def test_enforce_raises_with_message_and_retry_after(limiter):
    for _ in range(3):
        enforce(limiter, "u1", PER_MINUTE, "ช้าลงหน่อย")
    with pytest.raises(RateLimitExceeded) as excinfo:
        enforce(limiter, "u1", PER_MINUTE, "ช้าลงหน่อย")
    assert excinfo.value.message == "ช้าลงหน่อย"
    assert excinfo.value.retry_after >= 1


def test_rejected_request_does_not_consume_allowance(limiter, clock):
    """A blocked call must not push the window forward and extend the block."""
    for _ in range(3):
        enforce(limiter, "u1", PER_MINUTE, "ช้าลงหน่อย")

    for _ in range(5):
        with pytest.raises(RateLimitExceeded):
            enforce(limiter, "u1", PER_MINUTE, "ช้าลงหน่อย")

    assert limiter.count("u1", PER_MINUTE) == 3, "rejected calls were counted"
    clock.advance(61)
    assert limiter.retry_after("u1", PER_MINUTE) is None


# --- two windows on one user ----------------------------------------------


def test_hourly_and_daily_limits_use_separate_keys(limiter, clock):
    """Regression: sharing one key between two windows double-counted turns."""
    hourly = Limit(20, 3600)
    daily = Limit(60, 86400)

    for _ in range(20):
        limiter.hit("chat:hour:u1", hourly)
        limiter.hit("chat:day:u1", daily)

    assert limiter.count("chat:hour:u1", hourly) == 20
    assert limiter.count("chat:day:u1", daily) == 20
    assert limiter.retry_after("chat:hour:u1", hourly) is not None
    assert limiter.retry_after("chat:day:u1", daily) is None, "daily should still have room"

    clock.advance(3601)  # a new hour, same day
    assert limiter.retry_after("chat:hour:u1", hourly) is None
    assert limiter.count("chat:day:u1", daily) == 20


def test_daily_limit_still_binds_after_hourly_resets(limiter, clock):
    hourly = Limit(20, 3600)
    daily = Limit(60, 86400)
    for _ in range(3):
        for _ in range(20):
            limiter.hit("chat:hour:u1", hourly)
            limiter.hit("chat:day:u1", daily)
        clock.advance(3601)

    assert limiter.retry_after("chat:hour:u1", hourly) is None
    assert limiter.retry_after("chat:day:u1", daily) is not None


def test_global_cap_is_shared_across_users(limiter):
    cap = Limit(5, 86400)
    for user in ("u1", "u2", "u3", "u4", "u5"):
        assert limiter.retry_after("chat:all-users", cap) is None, user
        limiter.hit("chat:all-users", cap)
    assert limiter.retry_after("chat:all-users", cap) is not None


# --- message formatting ----------------------------------------------------


@pytest.mark.parametrize(
    "limit, expected",
    [
        (Limit(20, 3600), "20 ครั้งต่อ 1 ชั่วโมง"),
        (Limit(60, 86400), "60 ครั้งต่อ 1 วัน"),
        (Limit(10, 900), "10 ครั้งต่อ 15 นาที"),
        (Limit(2, 30), "2 ครั้งต่อ 30 วินาที"),
    ],
)
def test_describe_th(limit, expected):
    assert limit.describe_th() == expected


# --- edge cases ------------------------------------------------------------


def test_zero_limit_blocks_everything_without_crashing(limiter):
    """A limit of 0 is a kill switch. It used to raise IndexError: with no
    recorded events there was no timestamp to derive an expiry from."""
    closed = Limit(0, 60)
    wait = limiter.retry_after("u1", closed)
    assert wait == 60


def test_zero_limit_stays_closed_after_attempts(limiter):
    closed = Limit(0, 60)
    for _ in range(3):
        with pytest.raises(RateLimitExceeded):
            enforce(limiter, "u1", closed, "ปิดใช้งาน")
    assert limiter.retry_after("u1", closed) is not None


def test_negative_limit_is_treated_as_closed(limiter):
    assert limiter.retry_after("u1", Limit(-1, 60)) is not None
