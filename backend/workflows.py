"""Optional durable orchestration of the morning briefing with Temporal (ORCHESTRATOR=temporal).

Measured reason (tests/test_temporal.py, DECISION_LOG T1): with the asyncio loop a crash mid-briefing re-runs and re-bills
completed analyses, and side effects saved before the crash (a revisit) change what the rerun selects.
Here every analysis is an activity: completed ones are recorded in workflow history and never re-executed, transient
provider errors are retried, validation failures are results and never retried, and one workflow ID per owner and
date prevents a second run even with several workers. Production trigger: a Temporal Schedule at 07:00 per user.
"""
import asyncio
from dataclasses import replace
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.worker import Worker

with workflow.unsafe.imports_passed_through():
    from .agent import ProviderError
    from .briefing import analyze_item, select, summarize
    from .config import Settings
    from .store import Store

RETRY = RetryPolicy(initial_interval=timedelta(seconds=2), maximum_attempts=3)


class BriefingActivities:
    """Side effects (database, model calls) live here; the workflow itself stays deterministic."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def store(self, day):
        # The demo date is a workflow input, not process state: a separate worker sees the same clock.
        return Store(replace(self.settings, reference_date=day))

    @activity.defn
    async def select_opportunities(self, day: str) -> list[list[str]]:
        return [list(pick) for pick in select(self.store(day))]

    @activity.defn
    async def analyze_opportunity(self, day: str, oid: str, why: str) -> dict:
        # Heartbeats let Temporal notice a dead worker in seconds, not after the 120-second timeout.
        async def beat():
            while True:
                activity.heartbeat()
                await asyncio.sleep(2)
        beating = asyncio.create_task(beat())
        try:
            return await analyze_item(self.store(day), oid, why, transient=(ProviderError,))
        finally:
            beating.cancel()

    @activity.defn
    async def save_briefing(self, day: str, trigger: str, items: list[dict]) -> dict:
        return summarize(self.store(day), day, trigger, items, orchestrator='temporal')


@workflow.defn
class MorningBriefing:
    @workflow.run
    async def run(self, day: str, trigger: str) -> dict:
        picked = await workflow.execute_activity_method(
            BriefingActivities.select_opportunities, day, start_to_close_timeout=timedelta(seconds=30))
        items = []
        for oid, why in picked:  # Sequential on purpose: one model call at a time, as in the asyncio path.
            items.append(await workflow.execute_activity_method(
                BriefingActivities.analyze_opportunity, args=[day, oid, why],
                start_to_close_timeout=timedelta(seconds=120), heartbeat_timeout=timedelta(seconds=10), retry_policy=RETRY))
        return await workflow.execute_activity_method(
            BriefingActivities.save_briefing, args=[day, trigger, items], start_to_close_timeout=timedelta(seconds=30))


def workflow_id(settings: Settings, day):
    return f'briefing-{settings.owner_id}-{day}'


async def start_briefing(client: Client, settings: Settings, day, trigger):
    """Idempotent start: a running or completed briefing for the same owner and date is reused, never duplicated."""
    try:
        return await client.start_workflow(MorningBriefing.run, args=[day, trigger], id=workflow_id(settings, day),
                                           task_queue=settings.temporal_task_queue,
                                           id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY)
    except WorkflowAlreadyStartedError:
        return client.get_workflow_handle(workflow_id(settings, day))


def briefing_worker(client: Client, settings: Settings):
    activities = BriefingActivities(settings)
    return Worker(client, task_queue=settings.temporal_task_queue, workflows=[MorningBriefing],
                  activities=[activities.select_opportunities, activities.analyze_opportunity, activities.save_briefing],
                  max_concurrent_activities=1)


async def main():
    """Standalone worker, e.g. on another machine: python -m backend.workflows"""
    settings = Settings()
    await briefing_worker(await Client.connect(settings.temporal_address), settings).run()


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
