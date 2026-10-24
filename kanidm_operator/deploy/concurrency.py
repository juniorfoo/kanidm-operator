"""Limit concurrent dependent-resource reconciles so instance handlers keep capacity."""

from __future__ import annotations

import threading
from contextlib import contextmanager

import kopf

# Bulk User/Group/OAuth2 resume after a kopf persistence migration can saturate the
# handler thread pool; cap concurrent dependent work so Kanidm instance handlers
# can still acquire executor threads promptly.
DEPENDENT_RECONCILE_LIMIT = 4

_dependent_semaphore = threading.BoundedSemaphore(DEPENDENT_RECONCILE_LIMIT)


@contextmanager
def dependent_reconcile_slot():
    acquired = _dependent_semaphore.acquire(blocking=False)
    if not acquired:
        raise kopf.TemporaryError(
            "Waiting for reconcile capacity (Kanidm instance handlers prioritized)",
            delay=2,
        )
    try:
        yield
    finally:
        _dependent_semaphore.release()
