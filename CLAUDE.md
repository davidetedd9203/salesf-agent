# Guida allo sviluppo

Leggi README.md, docs/DECISION_LOG.md e docs/PANEL_WALKTHROUGH.md prima di modificare il comportamento.

## Obiettivo
Progetto per il colloquio Salesforce FDE, per un solo Account Executive. Il panel valuta impostazione del problema, scelte, guardrail e fallimenti osservati. Preferisci una soluzione piccola e ispezionabile all'ampiezza di funzionalità.

## Comandi
Python 3.12+, Node 22+. `pip install -r requirements-dev.txt`; `pytest -q`; `python -m backend.evaluate --mode demo`; `uvicorn backend.main:app --host 127.0.0.1 --port 8000`. Frontend: `cd frontend && npm ci && npm run dev`; verifica di produzione: `npm run build`.

## Invarianti
1. L'owner è scelto lato server dall'identità demo autenticata. Nessun override dell'owner da modello o client.
2. I tool di lettura sono limitati allo snapshot di una sola opportunità dell'owner (con `AGENT_STRATEGY=search|pipeline` anche i contatti del suo account, solo nome e ruolo). Si citano solo note effettivamente restituite al modello. Nessun tool SQL, filesystem o di rete nell'agente.
3. submit_decision non è una scrittura sul CRM. Un endpoint separato di approvazione umana crea esattamente la Task persistita; mai accettare campi arbitrari della Task dal client.
4. Esistenza delle citazioni, schema e deadline esplicita sono controllati lato server. Il supporto semantico richiede comunque evaluation.
5. Controlla scadenza della proposta e snapshot all'approvazione; mantieni idempotenza atomica e protezione dai duplicati.
6. La demo è una simulazione scriptata e va sempre etichettata. Mai fallback silenzioso dalla modalità live.
7. Mai caricare ground_truth.csv nell'agente. L'evaluation è esterna; la simulazione scriptata è orientata alle fixture e non è un benchmark equo del modello.
8. Le note sono non fidate e mostrate come testo semplice. Nessun messaggio o export automatico.
9. Mai fare commit di .env, chiavi, database in var, tracce del provider di clienti reali o node_modules. `.env.example` non deve contenere chiavi.
10. Registra solo eventi osservabili dei tool e il razionale per l'utente, mai il chain-of-thought privato.

## Dove modificare
backend/agent.py: prompt, loop del modello, tool di lettura, validazione e simulazione. backend/chat.py: router della chat (una query tipizzata, nessuna nota, nessuna scrittura). backend/store.py: query limitate e approvazioni. backend/main.py: confini di API e sessione. frontend/app/page.jsx: interazione. data/: fixture originale (non tradurre le note). tests/: regressioni di sicurezza e protocollo. backend/briefing.py: briefing proattivo (selezione deterministica, una volta per data). backend/workflows.py: workflow Temporal opzionale del briefing. backend/account_agent.py: strategie `search` (l'agente sceglie cosa leggere) e `pipeline` (una chiamata con tutto), contesto v3. backend/evaluate.py: etichette ed evaluation.

## Prossimo lavoro, in ordine
Fatto il 12/10/2026: evaluation reale, fallimenti e correzioni in DECISION_LOG.md (F1–F11); `z-ai/glm-5.3` fa 5/5 sulle fixture. Chat v1 fatta (C1–C4 nel DECISION_LOG). Proattività fatta il 13/10/2026 (briefing e `revisit_on`): misurata solo in demo, va rieseguita l'evaluation live di analisi e suite `proactive`. Temporal opzionale per il briefing aggiunto dopo il fallimento misurato T1; asyncio resta il default. Contesto ampio (fixture v3, `--suite scaling`) e contatto da interpellare fatti il 13/10/2026, solo in demo: il confronto pipeline/agente va eseguito con un modello reale prima di dichiarare un vincitore. Ora: confronto con una pipeline fissa a una chiamata; test della chat con un venditore contro tabella e ordinamento; verificare a mano il supporto di ogni citazione. Registra i fallimenti reali invece di inventarli. Aggiungi parafrasi in cieco e casi avversari, incluse richieste valide mescolate a iniezioni, date cambiate, Task esistenti, azioni non supportate e contatti mancanti. Risolvi le incoerenze temporali del dataset in una nuova fixture versionata prima di dichiarare accuratezza temporale. Valida l'utilità con un venditore. Solo dopo considera un adapter per sandbox Salesforce e un'identità di produzione.

Non aggiungere framework di orchestrazione, più agenti, un database vettoriale o integrazioni live senza una limitazione misurata che li giustifichi. Mantieni la data demo fissata per la riproducibilità; le modifiche devono includere fixture e aspettative di evaluation.
