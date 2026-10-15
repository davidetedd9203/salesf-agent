"""Tests pin the agent defaults: a local .env tuned for the demo (ACCOUNT_NOISE, AGENT_STRATEGY) must not change fixtures.
load_dotenv never overrides variables already set, and Settings reads them at import, so this runs before any backend import."""
import os

os.environ.update(ACCOUNT_NOISE='0', AGENT_STRATEGY='fixed', ORCHESTRATOR='asyncio')
