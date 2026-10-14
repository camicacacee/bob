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

pygame.init()
LARGHEZZA, ALTEZZA = 320, 240
schermo = pygame.display.set_mode((LARGHEZZA, ALTEZZA))
pygame.display.set_caption("Bob - Sistema Cognitivo")
clock = pygame.time.Clock()

NERO, AZZURRO, VERDE, VIOLA = (15, 15, 25), (0, 200, 255), (0, 255, 150), (200, 50, 255)
OCC_W, OCC_H, OCC_R = 70, 110, 35
CENTRO_SX_X, CENTRO_SX_Y = 100, 120
CENTRO_DX_X, CENTRO_DX_Y = 220, 120

stato_globale = "IDLE"
colore_corrente = AZZURRO
storico_conversazione = []
ultima_risposta_bob = ""

def salva_file_audio(buffer_audio, nome_file="temp_cmd.wav"):
    wf = wave.open(nome_file, 'wb')
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(16000)
    wf.writeframes(b''.join(buffer_audio))
    wf.close()
    return nome_file

def ciclo_ascolto():
    global stato_globale, colore_corrente, storico_conversazione, ultima_risposta_bob
    
    print("\n[CARICAMENTO] Avvio del motore vocale...")
    modello_vosk = Model("modello_vosk")
    recognizer_vosk = KaldiRecognizer(modello_vosk, 16000)
    
    CHUNK = 2000
    pa = pyaudio.PyAudio()
    mic_stream = pa.open(rate=16000, channels=1, format=pyaudio.paInt16, input=True, frames_per_buffer=CHUNK)
    
    buffer_storico = deque(maxlen=8)
    in_registrazione = False
    buffer_registrazione = []
    silenzi_consecutivi = 0
    
    SOGLIA_SILENZIO = 800
    MAX_SILENZIO_CHUNKS = 16
    TRIGGER_WORDS = ["bob", "pop", "bomb", "bop"]
    
    # Trigger allargati per ingannare il modello Vosk inglese
    TRIGGER_STOP = ["basta", "stop", "silenzio", "bust", "pasta", "stob"]

    print("\n[BOB PRONTO] Pronuncia 'Bob' per iniziare o un secco 'Stop' per zittirlo.")

    try:
        while True:
            audio_raw = mic_stream.read(CHUNK, exception_on_overflow=False)
            
            # --- 1. MENTRE BOB PARLA: ASCOLTO CONTINUO DELLO STOP ---
            if stato_globale == "PARLA":
                if recognizer_vosk.AcceptWaveform(audio_raw):
                    res = json.loads(recognizer_vosk.Result())
                    testo_parziale = res.get("text", "")
                else:
                    res = json.loads(recognizer_vosk.PartialResult())
                    testo_parziale = res.get("partial", "")
                
                testo_analizzato = testo_parziale.lower()
                
                if testo_analizzato.strip():
                    print(f"\r[ASCOLTO SOTTOFONDO]: {testo_analizzato}", end="")
                    
                if any(w in testo_analizzato for w in TRIGGER_STOP):
                    print(f"\n\n[🛑 INTERRUZIONE RILEVATA - Trigger: '{testo_analizzato}'] Fermo Bob...")
                    interrompi_voce()
                    stato_globale = "IDLE"
                    colore_corrente = AZZURRO
                    in_registrazione = False
                    buffer_storico.clear()
                    buffer_registrazione.clear()
                    recognizer_vosk.Reset()
                    
                    # Svuota fisicamente il buffer audio per neutralizzare l'eco
                    if mic_stream.get_read_available() > 0:
                        mic_stream.read(mic_stream.get_read_available(), exception_on_overflow=False)
                    continue
                
                # Se la traccia audio è finita regolarmente
                if not pygame.mixer.music.get_busy():
                    print("") 
                    if ultima_risposta_bob.strip().endswith("?"):
                        print("[DOMANDA RILEVATA] Bob ha finito e ti ascolta (senza wake word)...")
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

            # --- 2. ATTESA DELLA WAKE WORD ---
            if not in_registrazione:
                buffer_storico.append(audio_raw)
                
                if recognizer_vosk.AcceptWaveform(audio_raw):
                    testo_parziale = json.loads(recognizer_vosk.Result()).get("text", "")
                else:
                    testo_parziale = json.loads(recognizer_vosk.PartialResult()).get("partial", "")
                
                if any(w in testo_parziale.lower() for w in TRIGGER_WORDS):
                    print(f"\n[🟢 WAKE WORD] Ti ascolto...")
                    stato_globale = "ASCOLTO"
                    colore_corrente = VERDE
                    
                    in_registrazione = True
                    buffer_registrazione = list(buffer_storico)
                    silenzi_consecutivi = 0
                    recognizer_vosk.Reset()
                    
            # --- 3. REGISTRAZIONE DELLA VOCE DELL'UTENTE ---
            else:
                buffer_registrazione.append(audio_raw)
                audio_np = np.frombuffer(audio_raw, dtype=np.int16)
                volume = np.abs(audio_np).mean()
                
                if volume < SOGLIA_SILENZIO:
                    silenzi_consecutivi += 1
                else:
                    silenzi_consecutivi = 0
                
                if silenzi_consecutivi > MAX_SILENZIO_CHUNKS:
                    mic_stream.stop_stream()
                    
                    percorso_wav = salva_file_audio(buffer_registrazione)
                    print("[ELABORAZIONE WHISPER IN CORSO...]")
                    comando = trascrivi_audio(percorso_wav).lower()
                    
                    for trigger in TRIGGER_WORDS:
                        comando = comando.replace(trigger, "").strip()
                    
                    if comando:
                        print(f"[COMANDO]: '{comando}'")
                        stato_globale = "PENSA"
                        colore_corrente = VIOLA
                        
                        storico_conversazione.append({"role": "user", "content": comando})
                        ultima_risposta_bob = chiedi_a_bob(comando, cronologia=storico_conversazione)
                        print(f"[BOB]: {ultima_risposta_bob}")
                        storico_conversazione.append({"role": "assistant", "content": ultima_risposta_bob})
                        
                        if len(storico_conversazione) > 6:
                            storico_conversazione = storico_conversazione[-6:]
                        
                        if mic_stream.get_read_available() > 0:
                            mic_stream.read(mic_stream.get_read_available(), exception_on_overflow=False)
                        recognizer_vosk.Reset()
                        
                        stato_globale = "PARLA"
                        parla(ultima_risposta_bob)
                    else:
                        stato_globale = "IDLE"
                        colore_corrente = AZZURRO
                    
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

