# Sales Copilot
<!-- impeccable:product-schema 1 -->
## Platform
web
## Stack
FastAPI, SQLite, Next.js, OpenRouter: retained from the agreed MVP.
## Users
An individual Account Executive preparing today's follow-ups; a Salesforce FDE panel reviews the engineering method.
## Product Purpose
Investigate candidate opportunities using CRM evidence, recommend a concrete task, clarify conflicts or abstain. Create tasks only after explicit human approval.
## Operating Context
A reproducible interview demo with a pinned reference date, 20 synthetic opportunities and five labeled cases. Local source-code delivery; no hosting requested.
## Capabilities and Constraints
Read-only bounded tool calling, owner scope, no emails, no forecasting, approval and audit. Offline mode must be explicitly labeled as a scripted simulation. OpenRouter mode must fail visibly rather than silently substitute simulation.
## Evidence on Hand
The previously supplied sales_agent_mvp_dataset.zip is recovered in prior/. Five cases are illustrative, not market validation or a representative benchmark.
## Product Principles
Evidence before action. Separate deterministic detection from semantic interpretation. Report uncertainty. Evaluate failures honestly.
## Brand Commitments
Sales Copilot name. English interface assumed for the interview; Italian setup documentation.
