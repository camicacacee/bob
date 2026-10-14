# Documentazione Moduli — Bob

Riferimento tecnico dei cinque moduli Python che compongono Bob.

---

## `occhi.py` — Entry point e interfaccia

**Ruolo:** coordina il ciclo di ascolto vocale e anima l'interfaccia grafica Pygame.

### Macchina a stati

Bob vive in uno di quattro stati globali, che cambiano sia l'animazione degli occhi che il comportamento audio:

| Stato | Colore occhi | Descrizione |
|---|---|---|
| `IDLE` | Azzurro | Attesa della wake word, occhi che battono casualmente |
| `ASCOLTO` | Verde | Wake word rilevata, sta registrando il comando |
| `PENSA` | Viola | Audio inviato a Whisper + LLM in elaborazione |
| `PARLA` | Viola pulsante | Edge TTS in riproduzione |

### Variabili globali

```python
stato_globale: str          # Stato corrente della macchina a stati
colore_corrente: tuple      # RGB colore occhi
storico_conversazione: list # Ultimi 6 turni (3 user + 3 assistant)
ultima_risposta_bob: str    # Testo ultima risposta (per rilevare "?")
```

### Funzioni

#### `salva_file_audio(buffer_audio, nome_file) -> str`
Salva un buffer di chunk PyAudio come file `.wav` a 16kHz mono 16-bit.

| Parametro | Tipo | Descrizione |
|---|---|---|
| `buffer_audio` | `list[bytes]` | Lista di chunk audio raw |
| `nome_file` | `str` | Percorso del file di output (default: `temp_cmd.wav`) |

**Ritorna:** percorso del file salvato.

#### `ciclo_ascolto()` (thread daemon)
Loop principale audio. Legge il microfono a chunk da 2000 campioni a 16kHz.

Logica interna:
1. **Durante `PARLA`:** Vosk ascolta in sottofondo solo per i trigger di stop. Se rileva "stop/basta/silenzio", chiama `interrompi_voce()` e torna a `IDLE`.
2. **Durante `IDLE`:** Vosk cerca la wake word ("bob", "pop", "bomb", "bop"). Quando la trova, passa ad `ASCOLTO`.
3. **Durante `ASCOLTO`:** Registra audio fino a 16 chunk di silenzio consecutivi (`SOGLIA_SILENZIO=800`). Poi manda a Whisper, ottiene il testo, chiama `chiedi_a_bob()`, e avvia `parla()`.

#### `disegna_pillola(cx, cy, w, h, colore)`
Disegna un occhio a forma di pillola con effetto luce (highlight bianco semi-trasparente).

| Parametro | Descrizione |
|---|---|
| `cx, cy` | Centro della pillola |
| `w, h` | Larghezza e altezza |
| `colore` | Tupla RGB |

### Costanti rilevanti

```python
SOGLIA_SILENZIO     = 800   # Ampiezza media sotto cui un chunk è "silenzio"
MAX_SILENZIO_CHUNKS = 16    # Chunk di silenzio consecutivi per terminare la registrazione
TRIGGER_WORDS       = ["bob", "pop", "bomb", "bop"]
TRIGGER_STOP        = ["basta", "stop", "silenzio", "bust", "pasta", "stob"]
```

---

## `cervello.py` — LLM, Memoria, Trascrizione

**Ruolo:** interfaccia con Groq API per LLM e Whisper, gestione della memoria persistente.

### Configurazione

```python
MODEL_NAME   = "openai/gpt-oss-120b"   # Modello LLM su Groq
FILE_MEMORIA = "memoria.json"            # Path del file memoria
```

### Funzioni

#### `carica_memoria() -> dict`
Legge `memoria.json`. Se il file non esiste, lo crea vuoto.

**Ritorna:** dizionario con i fatti noti sull'utente.

---

#### `salva_memoria(nuovi_dati: dict)`
Effettua un merge tra la memoria esistente e `nuovi_dati`, poi sovrascrive il file.

| Parametro | Tipo | Descrizione |
|---|---|---|
| `nuovi_dati` | `dict` | Coppie chiave-valore da aggiungere/aggiornare |

---

#### `estrai_e_aggiorna_memoria(testo_utente: str)`
Usa il LLM per estrarre fatti personali dal messaggio dell'utente e li salva in memoria.

Le chiavi generate sono **semantiche e composte** per evitare collisioni (es. `pizza_preferita`, `fiore_preferito`). Se non ci sono fatti da salvare, il LLM restituisce `{}` e non viene scritto nulla.

---

#### `trascrivi_audio(file_path: str) -> str`
Trascrive un file audio usando `whisper-large-v3` via Groq.

| Parametro | Tipo | Descrizione |
|---|---|---|
| `file_path` | `str` | Percorso del file audio (`.wav` o `.mp3`) |

