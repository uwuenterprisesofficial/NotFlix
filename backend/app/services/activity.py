"""When someone last did something that needs streams now (opened a show, played or resolved
an episode, lingered on a preview): background work (prefetch.py) waits until that's a while
ago, so it never competes with what's being watched."""

import time

# Quiet for this long counts as idle.
IDLE_AFTER_S = 20.0

_last = 0.0


def touch() -> None:
    global _last
    _last = time.monotonic()


def quiet_for() -> float:
    return time.monotonic() - _last


def idle() -> bool:
    return quiet_for() >= IDLE_AFTER_S


def reset() -> None:
    """Forget the last activity (tests)."""
    global _last
    _last = 0.0