threading.Thread(target=ciclo_ascolto, daemon=True).start()

# --- GRAFICA PYGAME ---
offset_x, offset_y, target_offset_x, target_offset_y = 0, 0, 0, 0
scala_h, target_scala_h = 1.0, 1.0
timer_blink = pygame.time.get_ticks() + random.randint(2000, 4000)
timer_sguardo = pygame.time.get_ticks() + random.randint(1500, 3000)

def disegna_pillola(cx, cy, w, h, colore):
    if h < 4 or w < 4: return
    rect = pygame.Rect(int(cx - w / 2), int(cy - h / 2), int(w), int(h))
    pygame.draw.rect(schermo, colore, rect, border_radius=min(OCC_R, h // 2, w // 2))
    if h > 20:
        rl_surf = pygame.Surface((max(6, int(w * 0.82)), max(6, int(h * 0.32))), pygame.SRCALPHA)
        pygame.draw.rect(rl_surf, (255, 255, 255, 55), (0, 0, rl_surf.get_width(), rl_surf.get_height()), border_radius=min(rl_surf.get_height() // 2, rl_surf.get_width() // 2))
        schermo.blit(rl_surf, (int(cx - rl_surf.get_width() / 2), rect.top + int(h * 0.07)))

while True:
    t = pygame.time.get_ticks()
    for evento in pygame.event.get():
        if evento.type == pygame.QUIT:
            pygame.quit()
            sys.exit()

    if stato_globale == "IDLE":
        if t > timer_blink:
            target_scala_h = 0.05
            if scala_h <= 0.12:
                timer_blink = t + random.randint(2500, 5000)
                target_scala_h = 1.0
        if t > timer_sguardo:
            target_offset_x, target_offset_y = random.choice([-18, -9, 0, 0, 9, 18]), random.choice([-8, 0, 0, 8])
            timer_sguardo = t + random.randint(1500, 3500)
    elif stato_globale == "ASCOLTO": target_scala_h, target_offset_x, target_offset_y = 1.2, 0, 0
    elif stato_globale == "PENSA": target_scala_h, target_offset_x, target_offset_y = 0.75, 15, -12
    elif stato_globale == "PARLA": target_scala_h, target_offset_x, target_offset_y = 0.75 + 0.28 * abs(math.sin(t * 0.016)), 0, 0

    offset_x += (target_offset_x - offset_x) * 0.14
    offset_y += (target_offset_y - offset_y) * 0.14
    scala_h += (target_scala_h - scala_h) * 0.22

    schermo.fill(NERO)
    cur_h = max(4, int(OCC_H * scala_h))
    disegna_pillola(CENTRO_SX_X + offset_x, CENTRO_SX_Y + offset_y, OCC_W, cur_h, colore_corrente)
    disegna_pillola(CENTRO_DX_X + offset_x, CENTRO_DX_Y + offset_y, OCC_W, cur_h, colore_corrente)
    pygame.display.flip()
    clock.tick(60)