**Ritorna:** testo trascritto, stringa vuota in caso di errore.

---

#### `chiedi_a_bob(testo_utente: str, cronologia: list | None) -> str`
Genera la risposta di Bob integrando:
- memoria a lungo termine (da `memoria.json`)
- cronologia conversazione a breve termine (ultimi 6 messaggi)
- system prompt con personalità e regole operative

| Parametro | Tipo | Descrizione |
|---|---|---|
| `testo_utente` | `str` | Comando dell'utente |
| `cronologia` | `list[dict]` | Lista di messaggi `{"role": ..., "content": ...}` |

**Ritorna:** risposta testuale di Bob.

**Nota:** se la risposta termina con `?`, `occhi.py` mantiene aperto il microfono automaticamente (senza richiedere wake word).

---

## `voce.py` — Sintesi Vocale

**Ruolo:** converte testo in audio con Microsoft Edge TTS, con rilevamento automatico della lingua.

### Configurazione

```python
VOICE_MODEL = "it-IT-DiegoNeural"   # Voce italiana di default
```

### Funzioni

#### `formatta_numeri_per_tts(testo: str) -> str`
Pre-processa il testo per una lettura naturale dei numeri:
- Rimuove spazi separatori tra cifre (inclusi Unicode ` `, ` `)
- Formatta numeri ≥4 cifre con il punto delle migliaia (es. `1000` → `1.000`)

---

#### `rileva_lingua(testo: str) -> str`
Determina la voce TTS in base alla densità di parole inglesi comuni nel testo.

Soglia: ≥2 parole inglesi **oppure** >25% del testo → usa `en-US-GuyNeural`, altrimenti `it-IT-DiegoNeural`.

---

#### `parla(testo: str)`
Pipeline TTS completa:
1. Pre-processa il testo con `formatta_numeri_per_tts`
2. Rileva la lingua con `rileva_lingua`
3. Genera l'audio con Edge TTS (async → salva in `temp_voice.mp3`)
4. Riproduce via `pygame.mixer.music`

---

#### `interrompi_voce()`
Chiama `pygame.mixer.music.stop()` se l'audio è in riproduzione. Usata dal trigger "stop".

---

## `luci.py` — Controllo Luci Smart

**Ruolo:** controlla una lampadina Tuya tramite il protocollo locale (LAN, senza cloud).

### Configurazione

```python
DEVICE_ID = "..."        # ID dispositivo Tuya
IP_ADDRESS = "..."       # IP locale della lampadina
LOCAL_KEY  = "..."       # Chiave locale Tuya (da app Tuya/Smart Life)
```

> **Sicurezza:** non committare mai questi valori. Usare variabili d'ambiente o un file `.env`.

### Funzioni

#### `get_lampadina() -> tinytuya.BulbDevice`
Inizializza la connessione alla lampadina. `set_socketPersistent(False)` chiude il socket dopo ogni comando per evitare blocchi.

---

#### `controlla_luce_cami(azione: str, colore: str | None, luminosita: int | None) -> str`

| Parametro | Tipo | Valori accettati |
|---|---|---|
| `azione` | `str` | `"accendi"`, `"spegni"`, `"colore"`, `"luminosita"` |
| `colore` | `str \| None` | `"rosso"`, `"verde"`, `"blu"`, `"bianco"`, `"giallo"`, `"viola"`, `"rosa"`, `"arancione"` |
| `luminosita` | `int \| None` | `0–100` (percentuale) |

**Ritorna:** stringa descrittiva del risultato dell'operazione.

**Mapping luminosità:** il valore percentuale viene scalato su range `10–1000` (range nativo Tuya).

---

## `calendario.py` — Integrazione macOS Calendar

**Ruolo:** legge e crea eventi nel calendario macOS tramite AppleScript.

> Richiede macOS e i permessi di accesso a "Calendario" nelle impostazioni Privacy.

### Funzioni

#### `leggi_eventi_oggi() -> str`
Legge tutti gli eventi nella giornata corrente (00:00–23:59) dal calendario macOS.

**Ritorna:** stringa con elenco eventi nel formato `"Titolo alle HH:MM:SS; ..."`, oppure `"Nessun impegno in programma per oggi."`.

---

#### `crea_evento(titolo: str, data_ora: str, durata_minuti: int) -> str`

| Parametro | Tipo | Descrizione |
|---|---|---|
| `titolo` | `str` | Nome dell'evento |
| `data_ora` | `str` | Formato `"YYYY-MM-DD HH:MM"` (es. `"2026-09-14 15:30"`) |
| `durata_minuti` | `int` | Durata in minuti (default: 60) |

**Ritorna:** conferma testuale dell'evento creato, oppure messaggio di errore.

**Nota:** gli eventi vengono creati nel primo calendario disponibile (`calendar 1`).
