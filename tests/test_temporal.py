"""Measurement before the fix: what a crash mid-briefing costs with the asyncio loop, and with the Temporal workflow.
The Temporal tests start a local dev server (downloaded by the SDK on first use)."""
import asyncio
from dataclasses import replace

import pytest

import backend.briefing as briefing_module
from backend.agent import AgentError, ProviderError
from backend.briefing import run_briefing
from backend.config import Settings
from backend.store import Store

pytest.importorskip('temporalio')
from temporalio.client import WorkflowFailureError  # noqa: E402
from temporalio.testing import WorkflowEnvironment  # noqa: E402

from backend.workflows import briefing_worker, start_briefing  # noqa: E402

DAY = '2026-10-12'
FIRST_FIVE = ['OPP-001', 'OPP-002', 'OPP-003', 'OPP-004', 'OPP-005']


@pytest.fixture
def store(tmp_path):
    return Store(Settings(db_path=str(tmp_path / 'crm.sqlite3'), mode='demo', briefing_auto=False, temporal_task_queue='test-briefing'))


def analysed(store):
    return [a['data']['opportunity_id'] for a in reversed(store.records('audit')) if a['event'] == 'analysis_completed']


def fail_on(monkeypatch, oid, error, times=1):
    """Replace the analysis of one opportunity with a failure, `times` times, then let it through."""
    real, attempts = briefing_module.analyze, []

    async def flaky(store, current, **kwargs):
        if current == oid:
            attempts.append(current)
            if len(attempts) <= times:
                raise error
        return await real(store, current, **kwargs)
    monkeypatch.setattr(briefing_module, 'analyze', flaky)
    return attempts


async def run_workflow(settings, *starts):
    async with await WorkflowEnvironment.start_local() as env:
        async with briefing_worker(env.client, settings):
            handles = [await start_briefing(env.client, settings, DAY, trigger) for trigger in starts]
            return handles, await handles[0].result()


def test_asyncio_briefing_repeats_completed_analyses_after_a_crash(store, monkeypatch):
    fail_on(monkeypatch, 'OPP-003', RuntimeError('worker crashed mid-briefing'))
    with pytest.raises(RuntimeError):
        asyncio.run(run_briefing(store))
    assert store.briefing(DAY) is None
    rerun = asyncio.run(run_briefing(store))
    assert analysed(store).count('OPP-001') == 2  # Completed before the crash, analysed (and billed) again.
    # The revisit saved before the crash changed the rerun: Northstar silently left the briefing.
    assert 'OPP-002' not in [i['opportunity_id'] for i in rerun['items']]


def test_temporal_briefing_resumes_without_repeating_analyses(store, monkeypatch):
    attempts = fail_on(monkeypatch, 'OPP-003', RuntimeError('worker crashed mid-briefing'))
    handles, result = asyncio.run(run_workflow(store.settings, 'scheduler', 'clock'))
    assert handles[0].id == handles[1].id == f'briefing-AE-001-{DAY}'  # Second trigger reused the run.
    assert attempts == ['OPP-003', 'OPP-003']  # Only the failed step was retried.
    assert sorted(analysed(store)) == FIRST_FIVE  # Each analysis exactly once.
    assert [i['opportunity_id'] for i in result['items']] == FIRST_FIVE
    assert result['orchestrator'] == 'temporal' and store.briefing(DAY)['counts']['errors'] == 0
    assert store.records('tasks') == []


def test_temporal_retries_a_transient_provider_error(store, monkeypatch):
    attempts = fail_on(monkeypatch, 'OPP-003', ProviderError('HTTP 503'), times=2)
    asyncio.run(run_workflow(store.settings, 'scheduler'))
    assert len(attempts) == 3 and store.briefing(DAY)['counts']['errors'] == 0


def test_temporal_never_retries_a_validation_failure(store, monkeypatch):
    attempts = fail_on(monkeypatch, 'OPP-003', AgentError('citazione inventata'), times=5)
    _, result = asyncio.run(run_workflow(store.settings, 'scheduler'))
    item = next(i for i in result['items'] if i['opportunity_id'] == 'OPP-003')
    assert len(attempts) == 1 and 'citazione inventata' in item['error']  # Shown to the user, not re-billed.


def test_temporal_fails_visibly_when_retries_are_exhausted(store, monkeypatch):
    attempts = fail_on(monkeypatch, 'OPP-003', ProviderError('HTTP 503'), times=5)
    with pytest.raises(WorkflowFailureError):
        asyncio.run(run_workflow(store.settings, 'scheduler'))
    assert len(attempts) == 3 and store.briefing(DAY) is None  # No partial briefing saved as if complete.
