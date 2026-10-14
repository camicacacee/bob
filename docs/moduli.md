# Module Reference — Bob

Technical reference for all five Python modules that make up Bob.

---

## `occhi.py` — Entry Point & Interface

**Role:** coordinates the audio listen loop and animates the Pygame eye interface.

### State machine

Bob lives in one of four global states, which drive both the eye animation and audio behaviour:

| State | Eye colour | Description |
|---|---|---|
| `IDLE` | Blue | Waiting for wake word; eyes blink randomly |
| `ASCOLTO` | Green | Wake word detected; recording user command |
| `PENSA` | Purple | Audio sent to Whisper + LLM processing |
| `PARLA` | Pulsing purple | Edge TTS audio is playing |

### Global variables

```python
stato_globale: str          # Current state machine state
colore_corrente: tuple      # RGB eye colour
storico_conversazione: list # Last 6 turns (3 user + 3 assistant)
ultima_risposta_bob: str    # Last response text (used to detect trailing "?")
```

### Functions

#### `salva_file_audio(buffer_audio, nome_file) -> str`
Saves a PyAudio chunk buffer as a 16kHz mono 16-bit `.wav` file.

| Parameter | Type | Description |
|---|---|---|
| `buffer_audio` | `list[bytes]` | List of raw audio chunks |
| `nome_file` | `str` | Output file path (default: `temp_cmd.wav`) |

**Returns:** path of the saved file.

#### `ciclo_ascolto()` (daemon thread)
Main audio loop. Reads the microphone in 2000-sample chunks at 16kHz.

Internal logic:
1. **During `PARLA`:** Vosk listens in the background for stop triggers only. On detection, calls `interrompi_voce()` and returns to `IDLE`.
2. **During `IDLE`:** Vosk scans for wake words ("bob", "pop", "bomb", "bop"). On match, transitions to `ASCOLTO`.
3. **During `ASCOLTO`:** Records audio until 16 consecutive silence chunks (`SOGLIA_SILENZIO=800`). Then sends to Whisper, gets the transcript, calls `chiedi_a_bob()`, and starts `parla()`.

#### `disegna_pillola(cx, cy, w, h, colore)`
Draws a pill-shaped eye with a semi-transparent white highlight for depth.

| Parameter | Description |
|---|---|
| `cx, cy` | Centre of the pill |
| `w, h` | Width and height |
| `colore` | RGB tuple |

### Key constants

```python
SOGLIA_SILENZIO     = 800   # Mean amplitude below which a chunk counts as silence
MAX_SILENZIO_CHUNKS = 16    # Consecutive silence chunks before recording ends
TRIGGER_WORDS       = ["bob", "pop", "bomb", "bop"]
TRIGGER_STOP        = ["basta", "stop", "silenzio", "bust", "pasta", "stob"]
```

---

## `cervello.py` — LLM, Memory & Transcription

**Role:** interfaces with the Groq API for both LLM responses and Whisper transcription; manages persistent user memory.

### Configuration

```python
MODEL_NAME   = "openai/gpt-oss-120b"   # LLM model served on Groq
FILE_MEMORIA = "memoria.json"            # Memory file path
```

### Functions

#### `carica_memoria() -> dict`
Reads `memoria.json`. Creates an empty file if it does not exist.

**Returns:** dictionary of known user facts.

---

#### `salva_memoria(nuovi_dati: dict)`
Merges `nuovi_dati` into the existing memory and overwrites the file.

| Parameter | Type | Description |
|---|---|---|
| `nuovi_dati` | `dict` | Key-value pairs to add or update |

---

#### `estrai_e_aggiorna_memoria(testo_utente: str)`
Uses the LLM to extract personal facts from the user's message and persists them.

Keys are **semantic and compound** to avoid collisions (e.g. `pizza_preferita`, `fiore_preferito`). If no facts are found, the LLM returns `{}` and nothing is written.

---

#### `trascrivi_audio(file_path: str) -> str`
Transcribes an audio file using `whisper-large-v3` via Groq.

| Parameter | Type | Description |
|---|---|---|
| `file_path` | `str` | Path to the audio file (`.wav` or `.mp3`) |

