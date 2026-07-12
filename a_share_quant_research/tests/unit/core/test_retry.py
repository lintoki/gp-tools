import pytest

from a_share_research.core.retry import BoundedRetryPolicy, RetryExhausted


def test_retry_stops_after_three_total_attempts() -> None:
    calls = 0

    def fail() -> None:
        nonlocal calls
        calls += 1
        raise TimeoutError("network")

    policy = BoundedRetryPolicy(max_attempts=3, delays=(0, 0), sleep=lambda _: None)
    with pytest.raises(RetryExhausted) as exc_info:
        policy.execute(fail, lambda error: isinstance(error, TimeoutError))

    assert calls == 3
    assert exc_info.value.attempts == 3


def test_permanent_error_is_not_retried() -> None:
    calls = 0

    def fail() -> None:
        nonlocal calls
        calls += 1
        raise ValueError("schema changed")

    policy = BoundedRetryPolicy(max_attempts=3, delays=(0, 0), sleep=lambda _: None)
    with pytest.raises(RetryExhausted) as exc_info:
        policy.execute(fail, lambda error: isinstance(error, TimeoutError))

    assert calls == 1
    assert exc_info.value.attempts == 1


def test_retry_can_succeed_before_limit() -> None:
    calls = 0

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TimeoutError("temporary")
        return "ok"

    policy = BoundedRetryPolicy(max_attempts=3, delays=(0, 0), sleep=lambda _: None)
    assert policy.execute(operation, lambda error: isinstance(error, TimeoutError)) == "ok"
    assert calls == 3
