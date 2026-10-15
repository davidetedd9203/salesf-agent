"""Morning briefing: the server, not the user, starts a bounded batch of read-only analyses once per demo date.
Selection is deterministic (revisits the agent scheduled for itself first, then rule candidates);
the summary is composed by the server, with no extra model call. Nothing is written to the CRM.
The steps below are shared by the asyncio loop (default) and the optional Temporal workflow (backend/workflows.py)."""
import asyncio

from .agent import AgentError, analyze
from .goals import check_goal
from .store import Store

MAX_ANALYSES = 5
TTL = 12 * 3600  # Analysed at dawn, approved during the morning; the snapshot check still applies.


def select(store: Store):
    """Order: goals due for a check, revisits the agent scheduled, then rule candidates by nearest close date."""
    goals = store.goals()
    picked = [(g['opportunity_id'], 'goal') for g in store.goals(due_only=True)]
    tracked = {g['opportunity_id'] for g in goals if g['status'] in ('open', 'escalated', 'blocked')}
    due = store.revisits(due_only=True)
    waiting = {r['opportunity_id'] for r in store.revisits()} - {r['opportunity_id'] for r in due}
    picked += [(r['opportunity_id'], 'revisit') for r in due if r['opportunity_id'] not in tracked]
    candidates = sorted((o for o in store.opportunities() if o['candidate_reasons']), key=lambda o: o['close_date'])
    for o in candidates:
        oid = o['opportunity_id']
        # A pending revisit is the agent's own decision to wait; an active goal is already being followed.
        if oid not in waiting and oid not in tracked and all(oid != p for p, _ in picked):
            picked.append((oid, 'signals'))
    return picked[:MAX_ANALYSES]


async def analyze_item(store: Store, oid, why, transient=()):
    """One briefing entry. A rejected or failed analysis is a result shown to the user, not an exception;
    only `transient` errors propagate, so a durable orchestrator can retry them."""
    item = {'opportunity_id': oid, 'account_name': store.opportunity(oid)['account_name'], 'why': why}
    try:
        if why == 'goal':
            goal = next((g for g in store.goals(due_only=True) if g['opportunity_id'] == oid), None)
            if not goal:
                raise AgentError("Obiettivo già aggiornato o chiuso")  # e.g. a retried activity after the update.
            if store.settings.followthrough == 'graph':
                from . import goals_graph
                item['goal_check'] = await goals_graph.run(store, goal)
            else:
                item['goal_check'] = await check_goal(store, goal)
        else:
            item['analysis'] = await analyze(store, oid, ttl=TTL)
    except transient:
        raise
    except (AgentError, LookupError) as error:
        item['error'] = str(error)
    return item


def summarize(store: Store, day, trigger, items, orchestrator='asyncio'):
    decided = [i['analysis']['result'] for i in items if 'analysis' in i]
    counts = {'recommend': sum(d['decision'] == 'recommend' for d in decided),
              'clarify': sum(d['decision'] == 'clarify' for d in decided),
              'no_action': sum(d['decision'] == 'no_action' for d in decided),
              'goal_checks': sum('goal_check' in i for i in items), 'errors': sum('error' in i for i in items)}
    return store.save_briefing(day, {'briefing_date': day, 'trigger': trigger, 'mode': store.settings.mode,
                                     'orchestrator': orchestrator, 'items': items, 'counts': counts})


def workflow_id(settings, day, reset=''):
    # After a demo reset the same date is a new morning: the reset stamp keeps the ID unique, the date keeps it idempotent.
    return f'briefing-{settings.owner_id}-{day}' + (f'-r{reset}' if reset else '')


async def run_briefing(store: Store, trigger='scheduler'):
    day = store.settings.reference_date
    if existing := store.briefing(day):
        return existing  # Idempotent per date: never re-run (or re-bill) the same morning.
    # Known limit, measured in tests/test_temporal.py: a crash here loses the progress of completed analyses.
    # Parallel: each item is a different opportunity and waits on the provider, so five in a row took 35-50 s live.
    # ponytail: at most five concurrent calls; add a semaphore if MAX_ANALYSES grows or the provider rate-limits.
    items = await asyncio.gather(*(analyze_item(store, oid, why) for oid, why in select(store)))
    return summarize(store, day, trigger, items)
