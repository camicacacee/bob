"""
occhi.py — Bob's eyes: Pygame interface and main audio listen loop.

Entry point for the assistant. Spawns a daemon thread that continuously
listens for the wake word, records commands, and drives the LLM pipeline.
The main thread runs the Pygame event loop, animating two pill-shaped eyes
whose colour and shape reflect Bob's current state.

State machine
-------------
IDLE    → waiting for wake word; eyes blink and glance randomly (blue)
ASCOLTO → wake word detected; recording user command (green)
PENSA   → audio sent to Whisper + LLM in progress (purple)
PARLA   → Edge TTS audio playing; eyes pulse with the speech rhythm (purple)
"""

import warnings
warnings.filterwarnings("ignore")

import pyaudio
import pygame
import sys
import math
import random
import threading
import json
import os
import wave
import numpy as np
from collections import deque
from vosk import Model, KaldiRecognizer

from cervello import chiedi_a_bob, trascrivi_audio
from voce import parla, interrompi_voce

# ---------------------------------------------------------------------------
# Pygame initialisation
# ---------------------------------------------------------------------------

pygame.init()

LARGHEZZA, ALTEZZA = 320, 240
schermo = pygame.display.set_mode((LARGHEZZA, ALTEZZA))
pygame.display.set_caption("Bob - Cognitive System")
clock = pygame.time.Clock()

# Colour palette used for the eye animations.
NERO   = (15,  15,  25)   # Background
AZZURRO = (0,  200, 255)  # IDLE state
VERDE  = (0,  255, 150)   # ASCOLTO state
VIOLA  = (200, 50, 255)   # PENSA / PARLA state

# Eye geometry constants.
OCC_W, OCC_H, OCC_R = 70, 110, 35       # Width, height, corner radius
CENTRO_SX_X, CENTRO_SX_Y = 100, 120     # Left eye centre
CENTRO_DX_X, CENTRO_DX_Y = 220, 120     # Right eye centre

# ---------------------------------------------------------------------------
# Global state shared between the audio thread and the Pygame main thread
# ---------------------------------------------------------------------------

stato_globale = "IDLE"          # Current state machine state
colore_corrente = AZZURRO       # Current eye colour (mirrors stato_globale)
storico_conversazione = []      # Short-term memory: last 6 turns
ultima_risposta_bob = ""        # Last response text (used to detect trailing "?")


# ---------------------------------------------------------------------------
# Audio utilities
# ---------------------------------------------------------------------------

def salva_file_audio(buffer_audio, nome_file="temp_cmd.wav"):
    """Write a list of raw PyAudio chunks to a WAV file (16kHz, mono, 16-bit).

    Args:
        buffer_audio (list[bytes]): Recorded audio chunks from PyAudio.
        nome_file (str): Destination file path.

    Returns:
        str: Path of the written WAV file.
    """
    wf = wave.open(nome_file, 'wb')
    wf.setnchannels(1)
    wf.setsampwidth(2)   # 16-bit = 2 bytes per sample
    wf.setframerate(16000)
    wf.writeframes(b''.join(buffer_audio))
    wf.close()
    return nome_file


# ---------------------------------------------------------------------------
# Main audio listen loop (runs in a daemon thread)
# ---------------------------------------------------------------------------

