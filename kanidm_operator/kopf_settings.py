"""Kopf operator-wide persistence and runtime settings."""

import kopf

from kanidm_operator.deploy.concurrency import DEPENDENT_RECONCILE_LIMIT

# Headroom above dependent-handler concurrency so Kanidm instance work is not starved.
_MIN_HANDLER_THREADS = DEPENDENT_RECONCILE_LIMIT + 8


@kopf.on.startup()
def configure_kopf_persistence(settings: kopf.OperatorSettings, **_kwargs) -> None:
    """
    Store handler progress and diff-base in .status instead of metadata annotations.

    Annotation-backed progress can leave stale failure messages (for example a prior 422)
    visible after a later handler succeeds; the status subresource is the supported path
    for CRDs that define it.

    Blocking handler work runs in Kopf's thread-pool executor (sync handlers), keeping
    the asyncio loop free for the built-in ``--liveness`` HTTP server on :8080/healthz.
    """
    settings.persistence.progress_storage = kopf.StatusProgressStorage(name="kopf")
    settings.persistence.diffbase_storage = kopf.StatusDiffBaseStorage(name="kopf")

    current = settings.execution.max_workers
    if current is None or current < _MIN_HANDLER_THREADS:
        settings.execution.max_workers = _MIN_HANDLER_THREADS
