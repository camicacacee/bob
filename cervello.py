"""
cervello.py — Bob's brain: LLM responses, long-term memory, and Whisper transcription.

All cloud calls go through the Groq API. The memory system persists user facts
to a local JSON file so Bob can recall preferences across sessions.
"""

import os
import json
from groq import Groq

# ---------------------------------------------------------------------------
# Client & model configuration
# ---------------------------------------------------------------------------

# Groq client authenticates via the GROQ_API_KEY environment variable.
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# LLM model served on Groq used for both responses and memory extraction.
MODEL_NAME = "openai/gpt-oss-120b"

# Path to the local JSON file that stores persistent user facts.
FILE_MEMORIA = "memoria.json"


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------

def carica_memoria():
    """Load persistent facts from the JSON memory file.

    Creates an empty file on first run so the rest of the code can always
    assume the file exists.

    Returns:
        dict: Current memory contents, or {} if the file is missing or corrupt.
    """
    if not os.path.exists(FILE_MEMORIA):
        with open(FILE_MEMORIA, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=4)
        return {}
    try:
        with open(FILE_MEMORIA, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def salva_memoria(nuovi_dati):
    """Merge new facts into the existing memory file.

    Uses a read-then-write pattern so keys not present in nuovi_dati are
    preserved rather than overwritten.

    Args:
        nuovi_dati (dict): Key-value pairs to add or update in memory.
    """
    memoria_attuale = carica_memoria()
    memoria_attuale.update(nuovi_dati)
    with open(FILE_MEMORIA, "w", encoding="utf-8") as f:
        json.dump(memoria_attuale, f, ensure_ascii=False, indent=4)


def estrai_e_aggiorna_memoria(testo_utente):
    """Extract personal facts from the user's message and persist them.

    Sends the message to the LLM with a strict extraction prompt that forces
    compound semantic keys (e.g. 'pizza_preferita', 'fiore_preferito') to
    avoid key collisions between unrelated entities.

    If no personal information is detected, the LLM returns {} and nothing
    is written to disk.

    Args:
        testo_utente (str): The raw user message to analyse.
    """
    prompt_estrazione = f"""
You are a logical data extractor for an assistant's long-term memory.
Analyse the user message: "{testo_utente}"

If the user expresses a preference, habit, or personal fact, extract it as JSON
with COMPOUND SEMANTIC KEYS to avoid collisions.
Rules for keys:
- NEVER use generic keys like 'favourite', 'food', 'name'.
- ALWAYS prefix the entity: e.g. 'pizza_preferita', 'fiore_preferito', 'film_preferito'.
- If there is nothing personal to save, return only an empty JSON object: {{}}

Respond ONLY with valid JSON — no extra text or markdown.
"""
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt_estrazione}],
            temperature=0.1,  # Low temperature for deterministic extraction
        )
        risposta_testo = completion.choices[0].message.content.strip()

        # Strip markdown code fences if the model wraps its output in them.
        if risposta_testo.startswith("```json"):
            risposta_testo = risposta_testo[7:-3].strip()
        elif risposta_testo.startswith("```"):
            risposta_testo = risposta_testo[3:-3].strip()

        dati = json.loads(risposta_testo)
        if dati and isinstance(dati, dict):
            salva_memoria(dati)
            print(f"[MEMORY UPDATED]: {dati}")
    except Exception as e:
        # Non-fatal: a failed extraction just means memory isn't updated this turn.
        print(f"[MEMORY UPDATE ERROR]: {e}")


# ---------------------------------------------------------------------------
# Whisper transcription
# ---------------------------------------------------------------------------

def trascrivi_audio(file_path):
    """Transcribe an audio file using Whisper (large-v3) via the Groq API.

    Args:
        file_path (str): Path to the audio file (.wav or .mp3).

    Returns:
        str: Transcribed text, or empty string on failure.
    """
    try:
        with open(file_path, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(file_path), file.read()),
                model="whisper-large-v3",
                response_format="json",
            )
            return transcription.text.strip()
    except Exception as e:
        print(f"[TRANSCRIPTION ERROR]: {e}")
        return ""


# ---------------------------------------------------------------------------
# LLM response
# ---------------------------------------------------------------------------

def chiedi_a_bob(testo_utente, cronologia=None):
    """Generate Bob's response using long-term memory and short-term history.

    Builds a system prompt that injects the current memory snapshot so Bob
    can reference known user facts. The conversation history (up to 6 messages)
    provides short-term context for multi-turn exchanges.

    If the returned response ends with '?', occhi.py keeps the microphone open
    automatically so the user can reply without repeating the wake word.

    Args:
        testo_utente (str): The user's transcribed command.
        cronologia (list[dict] | None): Conversation history as a list of
            {"role": ..., "content": ...} dicts. None for a fresh exchange.

    Returns:
        str: Bob's response text, or an error message on failure.
    """
    # Always attempt to extract and persist new facts before answering.
    estrai_e_aggiorna_memoria(testo_utente)

    # Inject the current memory snapshot into the system prompt.
    memoria_fatti = carica_memoria()
    stringa_memoria = json.dumps(memoria_fatti, ensure_ascii=False)

    system_prompt = f"""
You are Bob, a bilingual (Italian and English) executive desktop assistant
with a sharp entrepreneurial mindset.

Core behaviour guidelines:
1. **Be direct and natural:** Answer short or closed questions (e.g. "How are you?")
   concisely and naturally. Never force unnecessary follow-up questions.
2. **Measured proactivity:** Ask questions ONLY when context genuinely requires it
   (e.g. brainstorming or missing clarification). Never close with a question
   unless it is truly necessary.
3. If and only if you ask a real question, end your turn with a question mark (?),
   so the system knows to keep the microphone open.
4. **Action-oriented mindset:** When appropriate and requested, be decisive and
   look for the practical angle or strategic opportunity.
5. **Long-term factual memory:**
   Known facts about the user:
   {stringa_memoria}

Operational rules:
- Distinguish precisely between entities with similar names
  (e.g. 'pizza_preferita' is separate from 'fiore_preferito').
- If a fact is not in memory, honestly say you don't know.
- Reply in the same language the user used in their last message.
"""

    messaggi = [{"role": "system", "content": system_prompt}]

    if cronologia:
        # Include full conversation history for multi-turn context.
        messaggi.extend(cronologia)
    else:
        messaggi.append({"role": "user", "content": testo_utente})

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messaggi,
            temperature=0.6,  # Balanced creativity vs. consistency
            max_tokens=300,   # Keep responses concise for voice output
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM ERROR]: {e}")
        return "A processing error occurred."
