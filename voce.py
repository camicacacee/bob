"""
voce.py — Bob's voice: text-to-speech synthesis via Microsoft Edge TTS.

Handles language detection, number formatting for natural reading, and
audio playback through pygame. Also exposes an interrupt function so the
listen loop can cut Bob off mid-sentence.
"""

import os
import asyncio
import edge_tts
import pygame
import re
import time

# Default voice for Italian text.
VOICE_MODEL = "it-IT-DiegoNeural"

# Initialise the pygame mixer only if it hasn't been set up yet
# (occhi.py calls pygame.init() before importing this module).
if not pygame.mixer.get_init():
    pygame.mixer.init()


# ---------------------------------------------------------------------------
# Text pre-processing
# ---------------------------------------------------------------------------

def rimuovi_markdown(testo):
    """Strip markdown formatting so the TTS engine never reads symbols aloud.

    Handles the most common patterns the LLM produces:
    - **bold** and *italic* → plain text
    - # headings → plain text
    - - bullet lines → sentence with a comma pause
    - Backtick code spans → plain text
    """
    if not testo:
        return ""
    # Bold (**text**) and italic (*text*) — remove the surrounding asterisks.
    testo = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', testo)
    # Headings (# Title) — drop the hashes.
    testo = re.sub(r'^\s*#{1,6}\s*', '', testo, flags=re.MULTILINE)
    # Bullet points (- item or • item) — replace the marker with a comma so
    # the TTS pauses naturally between items instead of running them together.
    testo = re.sub(r'^\s*[-•]\s+', ', ', testo, flags=re.MULTILINE)
    # Inline code (`code`) — remove backticks.
    testo = re.sub(r'`(.+?)`', r'\1', testo)
    # Newlines → single space (do this before comma cleanup).
    testo = re.sub(r'\n+', ' ', testo)
    # Clean up punctuation artefacts left by the replacements above.
    testo = re.sub(r',\s*,', ',', testo)          # double commas
    testo = re.sub(r'([.!?])\s*,\s*', r'\1 ', testo)  # ". ," → ". "
    testo = re.sub(r'^\s*,\s*', '', testo)        # leading comma
    testo = re.sub(r'\s{2,}', ' ', testo)         # multiple spaces
    return testo.strip()


def formatta_numeri_per_tts(testo):
    """Format numbers in text so the TTS engine reads them naturally.

    Two transformations are applied:
    1. Digit separators (regular spaces, narrow non-breaking spaces U+202F,
       and non-breaking spaces U+00A0) between consecutive digits are removed
       so that split numbers like "1 000" are read as "1000".
    2. Sequences of 4+ digits are then re-formatted with Italian thousands
       separators (dots) so the engine reads "1.000" as "mille" rather than
       four individual digits.

    Args:
        testo (str): Raw response text from the LLM.

    Returns:
        str: Pre-processed text ready for TTS.
    """
    if not testo:
        return ""

    # Step 1: collapse whitespace between digits.
    testo_unito = re.sub(r'(?<=\d)[\s  ]+(?=\d)', '', testo)

    # Step 2: add Italian thousands dots to long digit sequences.
    def inserisci_punti(match):
        num_str = match.group(0)
        try:
            valore = int(num_str)
            return f"{valore:,}".replace(",", ".")
        except Exception:
            return num_str

    testo_formattato = re.sub(r'\b\d{4,}\b', inserisci_punti, testo_unito)
    return testo_formattato


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

