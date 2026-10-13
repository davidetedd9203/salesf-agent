# Walkthrough per il panel — 18–23 minuti

## Il problema, e per chi — 2 minuti

“Mi sono concentrato su un Account Executive che decide quali follow-up fare oggi. L'ipotesi di lavoro è che ricostruire il contesto da record CRM sparsi costi tempo e generi errori di follow-up evitabili. Non ho dimostrato che sia il principale problema del CRM: servirebbe discovery con gli utenti.”

Dichiara l'obiettivo misurabile: ridurre il tempo di revisione mantenendo astensioni ed evidenze corrette. Nessuna promessa di aumento dei ricavi. Un test futuro rappresentativo misurerebbe con utenti reali il tempo mediano di revisione, il tasso di accettazione delle Task, i suggerimenti errati e le richieste azionabili mancate.

## Forma della soluzione — 3 minuti

Le regole selezionano le candidate; un piccolo tool loop legge snapshot dell'opportunità, note e attività, poi raccomanda, chiede chiarimento o si astiene. Il loop ha perimetro di lettura e budget rigidi. Spiega perché una regola rileva l'inattività ma non può capire da sola se l'attesa è intenzionale. Una pipeline di estrazione a passo fisso è un'alternativa seria: va confrontata sperimentalmente prima di aumentare l'autonomia.

Il loop attuale richiede tutte e tre le letture, quindi l'autonomia è modesta. Usare il tool calling non prova che servisse un agente. Dimostra soprattutto esecuzione delimitata e uso delle evidenze; un recupero più adattivo andrebbe giustificato da un contesto più ampio o da risparmi misurati.

## Flusso dal vivo — 5 minuti

Parti da un database pulito. Mostra il badge della modalità. In modalità scriptata dì esplicitamente: “Queste decisioni sono simulate; il flusso di approvazione e validazione è reale.”

Parti dall'**Assistente**: chiedi “Quali opportunità hanno la priorità più alta?”, mostra che dichiara il criterio e propone card, poi clicca “Analizza queste 5”. Fai una richiesta fuori perimetro (“manda un'email ad Acme”) per mostrare il rifiuto. Poi Acme: note sorgente, evidenze, anteprima della Task e approvazione esplicita. Northstar: attesa legittima. BluePeak: scadenza. Orion: conflitto. Helios: iniezione nella nota e superficie dei tool limitata. Apri **Task** e **Registro evidenze**.

Usa il modello reale solo dopo aver configurato e testato quel modello esatto. Se fallisce, mostra errore e traccia invece di passare in silenzio alla simulazione. Se si astiene per il conflitto di date, verifica se è sbagliata l'etichetta.

## Da reattivo a proattivo — 3 minuti

“Un agente che aspetta la domanda è un'interfaccia. Ho reso proattivo chi *avvia* il lavoro, non chi *approva*.” Due pezzi:

- **Briefing del mattino**: il server lo avvia da solo, una volta per data, al massimo cinque analisi. La selezione è deterministica, il riepilogo lo scrive il server dalle decisioni validate: nessun testo libero nuovo.
- **Ricontrollo programmato**: su Northstar il modello decide “aspetta” e indica la data di fine attesa (`revisit_on`), validata come una scadenza. Sposta l'orologio demo al 5/11: il briefing parte dal ricontrollo, trova la nota del 4/11 e propone la demo. Acme e BluePeak diventano chiarimenti: le scadenze sono passate.

Da dire apertamente: in demo è simulato; con il modello reale va ancora misurato. I rischi nuovi sono fatica da notifiche, costo di esecuzioni non richieste e un ricontrollo su un'attesa inesistente. Il passo successivo è un trigger sugli eventi del CRM (nuova nota, email) invece che sull'orario.

## Scelte e alternative scartate — 3 minuti

Rimanda a `DECISION_LOG.md`. Sottolinea orchestrazione Python esplicita, CRM simulato, nessun tool email, nessun lead scoring predittivo, nessun database vettoriale, titoli delle Task scritti dal server e approvazione persistita. Derivano dal rischio e dal perimetro richiesti, non dal voler far sembrare il sistema “agentico”.