def ciclo_ascolto():
    """Continuously listen for the wake word, record commands, and respond.

    Three-phase loop:
    1. PARLA phase  — listen only for stop triggers while Bob is speaking.
    2. IDLE phase   — scan the audio stream for the wake word using Vosk.
    3. ASCOLTO phase — record until silence, then transcribe and respond.

    The function runs indefinitely; it is started as a daemon thread so it
    exits automatically when the main Pygame thread closes.
    """
    global stato_globale, colore_corrente, storico_conversazione, ultima_risposta_bob

    print("\n[LOADING] Starting speech engine...")
    modello_vosk = Model("modello_vosk")
    recognizer_vosk = KaldiRecognizer(modello_vosk, 16000)

    CHUNK = 2000  # Samples per read — ~125ms at 16kHz
    pa = pyaudio.PyAudio()
    mic_stream = pa.open(
        rate=16000, channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=CHUNK,
    )

    # Rolling pre-buffer so audio just before the wake word is captured too.
    buffer_storico = deque(maxlen=8)
    in_registrazione = False
    buffer_registrazione = []
    silenzi_consecutivi = 0

    # Chunks with mean amplitude below this threshold count as silence.
    SOGLIA_SILENZIO = 800
    # How many consecutive silence chunks end the recording.
    MAX_SILENZIO_CHUNKS = 16

    # Vosk may transcribe "Bob" differently depending on the acoustic model
    # (English or Italian) and microphone conditions. The list is intentionally
    # broad to catch common phonetic confusions.
    TRIGGER_WORDS = ["bob", "pop", "bomb", "bop", "bot", "boh", "ob", "bog", "bok", "bob's", "pob"]

    # Similarly broadened to catch stop-word confusions in live audio.
    TRIGGER_STOP = ["basta", "stop", "silenzio", "bust", "pasta", "stob"]

    print("\n[BOB READY] Say 'Bob' to start, or 'Stop' to interrupt.")
    print("[DEBUG] Vosk will print what it hears in idle mode — check if 'bob' appears.")

    try:
        while True:
            audio_raw = mic_stream.read(CHUNK, exception_on_overflow=False)

            # ------------------------------------------------------------------
            # Phase 1 — PARLA: listen for stop triggers while Bob speaks
            # ------------------------------------------------------------------
            if stato_globale == "PARLA":
                if recognizer_vosk.AcceptWaveform(audio_raw):
                    res = json.loads(recognizer_vosk.Result())
                    testo_parziale = res.get("text", "")
                else:
                    res = json.loads(recognizer_vosk.PartialResult())
                    testo_parziale = res.get("partial", "")

                testo_analizzato = testo_parziale.lower()

                if testo_analizzato.strip():
                    print(f"\r[BACKGROUND LISTEN]: {testo_analizzato}", end="")

                if any(w in testo_analizzato for w in TRIGGER_STOP):
                    print(f"\n\n[STOP TRIGGERED — '{testo_analizzato}'] Interrupting Bob...")
                    interrompi_voce()
                    stato_globale = "IDLE"
                    colore_corrente = AZZURRO
                    in_registrazione = False
                    buffer_storico.clear()
                    buffer_registrazione.clear()
                    recognizer_vosk.Reset()

                    # Flush the mic buffer to eliminate echo from Bob's own speaker.
                    if mic_stream.get_read_available() > 0:
                        mic_stream.read(mic_stream.get_read_available(), exception_on_overflow=False)
                    continue

                # TTS audio finished normally — decide next state.
                if not pygame.mixer.music.get_busy():
                    print("")
                    if ultima_risposta_bob.strip().endswith("?"):
                        # Bob asked a question: keep mic open without requiring wake word.
                        print("[QUESTION DETECTED] Mic stays open for reply...")
                        stato_globale = "ASCOLTO"
                        colore_corrente = VERDE
                        in_registrazione = True
                    else:
                        stato_globale = "IDLE"
                        colore_corrente = AZZURRO
                        in_registrazione = False

                    buffer_storico.clear()
                    buffer_registrazione.clear()
                    silenzi_consecutivi = 0
                    recognizer_vosk.Reset()
                continue

            # ------------------------------------------------------------------
            # Phase 2 — IDLE: scan for wake word
            # ------------------------------------------------------------------
            if not in_registrazione:
                buffer_storico.append(audio_raw)

                if recognizer_vosk.AcceptWaveform(audio_raw):
                    testo_parziale = json.loads(recognizer_vosk.Result()).get("text", "")
                else:
                    testo_parziale = json.loads(recognizer_vosk.PartialResult()).get("partial", "")

                # Print every non-empty transcript so the user can see what
                # Vosk is hearing and add the correct variant to TRIGGER_WORDS.
                if testo_parziale.strip():
                    print(f"\r[VOSK IDLE]: {testo_parziale.strip():<40}", end="", flush=True)

                if any(w in testo_parziale.lower() for w in TRIGGER_WORDS):
                    print(f"\n[WAKE WORD] Listening...")
                    stato_globale = "ASCOLTO"
                    colore_corrente = VERDE

                    # Seed the recording buffer with pre-wake audio so the
                    # command word itself is not clipped.
                    in_registrazione = True
                    buffer_registrazione = list(buffer_storico)
                    silenzi_consecutivi = 0
                    recognizer_vosk.Reset()

            # ------------------------------------------------------------------
            # Phase 3 — ASCOLTO: record until silence, then process
            # ------------------------------------------------------------------
            else:
                buffer_registrazione.append(audio_raw)
                audio_np = np.frombuffer(audio_raw, dtype=np.int16)
                volume = np.abs(audio_np).mean()

                if volume < SOGLIA_SILENZIO:
                    silenzi_consecutivi += 1
                else:
                    silenzi_consecutivi = 0  # Reset on any non-silent chunk

                if silenzi_consecutivi > MAX_SILENZIO_CHUNKS:
                    # Enough silence — treat the buffer as a complete command.
                    mic_stream.stop_stream()

                    percorso_wav = salva_file_audio(buffer_registrazione)
                    print("[PROCESSING WITH WHISPER...]")
                    comando = trascrivi_audio(percorso_wav).lower()

                    # Strip the wake word from the transcript to avoid it
                    # appearing in the text sent to the LLM.
                    for trigger in TRIGGER_WORDS:
                        comando = comando.replace(trigger, "").strip()

                    if comando:
                        print(f"[COMMAND]: '{comando}'")
                        stato_globale = "PENSA"
                        colore_corrente = VIOLA

                        # Append to history and get Bob's response.
                        storico_conversazione.append({"role": "user", "content": comando})
                        ultima_risposta_bob = chiedi_a_bob(comando, cronologia=storico_conversazione)
                        print(f"[BOB]: {ultima_risposta_bob}")
                        storico_conversazione.append({"role": "assistant", "content": ultima_risposta_bob})

                        # Keep history bounded to the last 6 messages (3 turns).
                        if len(storico_conversazione) > 6:
                            storico_conversazione = storico_conversazione[-6:]

                        # Flush residual mic audio before starting TTS playback
                        # to prevent the microphone from picking up Bob's own voice.
                        if mic_stream.get_read_available() > 0:
                            mic_stream.read(mic_stream.get_read_available(), exception_on_overflow=False)
                        recognizer_vosk.Reset()

                        stato_globale = "PARLA"
                        parla(ultima_risposta_bob)
                    else:
                        # Empty transcript — nothing to act on.
                        stato_globale = "IDLE"
                        colore_corrente = AZZURRO

                    # Clean up temporary WAV file.
                    if os.path.exists(percorso_wav):
                        os.remove(percorso_wav)

                    in_registrazione = False
                    buffer_storico.clear()
                    buffer_registrazione.clear()
                    recognizer_vosk.Reset()
                    mic_stream.start_stream()

    finally:
        mic_stream.close()
        pa.terminate()


