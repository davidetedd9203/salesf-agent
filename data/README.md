# Sales Copilot — Next Best Action Agent

Synthetic CRM fixture, reference date **2026-10-12**. All names are fictitious, emails use example.invalid.

## Files
- `opportunities.csv`: 20 opportunities, one owner.
- `contacts.csv`: 20 contacts.
- `notes.csv`: 60 untrusted CRM notes.
- `activities.csv`: historical activities and example scheduled tasks.
- `ground_truth.csv`: 5 labeled evaluation scenarios.

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
