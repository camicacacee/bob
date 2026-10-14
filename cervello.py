"""
cervello.py — Bob's brain: dual-model LLM, tool calling, memory, and transcription.

Two-model strategy
------------------
MODEL_TOOLS  (llama3-groq-70b-8192-tool-use-preview)
    First pass on every user message. Decides whether a tool is needed.
    If the model returns a tool_call, the matching Python function is executed
    and a short confirmation is generated with the same model.

MODEL_CHAT  (llama-3.3-70b-versatile)
    Used only when no tool was triggered. Groq's best conversational model
    gives higher-quality free-form answers than the tool-use specialist.

Flow
----
User message
    └─▶ MODEL_TOOLS (with tool definitions)
            ├─ tool_call returned
            │       └─▶ execute Python function
            │               └─▶ MODEL_TOOLS → short spoken confirmation
            └─ plain text returned (no tool needed)
                    └─▶ MODEL_CHAT → richer conversational answer
"""

import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from groq import Groq

from calendario import crea_evento, leggi_eventi_oggi
from luci import controlla_luce_cami

# Load GROQ_API_KEY (and any other vars) from a .env file in the project root.
# Falls back to the shell environment if no .env file is present.
load_dotenv()

# ---------------------------------------------------------------------------
# Client & model configuration
# ---------------------------------------------------------------------------

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Tool-use specialist — must be this model for Groq tool calling to work.
MODEL_TOOLS = "llama3-groq-70b-8192-tool-use-preview"

# Best conversational model on Groq — used for free-form answers with no tool.
MODEL_CHAT = "llama-3.3-70b-versatile"

