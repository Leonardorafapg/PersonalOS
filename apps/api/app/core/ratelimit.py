"""Tiny in-memory brute-force guard for password endpoints (single-instance deployment)."""

import time
from collections import defaultdict, deque

WINDOW = 300  # seconds
MAX_FAILS = 10
_fails: dict[str, deque] = defaultdict(deque)


def blocked(key: str) -> bool:
    q = _fails[key]
    now = time.time()
    while q and now - q[0] > WINDOW:
        q.popleft()
    return len(q) >= MAX_FAILS


def record_failure(key: str) -> None:
    _fails[key].append(time.time())


def reset(key: str) -> None:
    _fails.pop(key, None)
