# Bob — AI Desktop Voice Assistant

Bob è un assistente vocale desktop per macOS, bilingue (italiano/inglese), con interfaccia grafica animata e integrazione con dispositivi smart home e calendario.

---

## Funzionalità

| Funzionalità | Tecnologia |
|---|---|
| Wake word detection offline | Vosk (modello locale) |
| Trascrizione comandi vocali | Whisper via Groq API |
| Risposta intelligente (LLM) | Groq API (`openai/gpt-oss-120b`) |
| Sintesi vocale bilingue | Microsoft Edge TTS (Diego IT, Guy EN) |
| Interfaccia "occhi" animata | Pygame |
| Memoria a lungo termine | JSON locale |
| Controllo luci smart | TinyTuya (protocollo Tuya) |
| Calendario macOS | AppleScript via `osascript` |
| Interruzione vocale istantanea | Vosk + `pygame.mixer` |

---

## Architettura

```
┌──────────────────────────────────────────────────────────┐
│                        occhi.py                          │
│   ┌──────────────┐   ┌──────────────┐   ┌────────────┐  │
│   │  Vosk (local)│──▶│   Whisper    │──▶│  cervello  │  │
│   │  wake word   │   │  (Groq API)  │   │  (LLM)     │  │
│   └──────────────┘   └──────────────┘   └────────────┘  │
│                                               │          │
│              ┌────────────────────────────────┘          │
│              ▼                                           │
│         ┌─────────┐    ┌──────────┐   ┌──────────────┐  │
│         │  voce   │    │  luci   │   │  calendario  │  │
│         │ Edge TTS│    │  Tuya   │   │  AppleScript │  │
│         └─────────┘    └──────────┘   └──────────────┘  │
└──────────────────────────────────────────────────────────┘
```

**Ciclo di una interazione:**
1. Vosk ascolta in background → rileva la wake word "Bob"
2. L'audio viene registrato fino al silenzio
3. Whisper (Groq) trascrive il comando in testo
4. `cervello.py` aggiorna la memoria e genera la risposta LLM
5. `voce.py` converte la risposta in audio con Edge TTS
6. Pygame riproduce l'audio e anima gli occhi in base allo stato

---

## Installazione

### Prerequisiti

- macOS 12+
- Python 3.10+
- [Modello Vosk italiano](https://alphacephei.com/vosk/models) (scarica `vosk-model-it-0.22` o simile)

### Setup

```bash
# Clona il repository
git clone https://github.com/tuo-username/bob.git
cd bob

# Crea un ambiente virtuale
python3 -m venv venv
source venv/bin/activate

# Installa le dipendenze
pip install -r requirements.txt

# Copia il file di memoria di esempio
cp memoria.json.example memoria.json

# Scarica il modello Vosk e rinominalo
# Metti i file del modello nella cartella: modello_vosk/
```

### Variabili d'ambiente

Crea un file `.env` nella root del progetto:

```env
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxx
```

Oppure esportala direttamente nel terminale:

```bash
export GROQ_API_KEY="gsk_xxxxxxxxxxxxxxxxxxxxxxxx"
```

### Configurazione luci (opzionale)

In `luci.py`, sostituisci i valori con i dati del tuo dispositivo Tuya:

```python
DEVICE_ID   = "il-tuo-device-id"
IP_ADDRESS  = "192.168.x.xxx"
LOCAL_KEY   = "la-tua-chiave-locale"
```

---

## Avvio

```bash
python occhi.py
```

La finestra di Pygame si apre con gli occhi animati. Pronuncia **"Bob"** per attivarlo.

---

## Comandi vocali

| Trigger | Comportamento |
|---|---|
| `"Bob"` | Attiva l'ascolto |
| `"Stop"` / `"Basta"` / `"Silenzio"` | Interrompe la risposta in corso |
| Qualsiasi domanda dopo il trigger | Bob risponde via LLM |

Se Bob pone una domanda (risposta che termina con `?`), il microfono rimane aperto automaticamente senza necessità di dire di nuovo "Bob".

---

## Struttura del progetto

```
bob/
├── occhi.py           # Entry point — interfaccia Pygame + ciclo ascolto
├── cervello.py        # LLM, memoria, trascrizione Whisper
├── voce.py            # Sintesi vocale Edge TTS
├── luci.py            # Controllo lampadina Tuya
├── calendario.py      # Lettura/creazione eventi macOS Calendar
├── memoria.json       # Memoria persistente utente (ignorata da git)
├── memoria.json.example
├── requirements.txt
└── modello_vosk/      # Modello Vosk locale (non incluso nel repo)
```

---

## Dipendenze

Vedi [`requirements.txt`](requirements.txt).

| Libreria | Uso |
|---|---|
| `groq` | Client Groq API (Whisper + LLM) |
| `vosk` | Riconoscimento vocale offline (wake word) |
| `edge-tts` | Sintesi vocale Microsoft Neural |
| `pygame` | Interfaccia grafica + riproduzione audio |
| `pyaudio` | Acquisizione microfono |
| `numpy` | Rilevamento volume/silenzio |
| `tinytuya` | Controllo dispositivi smart home Tuya |

---

## Sicurezza e Privacy

- I comandi vocali vengono inviati a Groq (cloud) solo dopo l'attivazione della wake word.
- La wake word è elaborata interamente **in locale** con Vosk.
- La memoria utente (`memoria.json`) è locale e non viene mai caricata su cloud.
- Le credenziali Tuya non devono essere committate — usare `.env` o variabili d'ambiente.

---

## Licenza

MIT
