# Verifiche eseguite

## 13 ottobre 2026 — proattività

Python 3.14.7, Windows 11. Node non installato su questa macchina.

- `pytest -q`: **39 passati** (31 precedenti + nota versionata e orologio, validazione di `revisit_on`, briefing idempotente e risveglio sul ricontrollo, approvazione rifiutata con scadenza passata, endpoint orologio/briefing/ricontrolli con sessione e Origin).
- `python -m backend.evaluate --suite proactive --mode demo`: 6/6 controlli (simulazione, non benchmark). `--mode demo` analisi 5/5, chat 6/6 invariati.
- Temporal (`temporalio` 1.34.0, server locale dell'SDK): `pytest -q` → **44 passati**, di cui 5 in `tests/test_temporal.py` (misura T1 con asyncio, ripresa senza ripetizioni, retry transitorio, nessun retry su validazione, fallimento visibile a retry esauriti). Backend con `ORCHESTRATOR=temporal` contro un server locale: briefing del 12/10 generato dal workflow all'avvio; spostato l'orologio al 5/11, nuovo workflow che parte dal ricontrollo di Northstar. Senza server raggiungibile l'avvio fallisce con errore.
- Contesto ampio (fixture v3, strategie `search` e `pipeline`): `pytest -q` → **62 passati**, di cui 18 in `tests/test_account.py` (letture limitate, ricerca deterministica, citazione di una nota esistente ma non letta rifiutata, contatto letto e dello stesso account, protocollo mock di search e pipeline, snapshot all'approvazione). `--suite scaling --mode demo`: 5/5 e contatto corretto per entrambe a 10/50/200 note. È una simulazione: il confronto reale non è stato eseguito.
- **Non eseguiti**: `npm run build` e verifica nel browser della UI del briefing (Node assente); evaluation live con OpenRouter dopo la modifica del prompt.

## 12 ottobre 2026 — seconda sessione

Python 3.14.7, Node 24.19.0, Next.js 16.4.0, Windows 11.

- `pytest -q`: 24 passati a metà sessione (aggiunto il test della correzione singola).
- `npm run build`: build di produzione completata.
- Flusso end-to-end via API attraverso il proxy Next (`http://localhost:3000/api`), backend in modalità demo: password errata rifiutata; POST da origine diversa bloccata (CSRF); analisi delle cinque candidate con razionale e titoli in italiano; approvazione di Orion (`clarify`) rifiutata; payload con campi extra rifiutato; approvazione di Acme ripetuta due volte → una sola Task; audit con `analysis_completed` e `task_approved`. La UI tradotta non è stata percorsa con clic in un browser in questa sessione.
- `python -m backend.evaluate --mode demo`: 5/5, baseline 2/5, nessuna Task automatica. Verifica di fixture, **non** qualità del modello.
- Evaluation con modelli reali OpenRouter (free tier): **0/5 proposte accettate per ogni modello, 0 Task senza approvazione**. Dettagli e cause in `docs/DECISION_LOG.md`, F1–F7. Report: `live-evaluation-run1.json` (404, `openrouter/free`), `live-nvidia_nemotron-3-ultra-550b-a55b_free.json`, `live-google_gemma-4-31b-it_free.json`, `live-nemotron-super-run1..3.json` (run3 contiene le tracce complete).
- Con credito a pagamento, `z-ai/glm-5.3`: esecuzione 1 → 1/5 (decisioni prima delle letture, note inventate); esecuzione 2, con tool per fasi e schema inline → 1/5 (`submit_decision` duplicati); esecuzioni 3 e 4, con riduzione dei duplicati → **5/5 e 5/5**, 0 Task senza approvazione, $0.014–0.015 a esecuzione. Report `live-glm-5.3-run1..4.json`. Spesa totale $0.074.
- `pytest -q` dopo queste modifiche: 25 passati.
- Chat (v1): `pytest -q` → **31 passati** (ordinamenti deterministici e limitati all'owner, rifiuti in demo, solo ID restituiti dal tool, ruoli `system` rifiutati, sessione e Origin obbligatori). Suite chat in demo 6/6 (simulazione a parole chiave, non un benchmark). Con `z-ai/glm-5.3`: 3/6, 5/6, 3/6, poi **6/6 e 5/6** dopo le correzioni C1–C3; 0 Task. Dettagli in `docs/DECISION_LOG.md`.
- Browser (Chrome headless, frontend di produzione, backend demo): domanda suggerita → card → “Analizza queste 5” → stato aggiornato sulle card; nessun overflow orizzontale. Server chiusi a fine verifica.
- Osservazione minore: la prima approvazione restituisce anche il campo `kind`, la ripetizione idempotente restituisce la riga del database senza `kind`. Nessun impatto sulla UI.

## 12 ottobre 2026 — prima sessione

Python 3.12.14, Node 24.19.0, Next.js 16.4.0.

- `pytest -q`: 23 passati. Autenticazione, CSRF, confini owner, allowlist dei tool, validazione dell'output, citazioni esatte, validazione delle date, approvazioni obsolete/scadute, scritture duplicate, protocollo OpenRouter simulato ed errori del provider.
- Browser end-to-end sul frontend di produzione e processo FastAPI reale: login; analisi dei cinque casi; revisione e approvazione della Task Acme; Task visibile; chiarimento Orion e astensione Helios/Northstar.
- Screenshot desktop 1440px e mobile 390px (UI allora in inglese). Nessun overflow orizzontale né errori JavaScript.
- Dockerfile e Compose inclusi; build delle immagini **non** eseguita.

## Note di integrazione

Il proxy di Next ha un timeout predefinito di 30 secondi; `experimental.proxyTimeout` è impostato a 500 secondi per cinque analisi sequenziali. Nessun batch reale da 450 secondi è stato provato.

Starlette segnala che il test client basato su HTTPX è deprecato. È un avviso degli strumenti; i test passano.

## Ancora necessario prima di parlare di qualità del prodotto

Esecuzione con un modello fissato e affidabile, giudizio umano sul supporto semantico delle evidenze, varianti in cieco e avversarie, discovery con utenti, misura di falsi positivi/negativi rappresentativi e test di permessi su un'integrazione Salesforce.