**Returns:** transcribed text, or empty string on error.

---

#### `chiedi_a_bob(testo_utente: str, cronologia: list | None) -> str`
Generates Bob's response by combining:
- Long-term memory (from `memoria.json`)
- Short-term conversation history (last 6 messages)
- System prompt with personality rules and operational guidelines

| Parameter | Type | Description |
|---|---|---|
| `testo_utente` | `str` | User command |
| `cronologia` | `list[dict]` | Message list `{"role": ..., "content": ...}` |

**Returns:** Bob's text response.

**Note:** if the response ends with `?`, `occhi.py` keeps the microphone open automatically.

---

## `voce.py` — Speech Synthesis

**Role:** converts text to audio using Microsoft Edge TTS, with automatic language detection.

### Configuration

```python
VOICE_MODEL = "it-IT-DiegoNeural"   # Default Italian voice
```

### Functions

#### `formatta_numeri_per_tts(testo: str) -> str`
Pre-processes text for natural number reading:
- Removes digit separators (including Unicode narrow-space and non-breaking space)
- Formats numbers ≥4 digits with thousands separators (e.g. `1000` → `1.000`)

---

#### `rileva_lingua(testo: str) -> str`
Picks the TTS voice based on the density of common English words in the text.

Threshold: ≥2 English words **or** >25% of tokens → uses `en-US-GuyNeural`; otherwise `it-IT-DiegoNeural`.

---

#### `parla(testo: str)`
Full TTS pipeline:
1. Pre-processes text with `formatta_numeri_per_tts`
2. Detects language with `rileva_lingua`
3. Generates audio with Edge TTS (async → saves to `temp_voice.mp3`)
4. Plays back via `pygame.mixer.music`

---

#### `interrompi_voce()`
Calls `pygame.mixer.music.stop()` if audio is playing. Triggered by stop words.

---

## `luci.py` — Smart Light Control

**Role:** controls a Tuya smart bulb over the local network (LAN, no cloud required).

### Configuration

```python
DEVICE_ID  = "..."   # Tuya device ID
IP_ADDRESS = "..."   # Local IP of the bulb
LOCAL_KEY  = "..."   # Local key (from Tuya / Smart Life app)
```

> **Security:** never commit these values. Use environment variables or a `.env` file.

### Functions

#### `get_lampadina() -> tinytuya.BulbDevice`
Initialises the bulb connection. `set_socketPersistent(False)` closes the socket after each command to prevent hangs.

---

#### `controlla_luce_cami(azione: str, colore: str | None, luminosita: int | None) -> str`

| Parameter | Type | Accepted values |
|---|---|---|
| `azione` | `str` | `"accendi"`, `"spegni"`, `"colore"`, `"luminosita"` |
| `colore` | `str \| None` | `"rosso"`, `"verde"`, `"blu"`, `"bianco"`, `"giallo"`, `"viola"`, `"rosa"`, `"arancione"` |
| `luminosita` | `int \| None` | `0–100` (percentage) |

**Returns:** string describing the result of the operation.

**Brightness mapping:** the percentage value is scaled to the `10–1000` range (native Tuya range).

---

## `calendario.py` — macOS Calendar Integration

**Role:** reads and creates events in macOS Calendar via AppleScript.

> Requires macOS and Calendar access permission in System Settings → Privacy.

### Functions

#### `leggi_eventi_oggi() -> str`
Reads all events in the current day (00:00–23:59) from macOS Calendar.

**Returns:** string listing events as `"Title at HH:MM:SS; ..."`, or `"No events scheduled for today."`.

---

#### `crea_evento(titolo: str, data_ora: str, durata_minuti: int) -> str`

| Parameter | Type | Description |
|---|---|---|
| `titolo` | `str` | Event name |
| `data_ora` | `str` | Format `"YYYY-MM-DD HH:MM"` (e.g. `"2026-09-14 15:30"`) |
| `durata_minuti` | `int` | Duration in minutes (default: 60) |

**Returns:** confirmation string, or error message.

**Note:** events are created in the first available calendar (`calendar 1`).