def rileva_lingua(testo):
    """Pick the TTS voice model based on the language of the text.

    Uses a simple heuristic: if at least 2 common English function words are
    found, or they make up more than 25% of the tokens, switch to the English
    voice. Otherwise stay with Italian.

    Args:
        testo (str): Text to analyse.

    Returns:
        str: Edge TTS voice model identifier.
    """
    parole = testo.lower().split()
    if not parole:
        return VOICE_MODEL

    en_words = {
        # Function words
        "the", "is", "in", "and", "to", "of", "a", "it", "you",
        "that", "my", "what", "how", "do", "for", "are", "have",
        "with", "this", "from", "i", "me", "we", "he", "she",
        "they", "them", "his", "her", "our", "your", "its", "can",
        "will", "would", "could", "should", "may", "might", "must",
        "shall", "was", "were", "be", "been", "being", "has", "had",
        "did", "does", "not", "no", "on", "at", "by", "an", "or",
        "but", "so", "if", "as", "up", "out", "about", "into",
        "then", "than", "when", "where", "who", "which", "there",
        "their", "all", "any", "also", "just", "more", "also",
        "some", "one", "two", "time", "get", "got", "go", "let",
        # Greetings and short conversational phrases
        "hi", "hey", "bye", "hello", "yes", "yeah", "no", "nope",
        "ok", "okay", "please", "thanks", "thank", "sorry", "great",
        "good", "well", "right", "sure", "fine", "nice", "cool",
        # Common command words
        "create", "add", "set", "show", "read", "check", "open",
        "turn", "make", "tell", "need", "want", "like", "know",
        "think", "see", "use", "find", "give", "put", "take",
        "remind", "schedule", "book", "cancel", "delete", "edit",
        "today", "tomorrow", "yesterday", "now", "later", "next",
        "morning", "afternoon", "evening", "night", "week", "month",
        "monday", "tuesday", "wednesday", "thursday", "friday",
        "saturday", "sunday", "january", "february", "march",
        "april", "june", "july", "august", "september", "october",
        "november", "december", "event", "meeting", "reminder",
        "light", "lights", "lamp", "calendar", "task", "note",
    }
    # Split hyphenated tokens too (e.g. "bye-bye" → ["bye", "bye"]).
    tokens = []
    for p in parole:
        tokens.extend(p.split("-"))
    en_score = sum(1 for t in tokens if t in en_words)

    # Lower threshold: 1 English word in a short phrase, or 15% in longer text.
    soglia = 1 if len(tokens) <= 3 else max(2, int(len(tokens) * 0.15))
    if en_score >= soglia:
        return "en-US-GuyNeural"
    return VOICE_MODEL


# ---------------------------------------------------------------------------
# Playback
# ---------------------------------------------------------------------------

def parla(testo):
    """Convert text to speech and play it back through pygame.

    Pipeline:
        1. Pre-process numbers with formatta_numeri_per_tts.
        2. Detect language and pick the correct voice.
        3. Generate the MP3 asynchronously with Edge TTS.
        4. Load and play the file via pygame.mixer.music.

    A leading ". " is prepended to the text to give the TTS engine a brief
    moment to stabilise before the actual content starts — this prevents the
    first syllable from being clipped on some systems.

    A short sleep before play() avoids a race condition where pygame starts
    reading the file before Edge TTS has fully flushed it to disk.

    Args:
        testo (str): Bob's response text to speak aloud.
    """
    if not testo or not testo.strip():
        return

    testo_pulito = formatta_numeri_per_tts(rimuovi_markdown(testo))
    modello_voce = rileva_lingua(testo_pulito)
    file_audio = "temp_voice.mp3"

    try:
        async def _save():
            # Prepend ". " to avoid clipping the first word on playback start.
            comm = edge_tts.Communicate(". " + testo_pulito.strip(), modello_voce)
            await comm.save(file_audio)

        asyncio.run(_save())

        if os.path.exists(file_audio) and os.path.getsize(file_audio) > 0:
            pygame.mixer.music.load(file_audio)
            # Brief delay to ensure the file is fully written before pygame reads it.
            time.sleep(0.3)
            pygame.mixer.music.play()
    except Exception as e:
        print(f"[VOICE ERROR]: {e}")


def interrompi_voce():
    """Immediately stop Bob's voice if audio is currently playing.

    Called by the listen loop when a stop trigger word is detected while
    Bob is speaking. Safe to call even when no audio is playing.
    """
    if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
        pygame.mixer.music.stop()
