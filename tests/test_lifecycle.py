import asyncio

import pytest


@pytest.fixture()
def lifecycle():
    from lifecycle import LifecycleManager

    return LifecycleManager(shutdown_timeout=2)


def test_lifecycle_not_shutting_down_initially(lifecycle):
    assert lifecycle.is_shutting_down is False


def test_lifecycle_shutting_down_after_trigger(lifecycle):
    lifecycle.trigger_shutdown()
    assert lifecycle.is_shutting_down is True


async def test_lifecycle_shutdown_completes_with_no_tasks(lifecycle):
    lifecycle.trigger_shutdown()
    await lifecycle.wait_for_completion()
    assert lifecycle.is_shutting_down is True


async def test_lifecycle_tracks_and_awaits_task(lifecycle):
    completed = False

    async def slow_task():
        nonlocal completed
        await asyncio.sleep(0.1)
        completed = True

    task = asyncio.create_task(slow_task())
    lifecycle.register_task(task)
    lifecycle.trigger_shutdown()
    await lifecycle.wait_for_completion()
    assert completed is True


async def test_lifecycle_unregister_removes_task(lifecycle):
    async def noop():
        pass

    task = asyncio.create_task(noop())
    lifecycle.register_task(task)
    lifecycle.unregister_task(task)
    lifecycle.trigger_shutdown()
    await lifecycle.wait_for_completion()


async def test_lifecycle_timeout_does_not_block_forever(lifecycle):
    async def stuck_task():
        await asyncio.sleep(999)

    task = asyncio.create_task(stuck_task())
    lifecycle.register_task(task)
    lifecycle.trigger_shutdown()

    # Should return within timeout (2s) + small buffer, not block forever
    await asyncio.wait_for(lifecycle.wait_for_completion(), timeout=5)
    task.cancel()
