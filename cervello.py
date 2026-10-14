"""
cervello.py — Bob's brain: LLM responses, intent-based actions, memory, and transcription.

Action detection strategy
--------------------------
openai/gpt-oss-120b does not support the Groq native tool_choice API, so actions
are detected via prompt engineering: the system prompt instructs the model to reply
with a compact JSON block when it needs to perform an action, and with plain text
for everything else. This module parses that JSON and dispatches to the matching
Python function.

JSON action format (model output when an action is needed):
    {"action": "<name>", "param1": "value1", ...}

Supported actions:
    crea_evento      — create a macOS Calendar event
    leggi_calendario — read today's events
    controlla_luce   — control the Tuya smart bulb
"""

import os
import json
import re
from datetime import datetime, timedelta
from groq import Groq
from voce import rileva_lingua

from calendario import crea_evento, leggi_eventi_oggi, leggi_eventi_data
from luci import controlla_luce_cami

# Load .env if python-dotenv is installed; otherwise fall back to shell env.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Client & model configuration
# ---------------------------------------------------------------------------

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# The original model that works well for this account.
MODEL_NAME = "openai/gpt-oss-120b"

FILE_MEMORIA = "memoria.json"


# ---------------------------------------------------------------------------
# Action dispatcher
# ---------------------------------------------------------------------------

def esegui_azione(dati: dict) -> str:
    """Execute a structured action decoded from the model's JSON reply.

    Args:
        dati (dict): Parsed JSON from the model. Must contain an "action" key.

    Returns:
        str: Human-readable result passed back to the model for confirmation.
    """
    azione = dati.get("action", "")

    if azione == "crea_evento":
        return crea_evento(
            titolo=dati.get("titolo", "Evento"),
            data_ora=dati.get("data_ora", ""),
            durata_minuti=int(dati.get("durata_minuti", 60)),
        )

    if azione == "leggi_calendario":
        data = dati.get("data")
        if data:
            return leggi_eventi_data(data)
        return leggi_eventi_oggi()

    if azione == "controlla_luce":
        return controlla_luce_cami(
            azione=dati.get("luce_azione", ""),
            colore=dati.get("colore"),
            luminosita=dati.get("luminosita"),
        )

    return f"Unknown action: {azione}"


def _estrai_json_azione(testo: str):
    """Try to extract an action JSON block from the model's reply.

    The model is instructed to output a single JSON object on the first line
    when it wants to perform an action. This function extracts it safely.

    Args:
        testo (str): Raw model reply.

    Returns:
        dict | None: Parsed action dict, or None if the reply is plain text.
    """
    # Look for a JSON object anywhere in the response (handles minor formatting drift).
    match = re.search(r'\{[^{}]+\}', testo, re.DOTALL)
    if not match:
        return None
    try:
        dati = json.loads(match.group())
        # Only treat it as an action if the "action" key is present.
        if "action" in dati:
            return dati
    except json.JSONDecodeError:
        pass
    return None


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------

def carica_memoria() -> dict:
    """Load persistent user facts from the JSON memory file.

    Returns:
        dict: Current memory, or {} if the file is missing or corrupt.
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


def salva_memoria(nuovi_dati: dict):
    """Merge new facts into the memory file without overwriting existing keys.

    Args:
        nuovi_dati (dict): Key-value pairs to add or update.
    """
    memoria_attuale = carica_memoria()
    memoria_attuale.update(nuovi_dati)
    with open(FILE_MEMORIA, "w", encoding="utf-8") as f:
        json.dump(memoria_attuale, f, ensure_ascii=False, indent=4)


def estrai_e_aggiorna_memoria(testo_utente: str):
    """Extract personal facts from the user's message and persist them.

    Uses compound semantic keys (e.g. 'pizza_preferita') to avoid collisions.
    Failures are silently swallowed — a missed extraction is non-fatal.

    Args:
        testo_utente (str): Raw user message to analyse.
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
            temperature=0.1,
        )
        risposta_testo = completion.choices[0].message.content.strip()

        # Strip markdown fences if the model wraps its output in them.
        if risposta_testo.startswith("```json"):
            risposta_testo = risposta_testo[7:-3].strip()
        elif risposta_testo.startswith("```"):
            risposta_testo = risposta_testo[3:-3].strip()

        dati = json.loads(risposta_testo)
        if dati and isinstance(dati, dict) and "action" not in dati:
            salva_memoria(dati)
            print(f"[MEMORY UPDATED]: {dati}")
    except Exception as e:
        print(f"[MEMORY UPDATE ERROR]: {e}")


# ---------------------------------------------------------------------------
# Whisper transcription
# ---------------------------------------------------------------------------

