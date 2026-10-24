"""Operator runtime: non-blocking handlers and kopf settings."""

from __future__ import annotations

import asyncio
import inspect

import kanidm_operator.deploy.group as group_mod
import kanidm_operator.deploy.kanidm as kanidm_mod
import kanidm_operator.deploy.oauth2client as oauth2_mod
import kanidm_operator.deploy.user as user_mod
import kopf
from kanidm_operator.deploy.concurrency import DEPENDENT_RECONCILE_LIMIT
from kanidm_operator.kopf_settings import _MIN_HANDLER_THREADS, configure_kopf_persistence


def _handler_functions(module, names: tuple[str, ...]):
    for name in names:
        fn = getattr(module, name)
        assert not inspect.iscoroutinefunction(fn), f"{name} must be a sync handler"
        yield fn


def test_identity_and_instance_handlers_are_sync() -> None:
    for fn in _handler_functions(
        user_mod,
        ("on_create_user", "on_delete_user"),
    ):
        assert callable(fn)
    for fn in _handler_functions(
        group_mod,
        ("on_create_group", "on_update_group_members", "on_delete_group"),
    ):
        assert callable(fn)
    for fn in _handler_functions(
        oauth2_mod,
        ("on_create_oauth2client", "on_delete_oauth2client"),
    ):
        assert callable(fn)
    for fn in _handler_functions(
        kanidm_mod,
        ("on_create_kanidms", "on_update_kanidms", "on_resume_kanidms"),
    ):
        assert callable(fn)


def test_startup_configures_status_persistence_and_thread_pool() -> None:
    settings = kopf.OperatorSettings()
    configure_kopf_persistence(settings)
    assert settings.persistence.progress_storage is not None
    assert settings.persistence.diffbase_storage is not None
    assert settings.execution.max_workers == _MIN_HANDLER_THREADS
    assert settings.execution.max_workers >= DEPENDENT_RECONCILE_LIMIT + 1


def test_event_loop_stays_responsive_while_sync_handler_runs_in_executor() -> None:
    async def _exercise() -> None:
        loop = asyncio.get_running_loop()

        def blocking_work() -> int:
            import time

            time.sleep(0.2)
            return 1

        health_reached = asyncio.Event()

        async def probe() -> None:
            await asyncio.sleep(0.05)
            health_reached.set()

        probe_task = asyncio.create_task(probe())
        await loop.run_in_executor(None, blocking_work)
        await probe_task
        assert health_reached.is_set()

    asyncio.run(_exercise())
