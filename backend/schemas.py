from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Evidence(StrictModel):
    note_id: str = Field(min_length=1, max_length=80)
    quote: str = Field(min_length=12, max_length=500)


class TaskDraft(StrictModel):
    kind: Literal['schedule_demo', 'prepare_security_response']
    due_date: date


class Decision(StrictModel):
    decision: Literal['recommend', 'clarify', 'no_action']
    priority: Literal['high', 'normal', 'low']
    reason: str = Field(min_length=10, max_length=1200)
    evidence: list[Evidence] = Field(min_length=1, max_length=5)
    task: TaskDraft | None
    question: str | None = Field(max_length=300)
    revisit_on: date | None = Field(default=None, description='Only for no_action caused by an agreed waiting period: '
                                    'the explicit end date quoted in evidence, when you will re-investigate. Otherwise null.')

    @model_validator(mode='after')
    def coherent(self):
        if (self.decision == 'recommend') != (self.task is not None):
            raise ValueError('Only recommendations may have a task, and must have one')
        if (self.decision == 'clarify') != bool(self.question):
            raise ValueError('Only clarify decisions must contain a question')
        if self.revisit_on and self.decision != 'no_action':
            raise ValueError('Only no_action decisions may schedule a revisit')
        return self


class AccountDecision(Decision):
    """search and pipeline strategies: a clarification can name who resolves it, chosen among contacts actually read."""
    ask_contact_id: str | None = Field(default=None, max_length=80, description='Only for clarify: contact_id from get_contacts '
                                       'of the person who can resolve the conflict, based on evidence. Otherwise null.')

    @model_validator(mode='after')
    def contact_only_for_clarify(self):
        if self.ask_contact_id and self.decision != 'clarify':
            raise ValueError('Only clarify decisions may name a contact')
        return self



class GoalCheck(StrictModel):
    """What happened to an approved task's goal. The model reads; the server decides the next action."""
    outcome: Literal['achieved', 'pending', 'blocked']
    reason: str = Field(min_length=10, max_length=600)
    evidence: list[Evidence] = Field(max_length=3)
    question: str | None = Field(max_length=300, description='Only for blocked: the decision the rep has to make. Otherwise null.')

    @model_validator(mode='after')
    def coherent(self):
        if self.outcome != 'pending' and not self.evidence:
            raise ValueError('achieved and blocked need evidence')
        if (self.outcome == 'blocked') != bool(self.question):
            raise ValueError('Only blocked outcomes must contain a question')
        return self


class ListQuery(StrictModel):
    sort: Literal['priority', 'amount', 'close_date']
    stage: Literal['Discovery', 'Qualification', 'Proposal', 'Negotiation'] | None = None
    only_candidates: bool = False
    account: str | None = Field(default=None, min_length=2, max_length=80, description='Case-insensitive part of the account name, e.g. "helios".')
    limit: int = Field(default=5, ge=1, le=10)


class ChatTask(StrictModel):
    """A task the rep asked for in their own words. Only a proposal: the rep's click creates it."""
    opportunity_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=3, max_length=120, pattern=r'^[^\r\n]+$', description="The user's task in Italian, in their words.")
    due_date: date


class ChatReply(StrictModel):
    message: str = Field(min_length=1, max_length=800, description='At most 600 characters; do not repeat the listed records.')
    opportunity_ids: list[str] = Field(max_length=5)


class ChatMessage(StrictModel):
    role: Literal['user', 'assistant']  # No client-supplied system or tool messages.
    content: str = Field(min_length=1, max_length=1000)


class ChatRequest(StrictModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=12)

    @model_validator(mode='after')
    def ends_with_user(self):
        if self.messages[-1].role != 'user':
            raise ValueError('The last message must come from the user')
        return self


class AnalysisRequest(StrictModel):
    opportunity_ids: list[str] = Field(min_length=1, max_length=5)


class ClockRequest(StrictModel):
    reference_date: date


class ApprovalRequest(StrictModel):
    approved: Literal[True]


class LoginRequest(StrictModel):
    password: str = Field(min_length=1, max_length=200)

