# Bob — AI Desktop Voice Assistant

Bob is a bilingual (Italian/English) macOS desktop voice assistant with an animated eye interface, smart home integration, and macOS Calendar support.

---

## Features

| Feature | Technology |
|---|---|
| Offline wake word detection | Vosk (local model) |
| Voice command transcription | Whisper via Groq API |
| Intelligent responses (LLM) | Groq API (`openai/gpt-oss-120b`) |
| Bilingual text-to-speech | Microsoft Edge TTS (Diego IT, Guy EN) |
| Animated eye interface | Pygame |
| Long-term memory | Local JSON file |
| Smart light control | TinyTuya (Tuya LAN protocol) |
| macOS Calendar integration | AppleScript via `osascript` |
| Instant speech interruption | Vosk + `pygame.mixer` |

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                        occhi.py                          │
│   ┌──────────────┐   ┌──────────────┐   ┌────────────┐  │
│   │ Vosk (local) │──▶│   Whisper    │──▶│  cervello  │  │
│   │  wake word   │   │  (Groq API)  │   │   (LLM)    │  │
│   └──────────────┘   └──────────────┘   └────────────┘  │
│                                               │          │
│              ┌────────────────────────────────┘          │
│              ▼                                           │
│         ┌─────────┐    ┌──────────┐   ┌──────────────┐  │
│         │  voce   │    │  luci    │   │  calendario  │  │
│         │Edge TTS │    │  Tuya    │   │  AppleScript │  │
│         └─────────┘    └──────────┘   └──────────────┘  │
└──────────────────────────────────────────────────────────┘
```

**Interaction cycle:**
1. Vosk listens in the background → detects the wake word "Bob"
2. Audio is recorded until silence is detected
3. Whisper (Groq) transcribes the command to text
4. `cervello.py` updates memory and generates the LLM response
5. `voce.py` converts the response to speech via Edge TTS
6. Pygame plays the audio and animates the eyes based on current state

---

## Installation

### Prerequisites

- macOS 12+
- Python 3.10+
- [Vosk Italian model](https://alphacephei.com/vosk/models) — download `vosk-model-it-0.22` or similar

### Setup

```bash
# Clone the repository
git clone https://github.com/camicacacee/bob.git
cd bob

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy the memory template
cp memoria.json.example memoria.json

# Download the Vosk model and place its contents in:
# modello_vosk/
```

### Environment variables

Create a `.env` file in the project root:

```env
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxx
```

Or export it directly in the terminal:

```bash
export GROQ_API_KEY="gsk_xxxxxxxxxxxxxxxxxxxxxxxx"
```

### Smart light configuration (optional)

In `luci.py`, replace the placeholder values with your Tuya device credentials:

```python
DEVICE_ID  = "your-device-id"
IP_ADDRESS = "192.168.x.xxx"
LOCAL_KEY  = "your-local-key"
```

---

## Running Bob

```bash
python occhi.py
```

A Pygame window opens showing the animated eyes. Say **"Bob"** to activate.

---

## Voice commands

| Trigger | Behavior |
|---|---|
| `"Bob"` | Activates listening mode |
| `"Stop"` / `"Basta"` / `"Silence"` | Interrupts the current response |
| Any question after the trigger | Bob responds via LLM |

If Bob ends a response with a question (`?`), the microphone stays open automatically — no need to say "Bob" again.

---

## Project structure

```
bob/
├── occhi.py            # Entry point — Pygame interface + audio listen loop
├── cervello.py         # LLM, memory management, Whisper transcription
├── voce.py             # Edge TTS speech synthesis
├── luci.py             # Tuya smart light control
├── calendario.py       # macOS Calendar read/write
├── memoria.json        # Persistent user memory (git-ignored)
├── memoria.json.example
├── requirements.txt
└── modello_vosk/       # Local Vosk model (not included in repo)
```

---

## Dependencies

| Library | Purpose |
|---|---|
| `groq` | Groq API client (Whisper + LLM) |
| `vosk` | Offline speech recognition (wake word) |
| `edge-tts` | Microsoft Neural TTS |
| `pygame` | GUI + audio playback |
| `pyaudio` | Microphone input |
| `numpy` | Volume / silence detection |
| `tinytuya` | Tuya smart home LAN control |

---

## Security & Privacy

- Voice commands are sent to Groq (cloud) **only** after the wake word is detected.
- Wake word detection runs entirely **on-device** with Vosk.
- User memory (`memoria.json`) stays local and is never uploaded.
- Tuya credentials must not be committed — use environment variables or `.env`.

---

## License

MIT
