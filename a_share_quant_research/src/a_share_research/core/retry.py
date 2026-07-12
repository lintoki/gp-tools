from __future__ import annotations

import time
from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class RetryExhausted(RuntimeError):
    def __init__(self, attempts: int, cause: Exception) -> None:
        self.attempts = attempts
        self.cause = cause
        super().__init__(f"operation failed after {attempts} attempt(s): {cause}")


class BoundedRetryPolicy(Generic[T]):
    def __init__(
        self,
        max_attempts: int = 3,
        delays: tuple[float, ...] = (1.0, 2.0),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if len(delays) < max_attempts - 1:
            raise ValueError("delays must cover every retry")
        if any(delay < 0 for delay in delays):
            raise ValueError("retry delays cannot be negative")
        self.max_attempts = max_attempts
        self.delays = delays
        self.sleep = sleep

    def execute(
        self,
        operation: Callable[[], T],
        is_transient: Callable[[Exception], bool],
    ) -> T:
        for attempt in range(1, self.max_attempts + 1):
            try:
                return operation()
            except Exception as exc:
                if not is_transient(exc) or attempt == self.max_attempts:
                    raise RetryExhausted(attempt, exc) from exc
                self.sleep(self.delays[attempt - 1])
        raise AssertionError("bounded retry loop ended unexpectedly")
