"""The rep's decision on a blocked or escalated goal. The LangGraph version lives on branch experiment/langgraph-followthrough."""
import asyncio
from dataclasses import replace
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.agent import analyze
from backend.briefing import run_briefing
from backend.config import Settings
from backend.main import create_app
from backend.schemas import GoalDecision
from backend.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(Settings(db_path=str(tmp_path / 'crm.sqlite3'), mode='demo', briefing_auto=False, orchestrator='asyncio'))


def decide(store, gid, **decision):
    store.decide_goal(gid, GoalDecision(**decision))


def blocked_bluepeak(store):
    """BluePeak's approved task, then the 15/10 note moving the review to January: the briefing of 17/10 blocks the goal."""
    store.approve(asyncio.run(analyze(store, 'OPP-003'))['proposal_id'])
    store.set_clock(date(2026, 10, 17))
    item = next(i for i in asyncio.run(run_briefing(store))['items'] if i['opportunity_id'] == 'OPP-003')
    goal = item['goal_check']['goal']
    assert (goal['status'], goal['last_check']['action']) == ('blocked', 'ask_rep')
    return goal['id']


def goal(store, gid):
    return next(g for g in store.goals() if g['id'] == gid)


def test_reschedule_restarts_the_follow_through(store):
    gid = blocked_bluepeak(store)
    decide(store, gid, action='reschedule', due_date='2027-01-15')
    g = goal(store, gid)
    assert (g['status'], g['due_date'], g['next_check'], g['nudges']) == ('open', '2027-01-15', '2027-01-15', 0)
    assert g['last_check'] == {'action': 'reschedule', 'by': 'rep', 'on': '2026-10-17', 'due_date': '2027-01-15'}
    with pytest.raises(ValueError, match='non in attesa'):
        decide(store, gid, action='drop')
    assert store.records('tasks')[0]['completed_at'] is None  # The CRM task is the rep's to close.


def test_drop_ends_the_goal(store):
    gid = blocked_bluepeak(store)
    decide(store, gid, action='drop')
    assert goal(store, gid)['status'] == 'cancelled'


def test_a_refused_date_leaves_the_goal_waiting_for_a_valid_one(store):
    gid = blocked_bluepeak(store)
    for bad in ('2026-10-17', '2027-01-16'):  # Today, and 91 days later.
        with pytest.raises(ValueError, match='90 giorni'):
            decide(store, gid, action='reschedule', due_date=bad)
        assert goal(store, gid)['status'] == 'blocked'
    decide(store, gid, action='reschedule', due_date='2027-01-15')
    assert goal(store, gid)['status'] == 'open'


def test_a_goal_not_waiting_for_the_rep_refuses_a_decision(store):
    store.approve(asyncio.run(analyze(store, 'OPP-001'))['proposal_id'])
    gid = store.goals()[0]['id']
    with pytest.raises(ValueError, match='non in attesa'):
        decide(store, gid, action='drop')


def test_the_decision_survives_a_restart(store):
    gid = blocked_bluepeak(store)
    restarted = Store(store.settings)  # New process, same database.
    decide(restarted, gid, action='reschedule', due_date='2027-01-10')
    assert goal(restarted, gid)['due_date'] == '2027-01-10'


def test_http_decision_needs_session_origin_and_a_valid_body(store):
    gid = blocked_bluepeak(store)
    with TestClient(create_app(replace(store.settings, reference_date='2026-10-17'))) as client:
        headers, route = {'Origin': store.settings.origin}, f'/api/goals/{gid}/decision'
        assert client.post(route, json={'action': 'drop'}, headers=headers).status_code == 401
        client.post('/api/login', json={'password': 'local-demo'}, headers=headers)
        assert client.post(route, json={'action': 'drop'}).status_code == 403
        assert client.post(route, json={'action': 'drop', 'due_date': '2027-01-15'}, headers=headers).status_code == 422
        assert client.post(route, json={'action': 'reschedule'}, headers=headers).status_code == 422
        assert client.post(route, json={'action': 'drop', 'title': 'x'}, headers=headers).status_code == 422
        assert client.post(route, json={'action': 'drop'}, headers=headers).status_code == 200
        assert client.post(route, json={'action': 'drop'}, headers=headers).status_code == 409
