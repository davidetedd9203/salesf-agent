"""Account-wide context (v3): search agent and one-call pipeline share data, schema and validator."""
import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from backend.account_agent import account_read, scripted_account, search, validate_account_decision
from backend.agent import AgentError, analyze
from backend.config import Settings
from backend.store import Store

LABELS = {'OPP-001': 'recommend', 'OPP-002': 'no_action', 'OPP-003': 'recommend', 'OPP-004': 'clarify', 'OPP-005': 'no_action'}


@pytest.fixture
def store(tmp_path):
    return Store(Settings(db_path=str(tmp_path / 'crm.sqlite3'), mode='demo', briefing_auto=False, strategy='search', account_noise=50))


def account(store, oid):
    return {**store.context(oid), 'contacts': store.contacts(oid)}


def seen():
    return {'notes': set(), 'contacts': set()}


def test_v3_is_opt_in_and_contacts_carry_no_email(store, tmp_path):
    assert len(store.context('OPP-004')['notes']) == 3 + 1 + 50
    plain = Store(Settings(db_path=str(tmp_path / 'plain.sqlite3'), briefing_auto=False))
    assert len(plain.context('OPP-004')['notes']) == 3 and len(plain.contacts('OPP-004')) == 1
    assert all(set(c) == {'contact_id', 'name', 'role'} for c in store.contacts('OPP-004'))
    with pytest.raises(LookupError):
        Store(replace(store.settings, owner_id='AE-OTHER')).contacts('OPP-004')


@pytest.mark.parametrize('name,args', [('get_note', {'opportunity_id': 'OPP-004', 'note_id': 'NOTE-001-1'}),
                                       ('search_notes', {'opportunity_id': 'OPP-001', 'query': 'demo'}),
                                       ('search_notes', {'opportunity_id': 'OPP-004', 'query': 'demo', 'limit': 50}),
                                       ('search_notes', {'opportunity_id': 'OPP-004', 'query': 'demo', 'owner_id': 'AE-OTHER'}),
                                       ('execute_sql', {'opportunity_id': 'OPP-004'})])
def test_account_reads_are_scoped_and_bounded(store, name, args):
    with pytest.raises(AgentError):
        account_read(name, args, 'OPP-004', account(store, 'OPP-004'), seen())


def test_search_is_deterministic_keyword_ranking(store):
    notes = account(store, 'OPP-004')['notes']
    assert [n['note_id'] for n in search(notes, 'budget sign-off', 5)][0] == 'NV3-004-S1'
    assert search(notes, 'zzzz', 5) == []


def test_citing_an_existing_but_unread_note_is_rejected(store):
    context = account(store, 'OPP-001')
    raw = scripted_account('OPP-001', context, store.settings, [], 'pipeline')
    raw = {k: v for k, v in raw.items() if k != 'ask_contact'}
    raw['task'] = {k: v for k, v in raw['task'].items() if k != 'title'}
    validate_account_decision(raw, context, {'notes': {'NOTE-001-1', 'NOTE-001-2'}, 'contacts': set()}, store.settings)
    with pytest.raises(AgentError, match='citazione esatta'):
        validate_account_decision(raw, context, {'notes': {'NOTE-001-2'}, 'contacts': set()}, store.settings)


@pytest.mark.parametrize('contact,read,ok', [('CON-004-B', {'CON-004-B'}, True), ('CON-004-B', set(), False),
                                             ('CON-001', {'CON-001'}, False)])
def test_named_contact_must_be_read_and_of_this_account(store, contact, read, ok):
    context = account(store, 'OPP-004')
    raw = {'decision': 'clarify', 'priority': 'normal', 'reason': 'Gli stakeholder non concordano sulla demo.',
           'evidence': [{'note_id': 'NOTE-004-2', 'quote': 'purchasing is paused'}], 'task': None,
           'question': 'Chi decide sulla demo?', 'ask_contact_id': contact}
    state = {'notes': {'NOTE-004-2'}, 'contacts': read}
    if ok:
        assert validate_account_decision(raw, context, state, store.settings)['ask_contact']['role'] == 'CFO'
    else:
        with pytest.raises(AgentError):
            validate_account_decision(raw, context, state, store.settings)


def test_contact_on_a_recommendation_is_rejected(store):
    context = account(store, 'OPP-001')
    raw = {'decision': 'recommend', 'priority': 'normal', 'reason': 'Demo richiesta con scadenza esplicita.',
           'evidence': [{'note_id': 'NOTE-001-1', 'quote': 'technical demo with CTO by 2026-10-16'}],
           'task': {'kind': 'schedule_demo', 'due_date': '2026-10-16'}, 'question': None, 'ask_contact_id': 'CON-001'}
    with pytest.raises(Exception):
        validate_account_decision(raw, context, {'notes': {'NOTE-001-1'}, 'contacts': {'CON-001'}}, store.settings)


