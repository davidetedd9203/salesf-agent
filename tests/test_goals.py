"""Follow-through: approved tasks open goals; the model reads outcomes, a fixed server policy decides the next step."""
import asyncio
import json
from dataclasses import replace
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.agent import AgentError, analyze
from backend.briefing import run_briefing
from backend.config import Settings
from backend.goals import check_goal, policy, validate_check
from backend.main import create_app
from backend.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(Settings(db_path=str(tmp_path / 'crm.sqlite3'), mode='demo', briefing_auto=False))


def approve(store, oid):
    proposal = asyncio.run(analyze(store, oid))
    return store.approve(proposal['proposal_id'])


def goal_of(store, oid):
    return next(g for g in store.goals() if g['opportunity_id'] == oid)


def test_approval_opens_one_goal_with_a_server_written_objective(store):
    task = approve(store, 'OPP-001')
    goal = goal_of(store, 'OPP-001')
    assert (goal['task_id'], goal['objective'], goal['next_check'], goal['status']) == \
        (task['id'], 'La demo tecnica richiesta si è svolta', '2026-10-16', 'open')
    store.approve(task['proposal_id'])  # Idempotent repeat: no second task, no second goal.
    assert len(store.goals()) == 1


def test_policy_waits_then_nudges_once_then_escalates():
    goal = {'due_date': '2026-10-13', 'next_check': '2026-10-13', 'nudges': 0}
    pending = {'outcome': 'pending'}
    assert policy(goal, pending, date(2026, 10, 12))[3] == 'wait'
    assert policy(goal, pending, date(2026, 10, 13))[:2] == ('open', '2026-10-14')
    assert policy(goal, pending, date(2026, 10, 14)) == ('open', '2026-10-16', 1, 'nudge')
    assert policy({**goal, 'nudges': 1}, pending, date(2026, 10, 16))[::3] == ('escalated', 'escalate')
    assert policy(goal, {'outcome': 'achieved'}, date(2026, 10, 20))[::3] == ('achieved', 'close')
    assert policy(goal, {'outcome': 'blocked'}, date(2026, 10, 20))[::3] == ('blocked', 'ask_rep')


def test_the_original_request_cannot_prove_its_own_outcome(store):
    approve(store, 'OPP-001')
    goal = goal_of(store, 'OPP-001')
    store.set_clock(date(2026, 10, 17))
    context = store.context('OPP-001')
    old = {'outcome': 'achieved', 'reason': 'La demo risulta richiesta e confermata.', 'question': None,
           'evidence': [{'note_id': 'NOTE-001-2', 'quote': 'Rep confirmed they would schedule the technical demo.'}]}
    with pytest.raises(AgentError, match='successiva'):
        validate_check(old, context, goal)
    new = {**old, 'evidence': [{'note_id': 'NOTE-001-4', 'quote': 'Technical demo with CTO held on 2026-10-16.'}]}
    assert validate_check(new, context, goal)['outcome'] == 'achieved'
    with pytest.raises(Exception):  # blocked without a question for the rep
        validate_check({**new, 'outcome': 'blocked'}, context, goal)


def test_escalation_stops_automatic_checks_and_reaches_the_rep(store):
    approve(store, 'OPP-003')
    for day in (date(2026, 10, 14), date(2026, 10, 16)):
        store.set_clock(day)
        with store.connect() as db:  # No outcome notes in this run: remove the v4 note to force the pending path.
            db.execute("DELETE FROM notes WHERE id='NOTE-003-4'")
        asyncio.run(check_goal(store, goal_of(store, 'OPP-003')))
    goal = goal_of(store, 'OPP-003')
    assert (goal['status'], goal['nudges'], goal['last_check']['action']) == ('escalated', 1, 'escalate')
    store.set_clock(date(2026, 10, 20))
    assert store.goals(due_only=True) == []
    assert store.records('tasks')[0]['completed_at'] is None  # The agent never closes a CRM task.


def test_rep_completion_closes_task_and_goal_and_allows_a_new_task(store):
    task = approve(store, 'OPP-001')
    store.complete_task(task['id'])
    assert goal_of(store, 'OPP-001')['status'] == 'achieved'
    assert goal_of(store, 'OPP-001')['last_check']['by'] == 'rep'
    with pytest.raises(ValueError):
        store.complete_task(task['id'])
    assert not any(o['has_pending_task'] for o in store.opportunities() if o['opportunity_id'] == 'OPP-001')


def test_briefing_checks_due_goals_first_and_skips_followed_deals(store):
    approve(store, 'OPP-001')
    approve(store, 'OPP-003')
    store.set_clock(date(2026, 10, 14))
    items = asyncio.run(run_briefing(store))['items']
    assert (items[0]['opportunity_id'], items[0]['why']) == ('OPP-003', 'goal')
    assert 'OPP-001' not in [i['opportunity_id'] for i in items]  # Followed by its goal, not due yet.


def test_openrouter_goal_check_is_phased_and_validated(store):
    approve(store, 'OPP-001')
    store.set_clock(date(2026, 10, 17))
    live = Store(replace(store.settings, mode='openrouter', api_key='test-placeholder', model='test/model', reference_date='2026-10-17'))
    final = {'outcome': 'achieved', 'reason': 'La demo si è svolta il 16 ottobre.', 'question': None,
             'evidence': [{'note_id': 'NOTE-001-4', 'quote': 'Technical demo with CTO held on 2026-10-16.'}]}
    steps = [(n, {'opportunity_id': 'OPP-001'}) for n in ('get_opportunity', 'get_notes', 'get_activities')] + [('submit_goal_check', final)]
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        name, args = steps[len(seen) - 1]
        return httpx.Response(200, json={'choices': [{'message': {'tool_calls': [
            {'id': f'c{len(seen)}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}}]})

    result = asyncio.run(check_goal(live, goal_of(live, 'OPP-001'), httpx.MockTransport(handler)))
    assert result['goal']['status'] == 'achieved'
    assert [t['function']['name'] for t in seen[0]['tools']] == ['get_opportunity', 'get_notes', 'get_activities']
    assert [t['function']['name'] for t in seen[-1]['tools']] == ['submit_goal_check']


def test_http_goal_and_task_endpoints_require_session_and_origin(store):
    task = approve(store, 'OPP-001')
    gid = goal_of(store, 'OPP-001')['id']
    with TestClient(create_app(store.settings)) as client:
        headers = {'Origin': store.settings.origin}
        assert client.get('/api/goals').status_code == 401
        client.post('/api/login', json={'password': 'local-demo'}, headers=headers)
        assert client.post(f'/api/tasks/{task["id"]}/complete', json={}).status_code == 403
        assert client.post(f'/api/goals/{gid}/cancel', json={}, headers=headers).status_code == 200
        assert client.post(f'/api/goals/{gid}/cancel', json={}, headers=headers).status_code == 409
        assert client.post(f'/api/tasks/{task["id"]}/complete', json={}, headers=headers).status_code == 200
        assert client.get('/api/goals').json()[0]['status'] == 'cancelled'
        assert client.get('/api/tasks').json()[0]['completed_at'] == '2026-10-12'