## Evaluation e apprendimento — 3 minuti

Mostra `reports/evaluation-demo.json` e chiamalo validazione di UI e fixture: la simulazione conosce i cinque casi, quindi 5/5 è atteso e non dice nulla sulla qualità del modello. La baseline ingenua fa 2/5 ma non è un benchmark competitivo.

Poi i fallimenti reali del 12/10/2026 (`DECISION_LOG.md`, F1–F11): sono la parte più interessante, perché mostrano un ciclo misura → causa → modifica minima.

- Modelli gratuiti: **0/5 accettate**. Un modello scriveva le tool call come testo; un altro saltava le letture o serializzava `task` come stringa.
- GLM 5.3, prima esecuzione: 1/5. Decideva **prima** di leggere e su Acme citava note inventate. Bloccato dalla regola delle letture obbligatorie.
- Tre modifiche, ognuna legata a un fallimento: tool per fasi (non si può decidere senza aver letto), schema senza `$ref` (niente più `task` come stringa), riduzione delle chiamate identiche duplicate.
- Risultato: **5/5 in due esecuzioni consecutive, 0 Task senza approvazione, circa $0.015 a esecuzione**. Su cinque fixture note non prova la generalizzazione: dimostra che il protocollo ora regge.
- Da dire apertamente: i tool per fasi tolgono quasi tutta l'autonomia all'agente, quindi una pipeline fissa diventa l'alternativa ovvia da confrontare.

Chat (C1–C4): il primo tentativo faceva 3/6, con una risposta che citava un ID inventato. Stessa cura applicata alle analisi (tool per fasi, schema e limiti espliciti): 6/6 e 5/6. Il punto da far notare è che il router sceglie solo *quale* query eseguire, mentre l'ordinamento lo fa il server: per “più alto valore” il modello non può sbagliare il calcolo, può solo sbagliare l'interpretazione.

“Una citazione esistente è necessaria, non sufficiente. Devo ancora verificare che sostenga l'azione.”

## Prossima iterazione — 2 minuti

Confronto con una pipeline fissa a una sola chiamata sugli stessi casi; revisione manuale delle citazioni; parafrasi in cieco, date cambiate e richieste legittime mescolate a iniezioni; poi feedback di un venditore. L'adapter per una sandbox Salesforce arriva dopo aver dimostrato utilità e comportamento corretto, con OAuth, mappatura dei permessi e controlli di versione del CRM.

## Domande da preparare

- Perché un agente invece di un'estrazione strutturata? Autonomia modesta oggi; confronto onesto con una pipeline fissa, da tenere se funziona altrettanto bene.
- Cosa succede senza accesso al modello? Modalità simulata esplicita, nessuna pretesa di inferenza reale.
- Il modello può modificare un'opportunità? No. Può solo inviare una proposta; l'approvazione della Task è fuori dal modello.
- La prompt injection è risolta? No. Le capacità sono limitate; il bias semantico va ancora testato.
- Che evidenza hai del valore di business? Un'ipotesi e un piano di evaluation, non uno studio di mercato validato.
- Perché una chat se “più alto valore” è un ordinamento? L'ordinamento resta deterministico; la chat serve a tradurre domande ambigue, spiegare il criterio e combinare filtri. Se con un venditore non fa risparmiare tempo rispetto alla tabella, la si toglie.
- Perché non avete fatto coercizione dei tipi lato server? Perché trasforma output sbagliati in proposte valide senza che il modello abbia dimostrato di capire lo schema; preferiamo che sia il modello a correggersi, una sola volta.
- Perché il briefing non lo sceglie l'LLM? Il triage deterministico ha recall 5/5 sui casi etichettati e un costo prevedibile; l'agentività è nel ricontrollo deciso dal modello. Se le regole perdono casi rilevanti in una misura reale, il triage LLM diventa un esperimento.
- Come scalerebbe? Sessioni e rate limit fuori dalla memoria, identità reale e coda, accesso al CRM partizionato per permessi; solo quando concorrenza e requisiti di produzione lo giustificano. Dettagli in `DECISION_LOG.md`, sezione “Evoluzione dell'architettura”.