@pytest.mark.parametrize('strategy', ['search', 'pipeline'])
def test_demo_strategies_match_labels_and_name_the_decider(store, strategy):
    local = Store(replace(store.settings, strategy=strategy))
    for oid, expected in LABELS.items():
        result = asyncio.run(analyze(local, oid))['result']
        assert result['decision'] == expected
    assert result is not None and asyncio.run(analyze(local, 'OPP-004'))['result']['ask_contact']['contact_id'] == 'CON-004-B'
    assert local.records('tasks') == []


def test_search_proposal_keeps_the_approval_snapshot(store):
    proposal = asyncio.run(analyze(store, 'OPP-001'))
    assert store.approve(proposal['proposal_id'])['title'] == 'Organizzare la demo tecnica richiesta'


def respond(calls):
    return httpx.Response(200, json={'usage': {'prompt_tokens': 10, 'completion_tokens': 5}, 'choices': [{'message': {'tool_calls': [
        {'id': f'c{i}-{name}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}
        for i, (name, args) in enumerate(calls)]}}]})


def test_openrouter_search_protocol_reads_then_decides(store):
    live = Store(replace(store.settings, mode='openrouter', api_key='test-placeholder', model='test/model'))
    good = {'decision': 'recommend', 'priority': 'normal', 'reason': 'Demo richiesta con scadenza esplicita.',
            'evidence': [{'note_id': 'NOTE-001-1', 'quote': 'technical demo with CTO by 2026-10-16'}],
            'task': {'kind': 'schedule_demo', 'due_date': '2026-10-16'}, 'question': None, 'revisit_on': None, 'ask_contact_id': None}
    rounds = [[('get_opportunity', {'opportunity_id': 'OPP-001'}), ('get_activities', {'opportunity_id': 'OPP-001'})],
              [('search_notes', {'opportunity_id': 'OPP-001', 'query': 'requested demo by'})],
              [('submit_decision', good)]]
    seen_requests = []

    def handler(request):
        seen_requests.append(json.loads(request.content))
        return respond(rounds[len(seen_requests) - 1])

    result = asyncio.run(analyze(live, 'OPP-001', httpx.MockTransport(handler)))
    assert result['result']['decision'] == 'recommend'
    names = [[t['function']['name'] for t in r['tools']] for r in seen_requests]
    assert 'submit_decision' not in names[0] and 'submit_decision' not in names[1] and 'submit_decision' in names[2]
    assert 'search_notes' in names[2]  # After the minimum, reading stays the model's choice.
    assert live.records('tasks') == []


def test_openrouter_search_cannot_cite_what_it_did_not_retrieve(store):
    live = Store(replace(store.settings, mode='openrouter', api_key='test-placeholder', model='test/model'))
    unread = {'decision': 'clarify', 'priority': 'normal', 'reason': 'Stakeholder in conflitto sulla demo.',
              'evidence': [{'note_id': 'NV3-004-S1', 'quote': 'budget sign-off for this purchase sits with the CFO'}],
              'task': None, 'question': 'Chi decide?', 'revisit_on': None, 'ask_contact_id': None}
    rounds = [[('get_opportunity', {'opportunity_id': 'OPP-004'}), ('get_activities', {'opportunity_id': 'OPP-004'}),
               ('search_notes', {'opportunity_id': 'OPP-004', 'query': 'zzzz'})],
              [('submit_decision', unread)], [('submit_decision', unread)]]
    count = []

    def handler(request):
        count.append(1)
        return respond(rounds[len(count) - 1])

    with pytest.raises(AgentError):
        asyncio.run(analyze(live, 'OPP-004', httpx.MockTransport(handler)))
    assert live.records('audit')[0]['event'] == 'analysis_failed'


def test_openrouter_pipeline_sends_everything_in_one_call(store):
    live = Store(replace(store.settings, mode='openrouter', api_key='test-placeholder', model='test/model', strategy='pipeline'))
    raw = {'decision': 'no_action', 'priority': 'low', 'reason': 'Attesa concordata con il cliente fino al 5 novembre.',
           'evidence': [{'note_id': 'NOTE-002-1', 'quote': 'no contact until 2026-11-05'}], 'task': None, 'question': None,
           'revisit_on': '2026-11-05', 'ask_contact_id': None}
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return respond([('submit_decision', raw)])

    result = asyncio.run(analyze(live, 'OPP-002', httpx.MockTransport(handler)))
    assert result['result']['revisit_on'] == '2026-11-05' and len(requests) == 1
    assert [t['function']['name'] for t in requests[0]['tools']] == ['submit_decision']
    assert requests[0]['messages'][1]['content'].count('"note_id"') == 3 + 50
