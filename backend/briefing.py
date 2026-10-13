"""Morning briefing: the server, not the user, starts a bounded batch of read-only analyses once per demo date.
Selection is deterministic (revisits the agent scheduled for itself first, then rule candidates);
the summary is composed by the server, with no extra model call. Nothing is written to the CRM."""
from .agent import AgentError, analyze
from .store import Store

MAX_ANALYSES = 5
TTL = 12 * 3600  # Analysed at dawn, approved during the morning; the snapshot check still applies.


def select(store: Store):
    due = store.revisits(due_only=True)
    waiting = {r['opportunity_id'] for r in store.revisits()} - {r['opportunity_id'] for r in due}
    picked = [(r['opportunity_id'], 'revisit') for r in due]
    candidates = sorted((o for o in store.opportunities() if o['candidate_reasons']), key=lambda o: o['close_date'])
    for o in candidates:
        oid = o['opportunity_id']
        # A pending future revisit is the agent's own decision to wait: do not re-investigate before it.
        if oid not in waiting and all(oid != p for p, _ in picked):
            picked.append((oid, 'signals'))
    return picked[:MAX_ANALYSES]


async def run_briefing(store: Store, trigger='scheduler'):
    day = store.settings.reference_date
    if existing := store.briefing(day):
        return existing  # Idempotent per date: never re-run (or re-bill) the same morning.
    names = {o['opportunity_id']: o['account_name'] for o in store.opportunities()}
    items = []
    for oid, why in select(store):
        item = {'opportunity_id': oid, 'account_name': names[oid], 'why': why}
        try:
            item['analysis'] = await analyze(store, oid, ttl=TTL)
        except (AgentError, LookupError) as error:
            item['error'] = str(error)
        items.append(item)
    decided = [i['analysis']['result'] for i in items if 'analysis' in i]
    counts = {'recommend': sum(d['decision'] == 'recommend' for d in decided),
              'clarify': sum(d['decision'] == 'clarify' for d in decided),
              'no_action': sum(d['decision'] == 'no_action' for d in decided),
              'errors': sum('error' in i for i in items)}
    return store.save_briefing(day, {'briefing_date': day, 'trigger': trigger, 'mode': store.settings.mode,
                                     'items': items, 'counts': counts})
