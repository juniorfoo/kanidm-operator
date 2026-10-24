"""Kopf operator-wide persistence settings."""

import kopf


@kopf.on.startup()
def configure_kopf_persistence(settings: kopf.OperatorSettings, **_kwargs) -> None:
    """
    Store handler progress and diff-base in .status instead of metadata annotations.

    Annotation-backed progress can leave stale failure messages (for example a prior 422)
    visible after a later handler succeeds; the status subresource is the supported path
    for CRDs that define it.
    """
    settings.persistence.progress_storage = kopf.StatusProgressStorage(name="kopf")
    settings.persistence.diffbase_storage = kopf.StatusDiffBaseStorage(name="kopf")
