'use client';

import {useEffect, useRef, useState} from 'react';

const money = value => new Intl.NumberFormat('it-IT', {style: 'currency', currency: 'EUR', maximumFractionDigits: 0}).format(value);
const welcome = {role: 'assistant', local: true, content: 'Ciao Alex. Chiedimi quali opportunità guardare oggi: le ordino e ti spiego il criterio. Le analisi partono solo quando le avvii tu.'};
const suggestions = ['Quali opportunità hanno la priorità più alta?', 'Quali hanno il valore più alto?', 'Quali chiudono prima?'];
const labels = {recommend: 'Azione proposta', clarify: 'Serve il tuo input', no_action: 'Nessuna azione necessaria'};
// Goal follow-through: the model reports what happened, the server policy picks the action shown here.
const goalActions = {close: ['Obiettivo raggiunto', 'recommend'], wait: ['Obiettivo in corso', 'no_action'],
  nudge: ['In ritardo: promemoria', 'clarify'], escalate: ['Escalation: decidi tu', 'failed'], ask_rep: ['Bloccato: serve una tua decisione', 'clarify']};
const goalStatus = {open: 'in corso', escalated: 'escalation', blocked: 'bloccato', achieved: 'raggiunto', cancelled: 'annullato'};

async function api(path, body) {
  const response = await fetch(`/api/${path}`, {credentials: 'same-origin', cache: 'no-store',
    ...(body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})});
  let data;
  try { data = await response.json(); } catch { throw new Error('Il backend non è disponibile. Avvia FastAPI e riprova.'); }
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Richiesta fallita (${response.status}).`);
  return data;
}

export default function Home() {
  const [signedIn, setSignedIn] = useState(false);
  const [checking, setChecking] = useState(true);
  const [password, setPassword] = useState('');
  const [config, setConfig] = useState(null);
  const [opportunities, setOpportunities] = useState([]);
  const [selected, setSelected] = useState('OPP-001');
  const [context, setContext] = useState(null);
  const [results, setResults] = useState({});
  const [tasks, setTasks] = useState([]);
  const [audit, setAudit] = useState([]);
  const [view, setView] = useState('Oggi');
  const [search, setSearch] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [review, setReview] = useState(null);
  const [resolved, setResolved] = useState({});
  const [messages, setMessages] = useState([welcome]);
  const [question, setQuestion] = useState('');
  const [briefing, setBriefing] = useState(null);
  const [revisits, setRevisits] = useState([]);
  const [goals, setGoals] = useState([]);
  const [clockDate, setClockDate] = useState('2026-11-05');
  const chatLog = useRef(null);
  const mergedBriefing = useRef('');

  useEffect(() => {chatLog.current?.scrollTo({top: chatLog.current.scrollHeight});}, [messages]);

  async function refresh() {
    const [c, o, t, a, b, r, g] = await Promise.all([api('config'), api('opportunities'), api('tasks'), api('audit'), api('briefing'), api('revisits'), api('goals')]);
    setConfig(c); setOpportunities(o); setTasks(t); setAudit(a); setRevisits(r); setGoals(g);
    if (b.status === 'ready' && mergedBriefing.current !== b.created_at) {
      // The briefing's analyses become the current results once; later manual analyses override them.
      mergedBriefing.current = b.created_at;
      setResults(old => ({...old, ...Object.fromEntries(b.items.filter(i => i.analysis).map(i => [i.opportunity_id, i.analysis]))}));
    }
    setBriefing(b);
  }

  useEffect(() => {
    if (!signedIn || !briefing || briefing.status === 'ready' || briefing.status === 'disabled') return;
    const timer = setInterval(() => {refresh().catch(e => setError(e.message));}, 2000);
    return () => clearInterval(timer);
  }, [signedIn, briefing?.status]);

  useEffect(() => {
    refresh().then(() => setSignedIn(true)).catch(() => {}).finally(() => setChecking(false));
  }, []);

  useEffect(() => {
    if (!signedIn || !selected) return;
    let active = true;
    setContext(null);
    api(`opportunities/${selected}`).then(c => {if (active) setContext(c);}).catch(e => {if (active) setError(e.message);});
    return () => {active = false;};
  }, [selected, signedIn]);

  async function login(event) {
    event.preventDefault(); setError(''); setBusy('Accesso in corso');
    try { await api('login', {password}); await refresh(); setSignedIn(true); setPassword(''); }
    catch (e) {setError(e.message);} finally {setBusy('');}
  }

  async function investigate(ids) {
    setError(''); setNotice(''); setReview(null); setBusy(`Analisi di ${ids.length} opportunità`);
    try {
      const response = await api('analysis', {opportunity_ids: ids});
      setResults(old => ({...old, ...Object.fromEntries(response.results.map(r => [r.opportunity_id, r]))}));
      const failed = response.results.filter(r => r.error).length;
      setNotice(`${response.results.length - failed} analizzate${failed ? `; ${failed} fallite. Apri l'opportunità interessata per vedere l'errore.` : '. Controlla le evidenze prima di agire.'}`);
      await refresh();
    } catch (e) {setError(e.message);} finally {setBusy('');}
  }

  async function approve(result) {
    setError(''); setBusy('Creazione della Task approvata');
    try {
      await api(`proposals/${result.proposal_id}/approve`, {approved: true});
      setResolved(old => ({...old, [result.proposal_id]: 'approved'})); setReview(null);
      setNotice('Task creata nel CRM simulato. Nessun messaggio è stato inviato.');
      await refresh(); setContext(await api(`opportunities/${selected}`));
    } catch (e) {setError(e.message);} finally {setBusy('');}
  }

  async function ask(text) {
    const content = text.trim();
    if (!content || busy) return;
    const history = [...messages.filter(m => !m.local && !m.error), {role: 'user', content}].slice(-11);
    setMessages(old => [...old, {role: 'user', content}]); setQuestion(''); setError(''); setBusy('L’assistente sta cercando');
    try {
      const reply = await api('chat', {messages: history.map(({role, content}) => ({role, content}))});
      setMessages(old => [...old, {role: 'assistant', content: reply.message, ids: reply.opportunity_ids, mode: reply.mode}]);
    } catch (e) {
      setMessages(old => [...old, {role: 'assistant', error: true, content: `Non sono riuscito a rispondere: ${e.message}`}]);
    } finally {setBusy('');}
  }

  async function moveClock(event) {
    event.preventDefault(); setError(''); setNotice(''); setReview(null); setBusy('Spostamento dell’orologio demo');
    try {
      await api('clock', {reference_date: clockDate});
      setResults({}); setResolved({}); mergedBriefing.current = '';
      await refresh();
      setNotice(`Orologio demo al ${clockDate}. Il briefing parte da solo: nessuna analisi è stata avviata da te.`);
    } catch (e) {setError(e.message);} finally {setBusy('');}
  }

  async function post(path, message) {
    setError('');
    try {await api(path, {}); await refresh(); if (message) setNotice(message);} catch (e) {setError(e.message);}
  }

  async function cancelRevisit(id) {
    setError('');
    try {await api(`revisits/${id}/cancel`, {}); await refresh();} catch (e) {setError(e.message);}
  }

  async function reject(result) {
    setBusy('Archiviazione della proposta'); setError('');
    try {await api(`proposals/${result.proposal_id}/reject`, {}); setResolved(old => ({...old, [result.proposal_id]: 'rejected'})); setReview(null); await refresh();}
    catch (e) {setError(e.message);} finally {setBusy('');}
  }

  function selectOpportunity(oid) {
    setSelected(oid); setReview(null);
    if (window.matchMedia('(max-width: 650px)').matches) {
      requestAnimationFrame(() => document.getElementById('selected-opportunity')?.scrollIntoView({block: 'start'}));
    }
  }

  if (checking) return <main className="signin"><p role="status">Connessione al workspace…</p></main>;
  if (!signedIn) return <main className="signin"><form onSubmit={login} className="loginform">
    <img className="login-logo" src="/logo.svg" alt="" width="92" height="64"/><h1>Sales Copilot</h1>
    <p>Una prossima mossa chiara, basata sul tuo CRM.</p>
    <div className="demo-note">Workspace per colloquio · dati sintetici<br/>Password demo locale: <code>local-demo</code></div>
    <label htmlFor="password">Password demo</label>
    <input id="password" type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" required/>
    <button className="primary" disabled={!!busy}>{busy || 'Apri workspace'}</button>
    {error && <p role="alert" className="error">{error}</p>}
    <p className="muted">Se hai cambiato DEMO_PASSWORD, usa il valore configurato.</p>
  </form></main>;

  const shortlist = opportunities.filter(o => o.candidate_reasons.length).sort((a,b) => a.close_date.localeCompare(b.close_date));
  const visible = (view === 'Oggi' ? shortlist : opportunities).filter(o => `${o.account_name} ${o.stage}`.toLowerCase().includes(search.toLowerCase()));
  const current = opportunities.find(o => o.opportunity_id === selected);
  const analysis = results[selected];
  const decision = analysis?.result;
  const state = resolved[analysis?.proposal_id];

  return <div className="app-shell">
    <header className="global-header"><a href="/" className="wordmark" aria-label="Sales Copilot, home"><img src="/logo.svg" alt="" width="46" height="32"/></a>
      <span className={`mode ${config.mode === 'demo' ? 'demo' : 'live'}`}>{config.mode === 'demo' ? 'Demo scriptata · nessun LLM' : `Modello reale · ${config.model || 'non configurato'}`}</span>
      <div className="user"><span className="avatar" aria-hidden="true">AM</span><p>Alex Morgan<br/><span>Account Executive · AE-001</span></p><button className="logout" onClick={async () => {try {await api('logout', {}); setSignedIn(false); setResults({}); setMessages([welcome]); setError('');} catch(e) {setError(e.message);}}}>Esci</button></div>
    </header>
    <nav className="context-bar" aria-label="Workspace"><span className="app-name">Sales Copilot</span>{['Oggi', 'Opportunità', 'Task', 'Registro evidenze'].map(item => <button key={item} className={view === item ? 'nav active' : 'nav'} aria-current={view === item ? 'page' : undefined} onClick={() => {setView(item); setError(''); setReview(null);}}>{item}{item === 'Task' && tasks.length > 0 && <span>{tasks.length}</span>}</button>)}</nav>
    <main className="workspace">
      <header className="page-header"><span className="page-icon" aria-hidden="true">{view === 'Task' ? '✓' : view === 'Registro evidenze' ? '≡' : '★'}</span><div><p className="eyebrow">Workspace personale</p><h1>{view === 'Oggi' ? 'La tua prossima mossa' : view}</h1><p>{view === 'Oggi' ? 'Leggi il segnale. Verifica le evidenze. Scegli l’azione.' : view === 'Task' ? 'Ogni Task qui è stata approvata esplicitamente.' : view === 'Registro evidenze' ? 'Tool call, validazione e approvazioni. Nessun ragionamento nascosto.' : 'Tutte le opportunità assegnate a te.'}</p></div><div className="reference">Data di riferimento demo<br/><strong>{config.reference_date}</strong>
        <form className="clock" onSubmit={moveClock}><label htmlFor="clock" className="visually-hidden">Nuova data dell’orologio demo</label>
          <input id="clock" type="date" min={config.base_date} value={clockDate} onChange={e => setClockDate(e.target.value)} required/>
          <button className="secondary" disabled={!!busy || briefing?.status === 'running'}>Sposta orologio demo</button></form></div></header>
      <div className="disclosure">CRM sintetico · {opportunities.length} opportunità · {shortlist.length} candidate selezionate da regole. Le regole segnalano record da rivedere; non stabiliscono un rischio.</div>
      {!config.ready && <p className="error" role="alert">Configurazione OpenRouter incompleta. Imposta chiave API e modello in .env, poi riavvia il backend.</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {notice && <p className="notice" role="status">{notice}</p>}
      {busy && <div className="working" role="status"><span className="spinner" aria-hidden="true"/>{busy}… {config.mode === 'openrouter' && 'Ogni analisi è limitata a 90 secondi.'}</div>}

      {(view === 'Oggi' || view === 'Opportunità') && <>
        {view === 'Oggi' && briefing && <section className="briefing" aria-label="Briefing del mattino">
          <div className="chat-heading"><h2>Briefing del mattino · {briefing.briefing_date}</h2><span>{briefing.status === 'ready'
            ? `Preparato dall’agente alle ${new Date(briefing.created_at).toLocaleTimeString('it-IT', {hour: '2-digit', minute: '2-digit'})}, senza una tua richiesta · ${briefing.mode === 'demo' ? 'simulazione scriptata' : 'modello reale'} · nessuna Task creata`
            : 'Avviato dal server una volta per data'}</span></div>
          {briefing.status === 'disabled' && <p className="briefing-body muted">Briefing automatico disattivato (BRIEFING_AUTO=false).</p>}
          {(briefing.status === 'pending' || briefing.status === 'running') && <div className="working briefing-body" role="status"><span className="spinner" aria-hidden="true"/>L’agente sta preparando il briefing di oggi…</div>}
          {briefing.status === 'ready' && <div className="briefing-body">
            <p className="briefing-summary"><strong>{briefing.counts.recommend}</strong> da approvare · <strong>{briefing.counts.clarify}</strong> da chiarire · <strong>{briefing.counts.no_action}</strong> senza azione{briefing.counts.errors > 0 && <> · <strong>{briefing.counts.errors}</strong> fallite</>}</p>
            <ul className="briefing-list">{briefing.items.map(i => {const d = i.analysis?.result; const g = i.goal_check?.goal; const c = g?.last_check; return <li key={i.opportunity_id}>
              <div className="briefing-row"><button className="account-button" onClick={() => selectOpportunity(i.opportunity_id)}>{i.account_name}</button>
                {i.why === 'revisit' && <span className="tag">Ricontrollo che l’agente si era programmato</span>}
                {g && <span className="tag">Obiettivo: {g.objective}</span>}
                {i.error ? <span className="status failed">Controllo fallito</span> : c ? <span className={`status ${goalActions[c.action][1]}`}>{goalActions[c.action][0]}</span> : <span className={`status ${d.decision}`}>{labels[d.decision]}</span>}</div>
              <p>{i.error || (c ? c.reason : d.reason)}</p>
              {c?.question && <p className="muted"><strong>Da decidere:</strong> {c.question}</p>}
              {c?.action === 'close' && <p className="muted">Se confermi, segna la Task come completata nella vista Task: l’agente non chiude record nel CRM.</p>}
              {d?.revisit_on && <p className="muted">L’agente ricontrollerà da solo il {d.revisit_on}.</p>}
            </li>;})}</ul>
          </div>}
          {goals.some(g => ['open', 'escalated', 'blocked'].includes(g.status)) && <div className="briefing-body revisits"><h3>Obiettivi seguiti dall’agente</h3><ul>{goals.filter(g => ['open', 'escalated', 'blocked'].includes(g.status)).map(g => <li key={g.id}>
            <span>{opportunities.find(o => o.opportunity_id === g.opportunity_id)?.account_name} · {g.objective} · {goalStatus[g.status]}{g.status === 'open' ? `, prossimo controllo ${g.next_check}` : ''}</span>
            <button className="text-button" onClick={() => post(`goals/${g.id}/cancel`)}>Annulla</button></li>)}</ul></div>}
          {revisits.length > 0 && <div className="briefing-body revisits"><h3>Ricontrolli programmati dall’agente</h3><ul>{revisits.map(r => <li key={r.id}>
            <span>{opportunities.find(o => o.opportunity_id === r.opportunity_id)?.account_name} · {r.due_date}</span>
            <button className="text-button" onClick={() => cancelRevisit(r.id)}>Annulla</button></li>)}</ul></div>}
        </section>}
        {view === 'Oggi' && <section className="chat" aria-label="Assistente">
          <div className="chat-heading"><h2>Assistente</h2><span>{config.mode === 'demo' ? 'Simulazione a parole chiave · nessun LLM' : 'Sola lettura · propone, non agisce'}</span></div>
          <div className="chat-log" aria-live="polite" ref={chatLog}>{messages.map((m, i) => <div key={i} className={`bubble ${m.role}${m.error ? ' failed' : ''}`}>
            <p>{m.content}</p>
            {m.ids?.length > 0 && <><ol className="chat-cards">{m.ids.map(id => {const o = opportunities.find(x => x.opportunity_id === id); return o && <li key={id}><button className="chat-card" onClick={() => selectOpportunity(id)}><strong>{o.account_name}</strong><span>{money(o.amount_eur)} · chiusura {o.close_date}</span><span>{results[id]?.result ? labels[results[id].result.decision] : o.candidate_reasons[0] || o.stage}</span></button></li>;})}</ol>
              <button className="secondary" disabled={!!busy || !config.ready} onClick={() => investigate(m.ids)}>Analizza {m.ids.length === 1 ? 'questa opportunità' : `queste ${m.ids.length}`}</button></>}
          </div>)}</div>
          <div className="chips">{suggestions.map(s => <button key={s} className="chip" disabled={!!busy || !config.ready} onClick={() => ask(s)}>{s}</button>)}</div>
          <form className="chat-input" onSubmit={e => {e.preventDefault(); ask(question);}}>
            <label htmlFor="question" className="visually-hidden">Fai una domanda all'assistente</label>
            <input id="question" value={question} maxLength={1000} placeholder="Es. quali opportunità in Negotiation chiudono prima?" onChange={e => setQuestion(e.target.value)}/>
            <button className="primary" disabled={!!busy || !config.ready || !question.trim()}>Invia</button>
          </form>
        </section>}
        <div className="toolbar"><label className="search-label" htmlFor="search">Cerca un’opportunità<input id="search" type="search" placeholder="Cerca account o fase" value={search} onChange={e => setSearch(e.target.value)}/></label></div>
        <div className="split"><section className="queue" aria-label="Opportunità"><div className="queue-heading"><h2>{view === 'Oggi' ? 'Coda di revisione' : 'Portafoglio opportunità'}</h2><span>{visible.length} record</span></div>
          <div className="table-scroll"><table><thead><tr><th>Account / fase</th><th>Valore</th><th>Segnale</th></tr></thead><tbody>{visible.map(o => <tr key={o.opportunity_id} className={selected === o.opportunity_id ? 'selected' : ''}><td><button className="account-button" onClick={() => selectOpportunity(o.opportunity_id)} aria-pressed={selected === o.opportunity_id}>{o.account_name}</button><span className="subline">{o.stage} · chiusura {o.close_date}</span></td><td className="amount">{money(o.amount_eur)}</td><td>{results[o.opportunity_id]?.error ? <span className="status failed">Analisi fallita</span> : results[o.opportunity_id]?.result ? <span className={`status ${results[o.opportunity_id].result.decision}`}>{labels[results[o.opportunity_id].result.decision]}</span> : <span className="signal">{o.candidate_reasons[0] || 'Task già pianificata'}</span>}</td></tr>)}</tbody></table></div>
          {!visible.length && <div className="empty">Nessuna opportunità corrispondente. Prova un’altra ricerca.</div>}
        </section>
        <section id="selected-opportunity" className="detail" aria-label="Opportunità selezionata">{current && <><div className="detail-heading"><h2>{current.account_name}</h2><p>{current.stage} · {money(current.amount_eur)}</p></div>
          <dl className="facts"><div><dt>Ultima attività registrata</dt><dd>{current.last_activity_date}</dd></div><div><dt>Prossima Task</dt><dd>{current.has_pending_task ? 'Pianificata' : 'Nessuna registrata'}</dd></div></dl>
          <div className="signals">{current.candidate_reasons.map(r => <span key={r}>{r}</span>)}</div>
          <button className="secondary full" disabled={!!busy || !config.ready || !context} onClick={() => investigate([selected])}>{analysis ? 'Analizza di nuovo' : 'Analizza questa opportunità'}</button>
          {analysis?.error && <div className="error" role="alert">{analysis.error}<p>Nessuna Task creata. Correggi la configurazione o riprova.</p></div>}
          {decision && <div className="finding"><div className="finding-title"><h3>{labels[decision.decision]}</h3><span className={`priority ${decision.priority}`}>priorità {{high: 'alta', normal: 'normale', low: 'bassa'}[decision.priority]}</span></div><p>{decision.reason}</p>
            {decision.revisit_on && <p className="question"><strong>Ricontrollo programmato</strong><br/>L’agente rianalizzerà questa opportunità il {decision.revisit_on}, senza che tu debba chiederlo.</p>}
            {decision.question && <p className="question"><strong>{decision.ask_contact ? `Chiedi a ${decision.ask_contact.name} (${decision.ask_contact.role})` : 'Chiarisci con lo stakeholder'}</strong><br/>{decision.question}</p>}
            {decision.task && <div className="task-preview"><h4>{decision.task.title}</h4><p>Scadenza {decision.task.due_date} · assegnata a te</p>{state ? <p className="resolution">{state === 'approved' ? 'Task creata' : 'Proposta archiviata'}</p> : review === analysis.proposal_id ? <div className="approval"><p>Stai approvando esattamente questa Task nel CRM simulato.</p><button className="primary full" disabled={!!busy} onClick={() => approve(analysis)}>Conferma e crea la Task</button><button className="text-button" disabled={!!busy} onClick={() => setReview(null)}>Torna alla revisione</button></div> : <div className="button-row"><button className="primary" disabled={!!busy} onClick={() => setReview(analysis.proposal_id)}>Rivedi la Task</button><button className="text-button" disabled={!!busy} onClick={() => reject(analysis)}>Archivia</button></div>}</div>}
            <h4 className="evidence-label">Evidenze a supporto</h4>{decision.evidence.map(e => <blockquote key={e.note_id}><p>{e.quote}</p><cite>{e.note_id}</cite></blockquote>)}
            <details className="trace"><summary>Attività dei tool e validazione</summary><pre>{JSON.stringify(analysis.trace, null, 2)}</pre></details>
          </div>}
          <details className="raw-notes" open={!decision}><summary>Note CRM · dati di origine non fidati</summary>{context ? context.notes.map(n => <article className="note" key={n.note_id}><p>{n.body}</p><small>{n.note_id} · registrata il {n.created_at}</small></article>) : <p role="status">Caricamento note…</p>}</details>
        </>}</section></div>
      </>}
      {view === 'Task' && <section className="records"><table><thead><tr><th>Task</th><th>Account</th><th>Scadenza</th><th>Approvazione</th><th>Stato</th></tr></thead><tbody>{tasks.map(t => <tr key={t.id}><td>{t.title}</td><td>{opportunities.find(o => o.opportunity_id === t.opportunity_id)?.account_name}</td><td>{t.due_date}</td><td><span className="status no_action">Approvata da te</span></td><td>{t.completed_at ? `Completata il ${t.completed_at}` : <button className="text-button" onClick={() => post(`tasks/${t.id}/complete`, 'Task completata: chiuso anche l’obiettivo collegato.')}>Segna completata</button>}</td></tr>)}</tbody></table>{!tasks.length && <div className="empty"><h2>Ancora nessuna Task approvata</h2><p>Analizza un’opportunità, rivedi la proposta, poi conferma la Task.</p></div>}</section>}
      {view === 'Registro evidenze' && <section className="audit-list">{audit.map(a => <details key={a.id}><summary><strong>{a.event.replaceAll('_',' ')}</strong><span>{new Date(a.created_at).toLocaleString('it-IT')}</span></summary><pre>{JSON.stringify(a.data, null, 2)}</pre></details>)}{!audit.length && <div className="empty">Esegui un’analisi per vedere eventi di tool e validazione.</div>}</section>}
      <footer>Analisi in sola lettura. La creazione di Task richiede la tua approvazione. Nessuna email automatica né cambio di fase nel CRM.<br/>Demo indipendente con stile ispirato a Salesforce Lightning; non è un prodotto Salesforce.</footer>
    </main>
  </div>;
}