FILE_MEMORIA = "memoria.json"

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------
# Each entry is passed to the Groq API so the LLM knows what actions exist.
# The "description" fields are the main signal the model uses to decide
# whether and when to call a tool — be explicit and give concrete examples.

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "crea_evento_calendario",
            "description": (
                "Creates an event or reminder in the user's macOS Calendar. "
                "Call this whenever the user asks to add, schedule, set, remind, "
                "or note something at a specific time or date. "
                "Today's date and tomorrow's date are always in the system prompt — "
                "use them to resolve relative expressions such as 'tomorrow', "
                "'next Monday', 'in 2 hours', 'this evening'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "titolo": {
                        "type": "string",
                        "description": "Short, clear event title (e.g. 'Grocery shopping', 'Call with Marco').",
                    },
                    "data_ora": {
                        "type": "string",
                        "description": "Start date and time in 'YYYY-MM-DD HH:MM' format.",
                    },
                    "durata_minuti": {
                        "type": "integer",
                        "description": "Duration in minutes. Default to 60 if not mentioned.",
                    },
                },
                "required": ["titolo", "data_ora"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "leggi_calendario_oggi",
            "description": (
                "Returns all events scheduled for today. "
                "Use when the user asks what's on today, what they have planned, "
                "or about their schedule / agenda for the day."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "controlla_luce",
            "description": (
                "Controls the smart light named 'Cami'. "
                "Use for any request to turn it on or off, change its colour, "
                "or adjust its brightness."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "azione": {
                        "type": "string",
                        "enum": ["accendi", "spegni", "colore", "luminosita"],
                        "description": "Action to perform on the light.",
                    },
                    "colore": {
                        "type": "string",
                        "enum": ["rosso", "verde", "blu", "bianco", "giallo", "viola", "rosa", "arancione"],
                        "description": "Colour name — required only when azione is 'colore'.",
                    },
                    "luminosita": {
                        "type": "integer",
                        "description": "Brightness 0–100 % — required only when azione is 'luminosita'.",
                    },
                },
                "required": ["azione"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------

def esegui_tool(nome_tool: str, argomenti: dict) -> str:
    """Execute the Python function that matches a tool call from the LLM.

    Each branch maps a tool name (as defined in TOOLS) to its Python
    implementation. Arguments arrive as a plain dict already parsed from JSON.

    Args:
        nome_tool (str): Tool name returned by the LLM.
        argomenti (dict): Parsed function arguments from the LLM's tool_call.

    Returns:
        str: Human-readable result passed back to the LLM for confirmation.
    """
    if nome_tool == "crea_evento_calendario":
        return crea_evento(
            titolo=argomenti["titolo"],
            data_ora=argomenti["data_ora"],
            durata_minuti=argomenti.get("durata_minuti", 60),
        )

    if nome_tool == "leggi_calendario_oggi":
        return leggi_eventi_oggi()

    if nome_tool == "controlla_luce":
        return controlla_luce_cami(
            azione=argomenti["azione"],
            colore=argomenti.get("colore"),
            luminosita=argomenti.get("luminosita"),
        )

    return f"Unknown tool: {nome_tool}"


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------

def carica_memoria() -> dict:
    """Load persistent user facts from the JSON memory file.

    Returns:
        dict: Current memory contents, or {} if missing or corrupt.
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

    Sends the message to MODEL_TOOLS with a strict JSON-only extraction
    prompt. Uses compound semantic keys (e.g. 'pizza_preferita') so that
    different entities with similar names never overwrite each other.

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
            model=MODEL_TOOLS,       # Structured output — tool model is reliable here
            messages=[{"role": "user", "content": prompt_estrazione}],
            temperature=0.1,         # Near-zero temperature for deterministic extraction
        )
        risposta_testo = completion.choices[0].message.content.strip()

        # Strip markdown fences if the model wraps its output in them.
        if risposta_testo.startswith("```json"):
            risposta_testo = risposta_testo[7:-3].strip()
        elif risposta_testo.startswith("```"):
            risposta_testo = risposta_testo[3:-3].strip()

        dati = json.loads(risposta_testo)
        if dati and isinstance(dati, dict):
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
# Shared system prompt builder
# ---------------------------------------------------------------------------

def _build_system_prompt() -> str:
    """Build the system prompt with current date, memory, and Bob's personality.

    Injecting the current date lets both models resolve relative expressions
    like 'tomorrow' or 'next Monday' without guessing.

    Returns:
        str: Fully assembled system prompt string.
    """
    ora_attuale = datetime.now().strftime("%Y-%m-%d %H:%M")
    domani = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    memoria_fatti = carica_memoria()
    stringa_memoria = json.dumps(memoria_fatti, ensure_ascii=False)

    return f"""
You are Bob, a bilingual (Italian and English) executive desktop assistant
with a sharp entrepreneurial mindset.

Current date and time : {ora_attuale}
Tomorrow's date       : {domani}

Core behaviour guidelines:
1. **Be direct and natural.** Answer short or closed questions concisely.
   Never force unnecessary follow-up questions.
2. **Use tools proactively.** When the user asks to create an event, reminder,
   or todo — always call crea_evento_calendario immediately. Do not ask for
   confirmation first; just act and report back concisely.
3. **Measured proactivity.** Ask questions ONLY when the context genuinely
   requires it. If you ask a real question, end your turn with a question
   mark (?) so the system keeps the microphone open.
4. **Action-oriented mindset.** Be decisive and look for the practical angle.
5. **Long-term factual memory.**
   Known facts about the user:
   {stringa_memoria}

Operational rules:
- Distinguish precisely between similar-named memory keys.
- If a fact is not in memory, honestly say you don't know.
- Reply in the same language the user used in their last message.
- After executing a tool, confirm what you did in one short spoken sentence.
"""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def chiedi_a_bob(testo_utente: str, cronologia: list = None) -> str:
    """Generate Bob's response using the dual-model strategy.

    Pass 1 — MODEL_TOOLS (tool-use specialist):
        Sent with the full tool list. If the model returns a tool_call,
        the matching Python function is executed. A brief confirmation is
        then generated with the same model (it already has the context).

    Pass 2 — MODEL_CHAT (conversational specialist):
        Runs only when Pass 1 produced NO tool call. The plain-text response
        from MODEL_TOOLS is discarded and the message list is re-submitted to
        MODEL_CHAT, which produces higher-quality free-form answers.

    This avoids doubling API calls on tool-triggered turns while giving the
    best conversation quality for ordinary exchanges.

    Args:
        testo_utente (str): The user's transcribed command.
        cronologia (list[dict] | None): Conversation history as
            [{"role": ..., "content": ...}, ...] dicts (last 6 messages).

    Returns:
        str: Bob's spoken response text.
    """
    # Always attempt to extract and persist new personal facts first.
    estrai_e_aggiorna_memoria(testo_utente)

    system_prompt = _build_system_prompt()

    # Assemble the message list for this turn.
    messaggi = [{"role": "system", "content": system_prompt}]
    if cronologia:
        messaggi.extend(cronologia)
    else:
        messaggi.append({"role": "user", "content": testo_utente})

    try:
        # ------------------------------------------------------------------
        # Pass 1: tool-use model — detects intent and executes actions
        # ------------------------------------------------------------------
        risposta = client.chat.completions.create(
            model=MODEL_TOOLS,
            messages=messaggi,
            tools=TOOLS,
            tool_choice="auto",   # Model decides whether a tool is needed
            temperature=0.6,
            max_tokens=300,
        )

        messaggio_assistente = risposta.choices[0].message

        if messaggio_assistente.tool_calls:
            # ── Tool path ──────────────────────────────────────────────────
            # Append the assistant's tool_call message so the next call has
            # full context of what was requested and what was returned.
            messaggi.append(messaggio_assistente)

            for tool_call in messaggio_assistente.tool_calls:
                nome_tool = tool_call.function.name
                argomenti = json.loads(tool_call.function.arguments)

                print(f"[TOOL CALL] {nome_tool}({argomenti})")
                risultato = esegui_tool(nome_tool, argomenti)
                print(f"[TOOL RESULT] {risultato}")

                messaggi.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": risultato,
                })

            # Generate a short spoken confirmation with the tool-use model.
            # MODEL_CHAT is not needed here — the reply is always brief.
            risposta_finale = client.chat.completions.create(
                model=MODEL_TOOLS,
                messages=messaggi,
                temperature=0.6,
                max_tokens=150,
            )
            return risposta_finale.choices[0].message.content.strip()

        # ── Conversational path ────────────────────────────────────────────
        # No tool was called — discard MODEL_TOOLS' plain-text reply and
        # re-submit the same messages to MODEL_CHAT for a richer response.
        risposta_chat = client.chat.completions.create(
            model=MODEL_CHAT,
            messages=messaggi,
            temperature=0.6,
            max_tokens=300,
        )
        return risposta_chat.choices[0].message.content.strip()

    except Exception as e:
        print(f"[LLM ERROR]: {e}")
        return "A processing error occurred."
