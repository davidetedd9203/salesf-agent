import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')


@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv('DB_PATH', str(ROOT / 'var/crm.sqlite3'))
    mode: str = os.getenv('AGENT_MODE', 'demo')
    model: str = os.getenv('OPENROUTER_MODEL', '')
    api_key: str = os.getenv('OPENROUTER_API_KEY', '')
    owner_id: str = 'AE-001'  # Bound to the demo identity; never supplied by the model/client.
    reference_date: str = os.getenv('REFERENCE_DATE', '2026-10-12')
    password: str = os.getenv('DEMO_PASSWORD', 'local-demo')
    origin: str = os.getenv('APP_ORIGIN', 'http://localhost:3000')
    cookie_secure: bool = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
    # The server starts the morning briefing by itself, once per demo date (see backend/briefing.py).
    briefing_auto: bool = os.getenv('BRIEFING_AUTO', 'true').lower() == 'true'

