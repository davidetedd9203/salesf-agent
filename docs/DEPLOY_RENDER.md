# Deploy della demo su Render

Una demo online temporanea per il panel: due servizi Docker descritti in `render.yaml`, il backend FastAPI (`sales-copilot-api`) e il frontend Next.js (`sales-copilot`). Il briefing gira in asyncio; Temporal resta una dimostrazione locale.

## Prima di iniziare

- Un account Render collegato a GitHub.
- Il repository `salesf-agent` su GitHub, con `render.yaml` e i Dockerfile aggiornati già pushati.
- Una chiave OpenRouter **dedicata alla demo, con un limite di credito** (OpenRouter → Keys → Create key → Credit limit, per esempio 5 $). Chi conosce URL e password usa quel credito.
- L'ID del modello già verificato, oggi `z-ai/glm-5.3`.

## 1. Pubblica il codice

Render costruisce solo ciò che è su GitHub: committa tutte le modifiche che vuoi mostrare, non solo i file di deploy.

```bash
git status            # .env non deve comparire: è in .gitignore
git add -A
git commit -m "Add Render blueprint for the online demo"
git push
```

Render legge il branch che scegli al punto 2. Se non è `main`, ricordati di selezionarlo.

## 2. Crea il Blueprint

1. Dashboard Render → **New** → **Blueprint**.
2. Seleziona il repository `salesf-agent` e il branch.
3. Render legge `render.yaml` e mostra due servizi: `sales-copilot-api` e `sales-copilot`.
4. Compila le variabili richieste:

| Servizio | Variabile | Valore |
|---|---|---|
| `sales-copilot-api` | `OPENROUTER_API_KEY` | la chiave dedicata |
| `sales-copilot-api` | `OPENROUTER_MODEL` | `z-ai/glm-5.3` |
| `sales-copilot-api` | `APP_ORIGIN` | `https://sales-copilot.onrender.com` |
| `sales-copilot` | `BACKEND_URL` | `https://sales-copilot-api.onrender.com` |

Senza slash finale. Gli URL sono quelli previsti dai nomi dei servizi; se sono già presi, Render ne assegna altri e li correggi al punto 4.

5. **Apply**. La prima build richiede qualche minuto, il frontend più del backend.

## 3. Leggi la password

`sales-copilot-api` → **Environment** → `DEMO_PASSWORD`: è generata da Render. `local-demo` non vale online.

## 4. Controlla gli URL

In alto nella pagina di ciascun servizio c'è l'URL pubblico. Se è diverso da quello inserito:

1. Correggi `APP_ORIGIN` sul backend: si riavvia da solo.
2. Correggi `BACKEND_URL` sul frontend, poi **Manual Deploy → Deploy latest commit**. Il valore entra nella build: senza un nuovo deploy il frontend continua a chiamare il vecchio indirizzo.

## 5. Prova completa

1. `https://<backend>/health` risponde `{"status":"ok"}`.
2. Apri il frontend, entra con la password.
3. In alto il badge mostra il modello reale, non "Demo scriptata".
4. Il briefing del mattino compare entro qualche minuto.
5. Apri l'Assistente e fai una domanda: i passaggi devono comparire uno alla volta, poi la risposta.
6. Analizza Acme, rivedi e conferma la Task: compare nella vista **Task**.

Dopo la prova, riavvia il backend (**Manual Deploy → Restart service**) per ripartire da un database pulito.

## Il giorno del panel

- Il piano gratuito sospende i servizi dopo 15 minuti di inattività; il risveglio richiede circa un minuto. Apri l'app **5–10 minuti prima**: il backend riparte dalla fixture e prepara il briefing del 12/10.
- Un riavvio del backend azzera il database. È il modo più semplice per avere una demo pulita, ma vale anche a metà presentazione: non riavviare durante il panel.
- Se vuoi evitare la sospensione, passa il backend a un piano a pagamento solo per quei giorni (Settings → Instance type).

## Dopo il colloquio

1. Sospendi o elimina i due servizi (Settings → Suspend / Delete).
2. Revoca la chiave OpenRouter dedicata.

## Problemi frequenti

| Sintomo | Causa probabile | Cosa fare |
|---|---|---|
| "Origine della richiesta non consentita" al login | `APP_ORIGIN` diverso dall'URL del frontend | Correggi il valore, senza slash finale |
| "Il backend non è disponibile" | `BACKEND_URL` errato, oppure backend sospeso | Controlla il valore e rifai il deploy del frontend; oppure aspetta un minuto e ricarica |
| Banner "Configurazione OpenRouter incompleta" | Chiave o modello mancanti | Compila le variabili sul backend |
| "Troppi tentativi" al login | Dietro i proxy il limite di 5 tentativi al minuto è condiviso | Aspetta un minuto |
| I passaggi della chat arrivano tutti insieme | Un proxy trattiene lo stream: non verificato su Render | La risposta resta corretta; segnalalo come limite |
| Briefing lento | Latenza del provider: un round può superare i 60 secondi | Aspetta; il briefing compare quando è pronto |
