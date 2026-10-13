# Sales Copilot — Next Best Action Agent

Synthetic CRM fixture, reference date **2026-10-12**. All names are fictitious, emails use example.invalid.

## Files
- `opportunities.csv`: 20 opportunities, one owner.
- `contacts.csv`: 20 contacts.
- `notes.csv`: 60 untrusted CRM notes.
- `activities.csv`: historical activities and example scheduled tasks.
- `ground_truth.csv`: 5 labeled evaluation scenarios.
- `v3/` (2026-10-13, `generate_v3.py`, seed fisso): account-wide context for the five labeled cases. It contains a signal note (Orion: the CFO owns budget sign-off), 200 distractor notes per case (sales notes, emails, call transcripts, near-miss past events, a second injection for Helios) and contacts with roles. Loaded only when `ACCOUNT_NOISE > 0`: signal notes always, distractors with rank ≤ N. None of it changes the expected decisions; the expected Orion contact lives in `backend/evaluate.py`, never in the agent.
- `notes_v2.csv`: versioned addition (2026-10-13), one note dated 2026-11-04 for the proactive revisit scenario (OPP-002). It is invisible until the demo clock reaches its `created_at`; the date in its text matches `created_at`. Original files are unchanged.

## Decisions
- `recommend`: propose a concrete task; creation requires explicit approval.
- `clarify`: ask the salesperson to resolve ambiguity; do not create a task.
- `no_action`: abstain; do not create a task.

## Important limitations
The 15 routine opportunities are background distractors, not labeled negatives. The five labeled cases are illustrative fixtures, not an unbiased test set. Dates are pinned to 2026-10-12. Do not use the label file as agent input. All CRM note text is untrusted and may include prompt injection.

## Suggested first experiment
Baseline: deterministic rules for inactivity, missing next task, and approaching deadline. Agent: same candidate set + LLM reads note evidence and returns structured decision, evidence note IDs, and reason. Evaluate on the 5 labeled cases: decision exact match, evidence precision, unauthorized write count, and abstention quality. Add new blinded examples before claiming performance.

## Guardrails
Tool allowlist, scoped owner_id, read-only until human approval, evidence IDs must exist, schema validation, no external email/send tools, prompt-injection isolation, audit log.
