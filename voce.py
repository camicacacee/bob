import os
import asyncio
import edge_tts
import pygame
import re
import time

VOICE_MODEL = "it-IT-DiegoNeural"

if not pygame.mixer.get_init():
    pygame.mixer.init()

def formatta_numeri_per_tts(testo):
    """
    Rimuove spazi separatori tra cifre (inclusi spazi Unicode invisibili)
    e formatta i numeri con il punto delle migliaia per una lettura unita e naturale.
    """
    if not testo:
        return ""
    
    # Rimuove spazi tra cifre consecutive
    testo_unito = re.sub(r'(?<=\d)[\s\u202f\u00a0]+(?=\d)', '', testo)
    
    # Formatta sequenze numeriche di 4 o più cifre con i punti delle migliaia
    def inserisci_punti(match):
        num_str = match.group(0)
        try:
            valore = int(num_str)
            return f"{valore:,}".replace(",", ".")
        except:
            return num_str

    testo_formattato = re.sub(r'\b\d{4,}\b', inserisci_punti, testo_unito)
    return testo_formattato

def rileva_lingua(testo):
    parole = testo.lower().split()
    if not parole:
        return VOICE_MODEL
    en_words = {"the", "is", "in", "and", "to", "of", "a", "it", "you", "that", "my", "what", "how", "do", "for", "are", "have", "with", "this", "from"}
    en_score = sum(1 for p in parole if p in en_words)
    if en_score >= 2 or (en_score / len(parole) > 0.25):
        return "en-US-GuyNeural"
    return VOICE_MODEL

def parla(testo):
    if not testo or not testo.strip():
        return
        
    testo_pulito = formatta_numeri_per_tts(testo)
    
    modello_voce = rileva_lingua(testo_pulito)
    file_audio = "temp_voice.mp3"
    try:
        async def _save():
            comm = edge_tts.Communicate(". " + testo_pulito.strip(), modello_voce)
            await comm.save(file_audio)
        asyncio.run(_save())
        
        if os.path.exists(file_audio) and os.path.getsize(file_audio) > 0:
            # os.system("afplay /System/Library/Sounds/Pop.aiff -v 0.3") # tienilo disattivato per ora
            pygame.mixer.music.load(file_audio)
            time.sleep(0.3)  # <--- AGGIUNGI QUESTO MICRO-RITARDO
            pygame.mixer.music.play()
    except Exception as e:
        print(f"[ERRORE VOCE]: {e}")

def interrompi_voce():
    """Blocca immediatamente la voce di Bob se sta parlando."""
    if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
        pygame.mixer.music.stop()