# Start the audio loop as a daemon thread so it exits when the Pygame window closes.
threading.Thread(target=ciclo_ascolto, daemon=True).start()


# ---------------------------------------------------------------------------
# Pygame animation — eye rendering
# ---------------------------------------------------------------------------

# Smooth interpolation state for eye movement and blinking.
offset_x, offset_y = 0, 0               # Current gaze offset
target_offset_x, target_offset_y = 0, 0 # Target gaze offset
scala_h, target_scala_h = 1.0, 1.0      # Current / target vertical eye scale

# Timers for random blink and gaze events (milliseconds since pygame.init()).
timer_blink = pygame.time.get_ticks() + random.randint(2000, 4000)
timer_sguardo = pygame.time.get_ticks() + random.randint(1500, 3000)


def disegna_pillola(cx, cy, w, h, colore):
    """Draw one pill-shaped eye with a soft white highlight for depth.

    Skips rendering if the eye is too small to be visible (avoids drawing
    artefacts when the eye is nearly closed during a blink).

    Args:
        cx (float): Horizontal centre of the pill.
        cy (float): Vertical centre of the pill.
        w (float): Width of the pill.
        h (float): Height of the pill (can be very small during blinks).
        colore (tuple): RGB colour for the main pill body.
    """
    if h < 4 or w < 4:
        return

    rect = pygame.Rect(int(cx - w / 2), int(cy - h / 2), int(w), int(h))
    pygame.draw.rect(schermo, colore, rect, border_radius=min(OCC_R, h // 2, w // 2))

    # Draw a semi-transparent white oval near the top of the pill to simulate
    # a light reflection, giving the eye a glossy look.
    if h > 20:
        rl_surf = pygame.Surface(
            (max(6, int(w * 0.82)), max(6, int(h * 0.32))),
            pygame.SRCALPHA,
        )
        pygame.draw.rect(
            rl_surf,
            (255, 255, 255, 55),
            (0, 0, rl_surf.get_width(), rl_surf.get_height()),
            border_radius=min(rl_surf.get_height() // 2, rl_surf.get_width() // 2),
        )
        schermo.blit(rl_surf, (int(cx - rl_surf.get_width() / 2), rect.top + int(h * 0.07)))


# ---------------------------------------------------------------------------
# Main Pygame loop
# ---------------------------------------------------------------------------

while True:
    t = pygame.time.get_ticks()

    for evento in pygame.event.get():
        if evento.type == pygame.QUIT:
            pygame.quit()
            sys.exit()

    # Update animation targets based on the current state.
    if stato_globale == "IDLE":
        # Trigger a blink when the timer fires, then schedule the next one.
        if t > timer_blink:
            target_scala_h = 0.05  # Nearly close the eyes
            if scala_h <= 0.12:    # Eyes are nearly shut — schedule re-open
                timer_blink = t + random.randint(2500, 5000)
                target_scala_h = 1.0

        # Shift gaze to a random direction every few seconds.
        if t > timer_sguardo:
            target_offset_x = random.choice([-18, -9, 0, 0, 9, 18])
            target_offset_y = random.choice([-8, 0, 0, 8])
            timer_sguardo = t + random.randint(1500, 3500)

    elif stato_globale == "ASCOLTO":
        # Wide-open eyes centred on the user.
        target_scala_h, target_offset_x, target_offset_y = 1.2, 0, 0

    elif stato_globale == "PENSA":
        # Squinted eyes looking slightly up-right — "thinking" expression.
        target_scala_h, target_offset_x, target_offset_y = 0.75, 15, -12

    elif stato_globale == "PARLA":
        # Eyes pulse with a sine wave to mimic the rhythm of speech.
        target_scala_h = 0.75 + 0.28 * abs(math.sin(t * 0.016))
        target_offset_x, target_offset_y = 0, 0

    # Ease all animated values toward their targets (exponential smoothing).
    offset_x  += (target_offset_x  - offset_x)  * 0.14
    offset_y  += (target_offset_y  - offset_y)  * 0.14
    scala_h   += (target_scala_h   - scala_h)   * 0.22

    # Draw frame.
    schermo.fill(NERO)
    cur_h = max(4, int(OCC_H * scala_h))
    disegna_pillola(CENTRO_SX_X + offset_x, CENTRO_SX_Y + offset_y, OCC_W, cur_h, colore_corrente)
    disegna_pillola(CENTRO_DX_X + offset_x, CENTRO_DX_Y + offset_y, OCC_W, cur_h, colore_corrente)
    pygame.display.flip()
    clock.tick(60)  # Cap at 60 FPS to avoid burning CPU
