import asyncio
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response

from .agent import AgentError, analyze
from .briefing import run_briefing
from .chat import chat
from .config import Settings
from .schemas import AnalysisRequest, ApprovalRequest, ChatRequest, ClockRequest, LoginRequest
from .store import Store


def create_app(settings=None):
    settings = settings or Settings()
    store = Store(settings)
    sessions = {}
    login_attempts = {}
    analysis_lock = asyncio.Lock()
    last_analysis = [0.0]
    background = set()
    temporal = {}
    if settings.orchestrator not in ('asyncio', 'temporal'):
        raise ValueError('ORCHESTRATOR deve essere asyncio oppure temporal')

    async def ensure_briefing(trigger):
        """Proactive trigger: runs without a user request, once per demo date, under the shared model lock."""
        live_ready = store.settings.mode == 'demo' or bool(settings.api_key and settings.model)
        if not settings.briefing_auto or not live_ready or store.briefing(store.settings.reference_date):
            return
        if settings.orchestrator == 'temporal':
            # The workflow ID per owner and date replaces the in-process lock as the guard against double runs.
            from .workflows import start_briefing
            await start_briefing(temporal['client'], settings, store.settings.reference_date, trigger)
            return
        if analysis_lock.locked():
            return
        async with analysis_lock:
            try:
                await run_briefing(store, trigger)
            except Exception as error:  # Visible in the audit; the next tick retries.
                store.audit('briefing_failed', {'briefing_date': store.settings.reference_date, 'error': str(error)[:300]})

    async def morning_loop():
        # Production: a cron at 07:00 per user. Here the demo date only changes when the presenter moves the clock.
        while True:
            await ensure_briefing('scheduler')
            await asyncio.sleep(60)

    def spawn(coroutine):
        task = asyncio.create_task(coroutine)
        background.add(task)
        task.add_done_callback(background.discard)

    @asynccontextmanager
    async def lifespan(app):
        if settings.orchestrator == 'temporal':
            from temporalio.client import Client
            from .workflows import briefing_worker
            # No silent fallback to asyncio: an unreachable Temporal server stops startup with a visible error.
            temporal['client'] = await Client.connect(settings.temporal_address)
            spawn(briefing_worker(temporal['client'], settings).run())  # In-process for the demo; `python -m backend.workflows` runs it separately.
        if settings.briefing_auto:
            spawn(morning_loop())
        yield
        for task in list(background):
            task.cancel()

    app = FastAPI(title='Sales Copilot — demo locale per colloquio', lifespan=lifespan)
    app.state.store = store

    @app.middleware('http')
    async def boundaries(request: Request, call_next):
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.headers.get('origin') != settings.origin:
            return Response('Origine della richiesta non consentita', status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    def authorized(request: Request):
        token = request.cookies.get('sales_session', '')
        if sessions.get(token, 0) < time.time():
            sessions.pop(token, None)
            raise HTTPException(401, 'Accedi alla demo locale')
        return settings.owner_id

    def crm_error(error):
        raise HTTPException(404 if isinstance(error, LookupError) else 409, str(error))

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.post('/api/login')
    def login(body: LoginRequest, request: Request, response: Response):
        address = request.client.host if request.client else 'local'
        now = time.monotonic()
        attempts = [t for t in login_attempts.get(address, []) if now - t < 60]
        if len(attempts) >= 5:
            raise HTTPException(429, 'Troppi tentativi. Riprova tra un minuto.')
        attempts.append(now)
        login_attempts[address] = attempts
        if not secrets.compare_digest(body.password, settings.password):
            raise HTTPException(401, 'Password demo non corretta')
        for token, expires in list(sessions.items()):
            if expires < time.time():
                sessions.pop(token)
        token = secrets.token_urlsafe(32)
        sessions[token] = time.time() + 8 * 3600
        response.set_cookie('sales_session', token, httponly=True, samesite='strict',
                            secure=settings.cookie_secure, max_age=8 * 3600, path='/')
        return {'owner_id': settings.owner_id}

    @app.post('/api/logout')
    def logout(request: Request, response: Response):
        sessions.pop(request.cookies.get('sales_session'), None)
        response.delete_cookie('sales_session', path='/')
        return {'ok': True}

    @app.get('/api/config', dependencies=[Depends(authorized)])
    def configuration():
        return {'mode': settings.mode, 'model': settings.model or None, 'reference_date': store.settings.reference_date,
                'base_date': store.base_date.isoformat(), 'briefing_auto': settings.briefing_auto, 'orchestrator': settings.orchestrator,
                'owner_id': settings.owner_id, 'ready': settings.mode == 'demo' or bool(settings.api_key and settings.model)}

    @app.post('/api/clock', dependencies=[Depends(authorized)])
    async def clock(body: ClockRequest):
        if analysis_lock.locked():
            raise HTTPException(429, "Un'analisi è in corso: attendi prima di spostare l'orologio")
        try:
            store.set_clock(body.reference_date)
        except ValueError as error:
            raise HTTPException(422, str(error))
        spawn(ensure_briefing('clock'))  # The user moved time; the briefing starts on its own.
        return configuration()

    @app.get('/api/briefing', dependencies=[Depends(authorized)])
    def briefing():
        day = store.settings.reference_date
        if found := store.briefing(day):
            return {'status': 'ready', **found}
        enabled = settings.briefing_auto and (settings.mode == 'demo' or bool(settings.api_key and settings.model))
        return {'status': 'running' if analysis_lock.locked() else 'pending' if enabled else 'disabled', 'briefing_date': day}

    @app.post('/api/tasks/{tid}/complete', dependencies=[Depends(authorized)])
    def complete_task(tid: str):
        try:
            store.complete_task(tid)
            return {'ok': True}
        except ValueError as error:
            crm_error(error)

    @app.get('/api/goals', dependencies=[Depends(authorized)])
    def goals():
        return store.goals()

    @app.post('/api/goals/{gid}/cancel', dependencies=[Depends(authorized)])
    def cancel_goal(gid: str):
        try:
            store.cancel_goal(gid)
            return {'ok': True}
        except ValueError as error:
            crm_error(error)

    @app.get('/api/revisits', dependencies=[Depends(authorized)])
    def revisits():
        return store.revisits()

    @app.post('/api/revisits/{rid}/cancel', dependencies=[Depends(authorized)])
    def cancel_revisit(rid: str):
        try:
            store.cancel_revisit(rid)
            return {'ok': True}
        except ValueError as error:
            crm_error(error)

    @app.get('/api/opportunities', dependencies=[Depends(authorized)])
    def opportunities():
        return store.opportunities()

    @app.get('/api/opportunities/{oid}', dependencies=[Depends(authorized)])
    def opportunity(oid: str):
        try:
            return store.context(oid)
        except LookupError as error:
            crm_error(error)

    @app.post('/api/analysis', dependencies=[Depends(authorized)])
    async def analysis(body: AnalysisRequest):
        if len(set(body.opportunity_ids)) != len(body.opportunity_ids):
            raise HTTPException(422, 'ID opportunità duplicati')
        for oid in body.opportunity_ids:
            try:
                store.opportunity(oid)
            except LookupError as error:
                crm_error(error)
        if analysis_lock.locked():
            raise HTTPException(429, "Un'analisi è già in corso")
        if time.monotonic() - last_analysis[0] < 2:
            raise HTTPException(429, "Attendi due secondi tra un'analisi e l'altra")
        async with analysis_lock:
            last_analysis[0] = time.monotonic()
            results = []
            for oid in body.opportunity_ids:
                try:
                    results.append(await analyze(store, oid))
                except (AgentError, LookupError) as error:
                    results.append({'opportunity_id': oid, 'mode': settings.mode, 'error': str(error)})
            return {'results': results}

    @app.post('/api/chat', dependencies=[Depends(authorized)])
    async def chat_turn(body: ChatRequest):
        # Shares the analysis lock: one model call at a time for this single-user demo.
        if analysis_lock.locked():
            raise HTTPException(429, "Un'altra richiesta al modello è in corso")
        async with analysis_lock:
            try:
                return await chat(store, [m.model_dump() for m in body.messages])
            except AgentError as error:
                raise HTTPException(502, str(error))

    @app.post('/api/proposals/{pid}/approve', dependencies=[Depends(authorized)])
    def approve(pid: str, body: ApprovalRequest):
        try:
            return store.approve(pid)
        except (LookupError, ValueError) as error:
            crm_error(error)

    @app.post('/api/proposals/{pid}/reject', dependencies=[Depends(authorized)])
    def reject(pid: str):
        try:
            store.reject(pid)
            return {'ok': True}
        except ValueError as error:
            crm_error(error)

    @app.get('/api/tasks', dependencies=[Depends(authorized)])
    def tasks():
        return store.records('tasks')

    @app.get('/api/audit', dependencies=[Depends(authorized)])
    def audit():
        return store.records('audit')

    return app


app = create_app()
