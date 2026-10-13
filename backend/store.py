import csv
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from .config import ROOT, Settings


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, settings: Settings):
        self.settings = settings
        Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS opportunities (id TEXT PRIMARY KEY, owner TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS notes (id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS activities (id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS contacts (id TEXT PRIMARY KEY, account_id TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS proposals (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, opportunity_id TEXT NOT NULL,
                    snapshot TEXT NOT NULL, decision TEXT NOT NULL, mode TEXT NOT NULL,
                    created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending');
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, opportunity_id TEXT NOT NULL,
                    proposal_id TEXT UNIQUE NOT NULL REFERENCES proposals(id), title TEXT NOT NULL,
                    due_date TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY, owner TEXT NOT NULL, event TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL);
            ''')
            if not db.execute('SELECT 1 FROM opportunities LIMIT 1').fetchone():
                for table, key, scope in [('opportunities', 'opportunity_id', 'owner_id'),
                                          ('notes', 'note_id', 'opportunity_id'),
                                          ('activities', 'activity_id', 'opportunity_id'),
                                          ('contacts', 'contact_id', 'account_id')]:
                    with (ROOT / 'data' / f'{table}.csv').open() as f:
                        for row in csv.DictReader(f):
                            db.execute(f'INSERT INTO {table} VALUES (?,?,?)', (row[key], row[scope], json.dumps(row)))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.settings.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def opportunity(self, oid, db=None):
        if db is None:
            with self.connect() as conn:
                return self.opportunity(oid, conn)
        row = db.execute('SELECT data FROM opportunities WHERE id=? AND owner=?', (oid, self.settings.owner_id)).fetchone()
        if not row:
            raise LookupError('Opportunità non disponibile per questo account')
        return json.loads(row['data'])

    def context(self, oid, db=None):
        if db is None:
            with self.connect() as conn:
                return self.context(oid, conn)
        opp = self.opportunity(oid, db)
        notes = [json.loads(r['data']) for r in db.execute('SELECT data FROM notes WHERE opportunity_id=? ORDER BY id', (oid,))]
        activities = [json.loads(r['data']) for r in db.execute('SELECT data FROM activities WHERE opportunity_id=? ORDER BY id', (oid,))]
        tasks = [dict(r) for r in db.execute('SELECT * FROM tasks WHERE opportunity_id=? AND owner=? ORDER BY id', (oid, self.settings.owner_id))]
        return {'opportunity': opp, 'notes': notes, 'activities': activities, 'tasks': tasks}

    @staticmethod
    def fingerprint(context):
        return hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()

    def opportunities(self):
        with self.connect() as db:
            rows = db.execute('SELECT id FROM opportunities WHERE owner=? ORDER BY id', (self.settings.owner_id,)).fetchall()
            result = []
            today = date.fromisoformat(self.settings.reference_date)
            for row in rows:
                context = self.context(row['id'], db)
                opp = context['opportunity']
                pending = any(a['type'] == 'Task' and not a['completed_at'] for a in context['activities']) or bool(context['tasks'])
                reasons = []
                if (today - date.fromisoformat(opp['last_activity_date'])).days >= 14:
                    reasons.append('Nessuna attività registrata da 14+ giorni')
                if not pending:
                    reasons.append('Nessuna prossima Task pianificata')
                if 0 <= (date.fromisoformat(opp['close_date']) - today).days <= 21:
                    reasons.append('Chiusura prevista entro 21 giorni')
                result.append({**opp, 'candidate_reasons': reasons if opp['status'] == 'Open' else [], 'has_pending_task': pending})
            return result

    def latest_decisions(self):
        with self.connect() as db:
            rows = db.execute("SELECT opportunity_id, decision FROM proposals WHERE owner=? AND status != 'rejected' ORDER BY created_at",
                              (self.settings.owner_id,)).fetchall()
        return {r['opportunity_id']: json.loads(r['decision']) for r in rows}  # Later analyses overwrite earlier ones.

    def audit(self, event, data, db=None):
        if db is None:
            with self.connect() as conn:
                self.audit(event, data, conn)
                return
        db.execute('INSERT INTO audit(owner,event,data,created_at) VALUES (?,?,?,?)',
                   (self.settings.owner_id, event, json.dumps(data), timestamp()))

    def save_analysis(self, oid, context, decision, trace, mode):
        pid = str(uuid4())
        with self.connect() as db:
            db.execute('INSERT INTO proposals(id,owner,opportunity_id,snapshot,decision,mode,created_at) VALUES (?,?,?,?,?,?,?)',
                       (pid, self.settings.owner_id, oid, self.fingerprint(context), json.dumps(decision), mode, timestamp()))
            self.audit('analysis_completed', {'proposal_id': pid, 'opportunity_id': oid, 'decision': decision, 'trace': trace, 'mode': mode}, db)
        return {'proposal_id': pid, 'opportunity_id': oid, 'mode': mode, 'result': decision, 'trace': trace}

    def approve(self, pid):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            p = db.execute('SELECT * FROM proposals WHERE id=? AND owner=?', (pid, self.settings.owner_id)).fetchone()
            if not p:
                raise LookupError('Proposta non disponibile')
            existing = db.execute('SELECT * FROM tasks WHERE proposal_id=? AND owner=?', (pid, self.settings.owner_id)).fetchone()
            if existing:
                return dict(existing)  # Idempotent repeat: never create a second task.
            decision = json.loads(p['decision'])
            if p['status'] != 'pending' or decision['decision'] != 'recommend' or not decision['task']:
                raise ValueError('Questa decisione non può creare una Task')
            if (datetime.now(timezone.utc) - datetime.fromisoformat(p['created_at'])).total_seconds() > 1800:
                raise ValueError("Proposta scaduta. Analizza di nuovo l'opportunità.")
            context = self.context(p['opportunity_id'], db)
            if self.fingerprint(context) != p['snapshot']:
                raise ValueError("Il CRM è cambiato dopo l'analisi. Analizza di nuovo l'opportunità.")
            if context['tasks'] or any(a['type'] == 'Task' and not a['completed_at'] for a in context['activities']):
                raise ValueError("Esiste già una Task. Verificala prima di aggiungerne un'altra.")
            task = {'id': str(uuid4()), 'owner': self.settings.owner_id, 'opportunity_id': p['opportunity_id'],
                    'proposal_id': pid, **decision['task'], 'created_at': timestamp()}
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',
                       (task['id'], task['owner'], task['opportunity_id'], pid, task['title'], task['due_date'], task['created_at']))
            db.execute("UPDATE proposals SET status='approved' WHERE id=?", (pid,))
            self.audit('task_approved', task, db)
            return task

    def reject(self, pid):
        with self.connect() as db:
            changed = db.execute("UPDATE proposals SET status='rejected' WHERE id=? AND owner=? AND status='pending'", (pid, self.settings.owner_id)).rowcount
            if not changed:
                raise ValueError('Proposta non disponibile o già gestita')
            self.audit('proposal_rejected', {'proposal_id': pid}, db)

    def records(self, table):
        if table not in ('tasks', 'audit'):
            raise ValueError('Unsupported table')
        with self.connect() as db:
            rows = [dict(r) for r in db.execute(f'SELECT * FROM {table} WHERE owner=? ORDER BY created_at DESC LIMIT 100', (self.settings.owner_id,))]
            if table == 'audit':
                for row in rows:
                    row['data'] = json.loads(row['data'])
            return rows
