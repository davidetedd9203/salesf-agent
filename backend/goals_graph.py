"""Experiment (FOLLOWTHROUGH=graph): the goal follow-through as a LangGraph graph, compared with the plain path in goals.py.

Same reading (read_outcome), same policy (apply_check), same rep decision (Store.decide_goal): only the control flow moves.
read -> decide -> (escalate | ask_rep) -> wait_rep, where wait_rep is an interrupt persisted by a SQLite checkpointer
and resumed by the rep's decision, possibly days later and after a restart. One thread per goal.
The goals table stays the source of truth for the UI and the briefing; the checkpoint only holds the paused run.
"""
from typing import TypedDict

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .goals import apply_check, read_outcome
from .schemas import GoalDecision


class FollowThrough(TypedDict, total=False):
    goal_id: str
    check: dict
    trace: list
    action: str


def build(store, transport=None):
    def goal(state):
        return next(g for g in store.goals() if g['id'] == state['goal_id'])

    async def read(state):
        check, trace = await read_outcome(store, goal(state), transport)
        return {'check': check, 'trace': trace}

    def decide(state):
        return {'action': apply_check(store, goal(state), state['check'])['last_check']['action']}

    def wait_rep(state):
        # Pauses here; the value passed to Command(resume=...) comes back as the rep's decision.
        answer = interrupt({'goal_id': state['goal_id'], 'question': state['check'].get('question')})
        store.decide_goal(state['goal_id'], GoalDecision.model_validate(answer))
        return {}

    graph = StateGraph(FollowThrough)
    graph.add_node('read', read)
    graph.add_node('decide', decide)
    graph.add_node('wait_rep', wait_rep)
    graph.add_edge(START, 'read')
    graph.add_edge('read', 'decide')
    graph.add_conditional_edges('decide', lambda s: 'wait_rep' if s['action'] in ('escalate', 'ask_rep') else END, ['wait_rep', END])
    graph.add_edge('wait_rep', END)
    return graph


def checkpoints(store):
    return AsyncSqliteSaver.from_conn_string(store.settings.db_path + '.graph')


async def run(store, goal, transport=None):
    """Drop-in for goals.check_goal: same return shape."""
    async with checkpoints(store) as saver:
        state = await build(store, transport).compile(checkpointer=saver).ainvoke(
            {'goal_id': goal['id']}, {'configurable': {'thread_id': goal['id']}})
    return {'goal': next(g for g in store.goals() if g['id'] == goal['id']), 'trace': state['trace']}


async def resume(store, gid, decision: GoalDecision):
    async with checkpoints(store) as saver:
        graph, config = build(store).compile(checkpointer=saver), {'configurable': {'thread_id': gid}}
        if not (await graph.aget_state(config)).interrupts:
            raise ValueError('Obiettivo non in attesa di una tua decisione')
        # Observed (G1): if wait_rep fails after a resume, the next resume replays the first value, not the new one,
        # and the goal can never be decided. Validate before resuming, so only a valid decision enters the graph.
        store.check_decision(decision)
        await graph.ainvoke(Command(resume=decision.model_dump(mode='json')), config)