def trascrivi_audio(file_path: str) -> str:
    """Transcribe an audio file using Whisper (large-v3) via Groq.

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
# LLM response with prompt-based action detection
# ---------------------------------------------------------------------------

def chiedi_a_bob(testo_utente: str, cronologia: list = None) -> str:
    """Generate Bob's response, executing actions when the model requests them.

    The system prompt instructs the model to reply with a specific JSON block
    when it detects an actionable intent (calendar, lights). This module parses
    that JSON, runs the Python function, then calls the model again with the
    result to get a natural spoken confirmation.

    For plain conversational replies (no JSON in the response), the model's
    text is returned directly.

    Args:
        testo_utente (str): The user's transcribed command.
        cronologia (list[dict] | None): Conversation history as
            [{"role": ..., "content": ...}] dicts (last 6 messages).

    Returns:
        str: Bob's spoken response text.
    """
    estrai_e_aggiorna_memoria(testo_utente)

    memoria_fatti = carica_memoria()
    stringa_memoria = json.dumps(memoria_fatti, ensure_ascii=False)

    # Detect the user's language from their message and make it explicit in
    # every prompt — "reply in the same language" is too vague and gets ignored.
    voce_rilevata = rileva_lingua(testo_utente)
    if voce_rilevata == "en-US-GuyNeural":
        lingua_utente = "English"
        lingua_istruzione = "You MUST reply in English only."
    else:
        lingua_utente = "Italian"
        lingua_istruzione = "Devi rispondere SOLO in italiano."

    # Inject current date so the model resolves relative expressions correctly.
    ora_attuale = datetime.now().strftime("%Y-%m-%d %H:%M")
    domani = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    system_prompt = f"""
You are Bob, a bilingual (Italian and English) executive desktop assistant
with a sharp entrepreneurial mindset.

Current date and time : {ora_attuale}
Tomorrow's date       : {domani}

⚠️ LANGUAGE RULE (mandatory, no exceptions):
The user's last message was in {lingua_utente}. {lingua_istruzione}
This applies to EVERY reply, including action confirmations.

═══ ACTION SYSTEM ═══
When the user asks you to perform one of the following actions, reply ONLY
with the corresponding JSON object — nothing else, no extra text.

1. Create a calendar event or reminder:
   {{"action":"crea_evento","titolo":"<title>","data_ora":"YYYY-MM-DD HH:MM","durata_minuti":<minutes>}}

2. Read the calendar for a specific date (ALWAYS use this when the user asks
   what they have planned, what's on their schedule, or what they need to do
   on any day — today, tomorrow, or any named day):
   {{"action":"leggi_calendario","data":"YYYY-MM-DD"}}
   Use today's date ({ora_attuale[:10]}) if no specific date is mentioned.
   Resolve named days using the current date: "venerdì", "Friday", "tomorrow", etc.

3. Control the smart light "Cami":
   {{"action":"controlla_luce","luce_azione":"accendi|spegni|colore|luminosita","colore":"<name>","luminosita":<0-100>}}

Rules for actions:
- Use the current date above to resolve relative expressions: "tomorrow" → {domani}, "in 2 hours" → calculate from {ora_attuale}.
- For durata_minuti, default to 60 if not mentioned.
- For colore and luminosita, omit the key if not applicable.
- Output ONLY the JSON, with no surrounding text or markdown.

═══ CONVERSATION ═══
For everything else, reply normally in plain text following these guidelines:
1. Be direct and natural. Answer short questions concisely.
2. Measured proactivity: ask follow-up questions ONLY when truly necessary.
   If you ask a question, end with ? so the microphone stays open.
3. Action-oriented mindset: be decisive, look for the practical angle.
4. Long-term memory — known facts about the user:
   {stringa_memoria}
- Distinguish precisely between similar memory keys.
- If a fact is not in memory, honestly say you don't know.
"""

    messaggi = [{"role": "system", "content": system_prompt}]
    if cronologia:
        messaggi.extend(cronologia)
    else:
        messaggi.append({"role": "user", "content": testo_utente})

    try:
        # First call: model either returns an action JSON or a plain reply.
        risposta = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messaggi,
            temperature=0.6,
            max_tokens=300,
        )
        testo_risposta = risposta.choices[0].message.content.strip()

        # Check whether the model wants to perform an action.
        azione_dati = _estrai_json_azione(testo_risposta)

        if azione_dati:
            print(f"[ACTION]: {azione_dati}")
            risultato = esegui_azione(azione_dati)
            print(f"[ACTION RESULT]: {risultato}")

            # Build the confirmation prompt based on the action type.
            # Calendar reads must list every event aloud — other actions just confirm briefly.
            azione_tipo = azione_dati.get("action", "")
            if azione_tipo == "leggi_calendario":
                istruzione_conferma = (
                    f"[System: calendar result: {risultato}] "
                    f"Read out ALL the events naturally, including their times. "
                    f"If there are no events, say so. {lingua_istruzione}"
                )
                max_tok = 300  # Enough room to list multiple events
            else:
                istruzione_conferma = (
                    f"[System: action completed with result: {risultato}] "
                    f"Confirm in one short spoken sentence what you just did. {lingua_istruzione}"
                )
                max_tok = 100

            messaggi.append({"role": "assistant", "content": testo_risposta})
            messaggi.append({"role": "user", "content": istruzione_conferma})

            conferma = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messaggi,
                temperature=0.6,
                max_tokens=max_tok,
            )
            return conferma.choices[0].message.content.strip()

        # Plain conversational reply — return as-is.
        return testo_risposta

    except Exception as e:
        print(f"[LLM ERROR]: {e}")
        return "A processing error occurred."
