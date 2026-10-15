import csv
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from .config import ROOT, Settings

# Written by the server from the approved task kind; the model never phrases the objective.
GOAL_OBJECTIVES = {'schedule_demo': 'La demo tecnica richiesta si è svolta',
                   'prepare_security_response': 'La risposta al questionario di sicurezza è stata inviata'}
# ponytail: fixed follow-up window for clarifications; let the rep pick the date if two days proves wrong.
CLARIFY_DAYS = 2


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def has_open_task(context):
    """An incomplete CRM activity of type Task, or an approved task the rep has not completed yet."""
    return any(not t.get('completed_at') for t in context['tasks']) or \
        any(a['type'] == 'Task' and not a['completed_at'] for a in context['activities'])


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
                -- Agent memory, not CRM records: a self-scheduled re-investigation and the daily briefing.
                CREATE TABLE IF NOT EXISTS revisits (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, opportunity_id TEXT NOT NULL, due_date TEXT NOT NULL,
                    proposal_id TEXT NOT NULL REFERENCES proposals(id), status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS goals (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, opportunity_id TEXT NOT NULL, task_id TEXT UNIQUE NOT NULL REFERENCES tasks(id),
                    kind TEXT NOT NULL, objective TEXT NOT NULL, due_date TEXT NOT NULL, created_on TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open', next_check TEXT NOT NULL, nudges INTEGER NOT NULL DEFAULT 0,
                    last_check TEXT, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS briefings (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, briefing_date TEXT NOT NULL, data TEXT NOT NULL,
                    created_at TEXT NOT NULL, UNIQUE(owner, briefing_date));
            ''')
            if 'expires_at' not in {r['name'] for r in db.execute('PRAGMA table_info(proposals)')}:
                db.execute('ALTER TABLE proposals ADD COLUMN expires_at TEXT')
            if 'completed_at' not in {r['name'] for r in db.execute('PRAGMA table_info(tasks)')}:
                db.execute('ALTER TABLE tasks ADD COLUMN completed_at TEXT')
            if not db.execute('SELECT 1 FROM opportunities LIMIT 1').fetchone():
                for table, key, scope in [('opportunities', 'opportunity_id', 'owner_id'),
                                          ('notes', 'note_id', 'opportunity_id'),
                                          ('activities', 'activity_id', 'opportunity_id'),
                                          ('contacts', 'contact_id', 'account_id')]:
                    with (ROOT / 'data' / f'{table}.csv').open() as f:
                        for row in csv.DictReader(f):
                            db.execute(f'INSERT INTO {table} VALUES (?,?,?)', (row[key], row[scope], json.dumps(row)))
            # Versioned addition, original CSVs untouched: notes stay invisible until the demo clock reaches created_at.
            for version in ('notes_v2.csv', 'notes_v4.csv'):  # v4: outcomes after approved tasks, for goal follow-through.
                with (ROOT / 'data' / version).open() as f:
                    for row in csv.DictReader(f):
                        db.execute('INSERT OR IGNORE INTO notes VALUES (?,?,?)', (row['note_id'], row['opportunity_id'], json.dumps(row)))
            if settings.account_noise > 0:
                # v3: account-wide context (data/generate_v3.py). Signal notes always, then the first N distractors.
                with (ROOT / 'data' / 'v3' / 'notes.csv').open() as f:
                    for row in csv.DictReader(f):
                        if int(row.pop('rank')) <= settings.account_noise:
                            db.execute('INSERT OR IGNORE INTO notes VALUES (?,?,?)', (row['note_id'], row['opportunity_id'], json.dumps(row)))
                with (ROOT / 'data' / 'v3' / 'contacts.csv').open() as f:
                    for row in csv.DictReader(f):
                        db.execute('INSERT OR IGNORE INTO contacts VALUES (?,?,?)', (row['contact_id'], row['account_id'], json.dumps(row)))
        self.base_date = date.fromisoformat(settings.reference_date)

    @property
    def today(self):
        return date.fromisoformat(self.settings.reference_date)

    def set_clock(self, day):
        """Demo clock: the fixture date stays pinned unless the presenter explicitly moves it forward."""
        if not 0 <= (day - self.base_date).days <= 120:
            raise ValueError(f"L'orologio demo può andare solo da {self.base_date} a 120 giorni dopo")
        previous = self.settings.reference_date
        self.settings = replace(self.settings, reference_date=day.isoformat())
        self.audit('clock_changed', {'from': previous, 'to': day.isoformat()})

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
        today = self.settings.reference_date  # The CRM as it was known on the demo date.
        notes = [n for r in db.execute('SELECT data FROM notes WHERE opportunity_id=? ORDER BY id', (oid,))
                 if (n := json.loads(r['data']))['created_at'] <= today]
        activities = [a for r in db.execute('SELECT data FROM activities WHERE opportunity_id=? ORDER BY id', (oid,))
                      if (a := json.loads(r['data']))['completed_at'] <= today]
        tasks = [dict(r) for r in db.execute('SELECT * FROM tasks WHERE opportunity_id=? AND owner=? ORDER BY id', (oid, self.settings.owner_id))]
        return {'opportunity': opp, 'notes': notes, 'activities': activities, 'tasks': tasks}

    def contacts(self, oid):
        """Contacts of the opportunity's account, owner-checked. Names and roles only: the agent has no use for emails."""
        with self.connect() as db:
            account = self.opportunity(oid, db)['account_id']
            rows = [json.loads(r['data']) for r in db.execute('SELECT data FROM contacts WHERE account_id=? ORDER BY id', (account,))]
        return [{k: c[k] for k in ('contact_id', 'name', 'role')} for c in rows]

    @staticmethod
    def fingerprint(context):
        return hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()

    def opportunities(self):
        with self.connect() as db:
            rows = db.execute('SELECT id FROM opportunities WHERE owner=? ORDER BY id', (self.settings.owner_id,)).fetchall()
            result = []
            today = self.today
            for row in rows:
                context = self.context(row['id'], db)
                opp = context['opportunity']
                pending = has_open_task(context)
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
        # Later analyses overwrite earlier ones; chat-requested tasks are not analyses and never rank a record.
        return {r['opportunity_id']: d for r in rows if (d := json.loads(r['decision'])).get('source') != 'chat'}

    def audit(self, event, data, db=None):
        if db is None:
            with self.connect() as conn:
                self.audit(event, data, conn)
                return
        db.execute('INSERT INTO audit(owner,event,data,created_at) VALUES (?,?,?,?)',
                   (self.settings.owner_id, event, json.dumps(data), timestamp()))

    def save_analysis(self, oid, context, decision, trace, mode, ttl=1800):
        pid = str(uuid4())
        now = datetime.now(timezone.utc)
        if decision['decision'] == 'clarify':
            # A question alone left the rep with nothing to do. The server drafts the follow-up from a fixed template
            # (contact name and role come from the CRM, never from the model); it exists only once the rep approves it.
            who = decision.get('ask_contact')
            decision = {**decision, 'followup': {'kind': 'clarify', 'due_date': (self.today + timedelta(days=CLARIFY_DAYS)).isoformat(),
                        'title': f"Chiarire con {who['name']} ({who['role']}) la decisione aperta" if who else 'Chiarire con lo stakeholder la decisione aperta'}}
        with self.connect() as db:
            db.execute('INSERT INTO proposals(id,owner,opportunity_id,snapshot,decision,mode,created_at,expires_at) VALUES (?,?,?,?,?,?,?,?)',
                       (pid, self.settings.owner_id, oid, self.fingerprint(context), json.dumps(decision), mode, now.isoformat(),
                        (now + timedelta(seconds=ttl)).isoformat()))
            self.audit('analysis_completed', {'proposal_id': pid, 'opportunity_id': oid, 'decision': decision, 'trace': trace, 'mode': mode}, db)
            # A new analysis replaces earlier plans: due revisits are done, future ones superseded.
            db.execute("UPDATE revisits SET status=CASE WHEN due_date<=? THEN 'done' ELSE 'superseded' END "
                       "WHERE opportunity_id=? AND owner=? AND status='pending'", (self.settings.reference_date, oid, self.settings.owner_id))
            if decision.get('revisit_on'):
                revisit = {'id': str(uuid4()), 'opportunity_id': oid, 'due_date': decision['revisit_on'], 'proposal_id': pid}
                db.execute('INSERT INTO revisits(id,owner,opportunity_id,due_date,proposal_id,created_at) VALUES (?,?,?,?,?,?)',
                           (revisit['id'], self.settings.owner_id, oid, revisit['due_date'], pid, timestamp()))
                self.audit('revisit_scheduled', revisit, db)
        return {'proposal_id': pid, 'opportunity_id': oid, 'mode': mode, 'result': decision, 'trace': trace}

    def propose_task(self, oid, task, mode, ttl=1800):
        """A task the rep asked for in chat: a proposal with snapshot and expiry, approved by the same endpoint as analyses."""
        context = self.context(oid)
        if has_open_task(context):
            raise ValueError("Esiste già una Task aperta per questa opportunità: nessuna proposta creata.")
        pid, now = str(uuid4()), datetime.now(timezone.utc)
        decision = {'decision': 'recommend', 'source': 'chat', 'task': {'kind': 'custom', **task}}
        with self.connect() as db:
            db.execute('INSERT INTO proposals(id,owner,opportunity_id,snapshot,decision,mode,created_at,expires_at) VALUES (?,?,?,?,?,?,?,?)',
                       (pid, self.settings.owner_id, oid, self.fingerprint(context), json.dumps(decision), mode, now.isoformat(),
                        (now + timedelta(seconds=ttl)).isoformat()))
            self.audit('task_proposed', {'proposal_id': pid, 'opportunity_id': oid, 'decision': decision, 'mode': mode}, db)
        return {'proposal_id': pid, 'opportunity_id': oid, 'mode': mode, 'result': decision}

    def reset(self):
        """Back to the fixture: everything the demo produced goes, the CRM fixture tables are never written and stay."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for table in ('goals', 'revisits', 'tasks', 'proposals', 'briefings', 'audit'):  # Children before parents.
                db.execute(f'DELETE FROM {table} WHERE owner=?', (self.settings.owner_id,))
            self.settings = replace(self.settings, reference_date=self.base_date.isoformat())
            self.audit('demo_reset', {'reference_date': self.settings.reference_date}, db)

    def reset_stamp(self):
        """Time of the last reset, '' if never: a new run of the same date needs a new Temporal workflow ID."""
        with self.connect() as db:
            row = db.execute("SELECT created_at FROM audit WHERE owner=? AND event='demo_reset' ORDER BY id DESC LIMIT 1",
                             (self.settings.owner_id,)).fetchone()
        return ''.join(c for c in row['created_at'] if c.isdigit())[:14] if row else ''

    def revisits(self, due_only=False):
        query = "SELECT * FROM revisits WHERE owner=? AND status='pending'" + (' AND due_date<=?' if due_only else '') + ' ORDER BY due_date, created_at'
        args = (self.settings.owner_id, self.settings.reference_date) if due_only else (self.settings.owner_id,)
        with self.connect() as db:
            return [dict(r) for r in db.execute(query, args)]

    def cancel_revisit(self, rid):
        with self.connect() as db:
            changed = db.execute("UPDATE revisits SET status='cancelled' WHERE id=? AND owner=? AND status='pending'", (rid, self.settings.owner_id)).rowcount
            if not changed:
                raise ValueError('Ricontrollo non disponibile o già gestito')
            self.audit('revisit_cancelled', {'revisit_id': rid}, db)

    def briefing(self, day):
        with self.connect() as db:
            row = db.execute('SELECT data, created_at FROM briefings WHERE owner=? AND briefing_date=?', (self.settings.owner_id, day)).fetchone()
        return {**json.loads(row['data']), 'created_at': row['created_at']} if row else None

    def save_briefing(self, day, data):
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO briefings VALUES (?,?,?,?,?)', (str(uuid4()), self.settings.owner_id, day, json.dumps(data), timestamp()))
            self.audit('briefing_completed', {'briefing_date': day, 'counts': data['counts'], 'trigger': data['trigger']}, db)
        return self.briefing(day)

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
            draft = {'recommend': decision.get('task'), 'clarify': decision.get('followup')}.get(decision['decision'])
            if p['status'] != 'pending' or not draft:
                raise ValueError('Questa decisione non può creare una Task')
            expires = datetime.fromisoformat(p['expires_at'] or p['created_at']) + timedelta(seconds=0 if p['expires_at'] else 1800)
            if datetime.now(timezone.utc) > expires:
                raise ValueError("Proposta scaduta. Analizza di nuovo l'opportunità.")
            if draft['due_date'] < self.settings.reference_date:
                raise ValueError("La scadenza della Task è già passata. Analizza di nuovo l'opportunità.")
            context = self.context(p['opportunity_id'], db)
            if self.fingerprint(context) != p['snapshot']:
                raise ValueError("Il CRM è cambiato dopo l'analisi. Analizza di nuovo l'opportunità.")
            if has_open_task(context):
                raise ValueError("Esiste già una Task. Verificala prima di aggiungerne un'altra.")
            task = {'id': str(uuid4()), 'owner': self.settings.owner_id, 'opportunity_id': p['opportunity_id'],
                    'proposal_id': pid, **draft, 'created_at': timestamp()}
            db.execute('INSERT INTO tasks(id,owner,opportunity_id,proposal_id,title,due_date,created_at) VALUES (?,?,?,?,?,?,?)',
                       (task['id'], task['owner'], task['opportunity_id'], pid, task['title'], task['due_date'], task['created_at']))
            db.execute("UPDATE proposals SET status='approved' WHERE id=?", (pid,))
            self.audit('task_approved', task, db)
            if task['kind'] not in GOAL_OBJECTIVES:
                # ponytail: chat and clarify tasks get no goal, the server has no objective to check; add one if reps want follow-through.
                return task
            # The approval also opens a goal: agent memory to follow the task through, not a CRM record.
            goal = {'id': str(uuid4()), 'opportunity_id': task['opportunity_id'], 'task_id': task['id'], 'kind': task['kind'],
                    'objective': GOAL_OBJECTIVES[task['kind']], 'due_date': task['due_date'], 'created_on': self.settings.reference_date}
            db.execute('INSERT INTO goals(id,owner,opportunity_id,task_id,kind,objective,due_date,created_on,next_check,updated_at) '
                       'VALUES (?,?,?,?,?,?,?,?,?,?)', (goal['id'], self.settings.owner_id, goal['opportunity_id'], goal['task_id'],
                                                        goal['kind'], goal['objective'], goal['due_date'], goal['created_on'],
                                                        goal['due_date'], timestamp()))
            self.audit('goal_opened', goal, db)
            return task

    def complete_task(self, tid):
        """The rep's word closes the task and its goal: human authority, no model involved."""
        with self.connect() as db:
            changed = db.execute('UPDATE tasks SET completed_at=? WHERE id=? AND owner=? AND completed_at IS NULL',
                                 (self.settings.reference_date, tid, self.settings.owner_id)).rowcount
            if not changed:
                raise ValueError('Task non disponibile o già completata')
            db.execute("UPDATE goals SET status='achieved', last_check=?, updated_at=? WHERE task_id=? AND owner=? AND status IN ('open','escalated','blocked')",
                       (json.dumps({'outcome': 'achieved', 'action': 'close', 'by': 'rep', 'on': self.settings.reference_date}), timestamp(), tid, self.settings.owner_id))
            self.audit('task_completed', {'task_id': tid, 'on': self.settings.reference_date}, db)

    def goals(self, due_only=False):
        query = 'SELECT * FROM goals WHERE owner=?' + (" AND status='open' AND next_check<=?" if due_only else '') + ' ORDER BY next_check, created_on'
        args = (self.settings.owner_id, self.settings.reference_date) if due_only else (self.settings.owner_id,)
        with self.connect() as db:
            rows = [dict(r) for r in db.execute(query, args)]
        for row in rows:
            row['last_check'] = json.loads(row['last_check']) if row['last_check'] else None
        return rows

    def update_goal(self, gid, status, next_check, nudges, check):
        with self.connect() as db:
            db.execute('UPDATE goals SET status=?, next_check=?, nudges=?, last_check=?, updated_at=? WHERE id=? AND owner=?',
                       (status, next_check, nudges, json.dumps(check), timestamp(), gid, self.settings.owner_id))
            self.audit('goal_checked', {'goal_id': gid, 'status': status, 'next_check': next_check, **check}, db)

    def cancel_goal(self, gid):
        with self.connect() as db:
            changed = db.execute("UPDATE goals SET status='cancelled', updated_at=? WHERE id=? AND owner=? AND status IN ('open','escalated','blocked')",
                                 (timestamp(), gid, self.settings.owner_id)).rowcount
            if not changed:
                raise ValueError('Obiettivo non disponibile o già chiuso')
            self.audit('goal_cancelled', {'goal_id': gid}, db)

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
