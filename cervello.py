"""
cervello.py — Bob's brain: LLM responses, tool calling, long-term memory, and Whisper transcription.

Tool calling lets the LLM trigger real actions (calendar events, light control) by
returning a structured function call instead of plain text. The flow is:
  1. Send user message + tool definitions to Groq.
  2. If the model returns a tool_call, execute the matching Python function.
  3. Send the function result back to get a natural-language confirmation.
  4. Speak the confirmation.
"""

import os
import json
from datetime import datetime, timedelta
from groq import Groq

from calendario import crea_evento, leggi_eventi_oggi
from luci import controlla_luce_cami

# ---------------------------------------------------------------------------
# Client & model configuration
# ---------------------------------------------------------------------------

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL_NAME = "llama3-groq-70b-8192-tool-use-preview"  # Tool-use capable model on Groq
FILE_MEMORIA = "memoria.json"

# ---------------------------------------------------------------------------
# Tool definitions (passed to the LLM so it knows what actions are available)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "crea_evento_calendario",
            "description": (
                "Creates an event or reminder in the user's macOS Calendar. "
                "Use this whenever the user asks to add, schedule, set, or remind "
                "something at a specific time or date. "
                "Today's date is always injected in the system prompt — use it to "
                "resolve relative expressions like 'tomorrow', 'next Monday', 'in 2 hours'."
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
                        "description": "Duration in minutes. Default to 60 if not specified.",
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
            "description": "Returns all events scheduled for today. Use when the user asks what's on today, what they have planned, or about their schedule.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "controlla_luce",
            "description": "Controls the smart light named 'Cami'. Use for any request to turn it on/off, change its colour, or adjust brightness.",
            "parameters": {
                "type": "object",
                "properties": {
                    "azione": {
                        "type": "string",
                        "enum": ["accendi", "spegni", "colore", "luminosita"],
                        "description": "Action to perform.",
                    },
                    "colore": {
                        "type": "string",
                        "enum": ["rosso", "verde", "blu", "bianco", "giallo", "viola", "rosa", "arancione"],
                        "description": "Colour name — required only when azione is 'colore'.",
                    },
                    "luminosita": {
                        "type": "integer",
                        "description": "Brightness percentage (0–100) — required only when azione is 'luminosita'.",
                    },
                },
                "required": ["azione"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool dispatcher — maps LLM tool names to Python functions
# ---------------------------------------------------------------------------

def esegui_tool(nome_tool: str, argomenti: dict) -> str:
    """Execute the Python function that corresponds to a tool call from the LLM.

    Args:
        nome_tool (str): Tool name as returned by the LLM (must match TOOLS definitions).
        argomenti (dict): Parsed arguments from the LLM's tool_call.

    Returns:
        str: Human-readable result of the function, passed back to the LLM.
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

def carica_memoria():
    """Load persistent user facts from the JSON memory file.

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
    """Merge new facts into the memory file without overwriting existing keys.

    Args:
        nuovi_dati (dict): Key-value pairs to add or update.
    """
    memoria_attuale = carica_memoria()
    memoria_attuale.update(nuovi_dati)
    with open(FILE_MEMORIA, "w", encoding="utf-8") as f:
        json.dump(memoria_attuale, f, ensure_ascii=False, indent=4)


def estrai_e_aggiorna_memoria(testo_utente):
    """Extract personal facts from the user's message and persist them.

    Uses compound semantic keys (e.g. 'pizza_preferita') to avoid collisions.
    Returns silently on failure — a missed extraction is non-fatal.

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

def trascrivi_audio(file_path):
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
# LLM response with tool calling
# ---------------------------------------------------------------------------

def chiedi_a_bob(testo_utente, cronologia=None):
    """Generate Bob's response, executing tool calls when the LLM requests them.

    Flow:
      1. Send messages + TOOLS to Groq.
      2. If the response contains a tool_call, run the matching Python function.
      3. Append the tool result to the messages and call the LLM again for a
         natural-language confirmation the user can hear.
      4. Return the final text response.

    Today's date is injected into the system prompt so the LLM can correctly
    resolve relative date expressions ("tomorrow", "next week", "in 2 hours").

    Args:
        testo_utente (str): The user's transcribed command.
        cronologia (list[dict] | None): Conversation history as
            {"role": ..., "content": ...} dicts.

    Returns:
        str: Bob's spoken response text.
    """
    estrai_e_aggiorna_memoria(testo_utente)

    memoria_fatti = carica_memoria()
    stringa_memoria = json.dumps(memoria_fatti, ensure_ascii=False)

    # Inject today's full date and time so the LLM can resolve relative expressions.
    ora_attuale = datetime.now().strftime("%Y-%m-%d %H:%M")
    domani = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    system_prompt = f"""
You are Bob, a bilingual (Italian and English) executive desktop assistant
with a sharp entrepreneurial mindset.

Current date and time: {ora_attuale}
Tomorrow's date: {domani}

Core behaviour guidelines:
1. **Be direct and natural:** Answer short or closed questions concisely.
   Never force unnecessary follow-up questions.
2. **Use tools proactively:** When the user asks to create an event, reminder,
   or todo — always call crea_evento_calendario. Don't ask for confirmation first,
   just do it and report back. Resolve relative dates using the current date above.
3. **Measured proactivity:** Ask questions ONLY when context genuinely requires it.
   If you ask a real question, end your turn with a question mark (?).
4. **Action-oriented mindset:** Be decisive and look for the practical angle.
5. **Long-term factual memory:**
   Known facts about the user:
   {stringa_memoria}

Operational rules:
- Distinguish precisely between similar-named memory keys.
- If a fact is not in memory, honestly say you don't know.
- Reply in the same language the user used in their last message.
- After executing a tool, confirm what you did in one short sentence.
"""

    messaggi = [{"role": "system", "content": system_prompt}]

    if cronologia:
        messaggi.extend(cronologia)
    else:
        messaggi.append({"role": "user", "content": testo_utente})

    try:
        # --- First LLM call: may return a tool_call instead of text ---
        risposta = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messaggi,
            tools=TOOLS,
            tool_choice="auto",   # Let the model decide when to use tools
            temperature=0.6,
            max_tokens=300,
        )

        messaggio_assistente = risposta.choices[0].message

        # --- Check for tool calls ---
        if messaggio_assistente.tool_calls:
            # Append the assistant's tool_call message to the history.
            messaggi.append(messaggio_assistente)

            # Execute each requested tool and collect results.
            for tool_call in messaggio_assistente.tool_calls:
                nome_tool = tool_call.function.name
                argomenti = json.loads(tool_call.function.arguments)

                print(f"[TOOL CALL]: {nome_tool}({argomenti})")
                risultato = esegui_tool(nome_tool, argomenti)
                print(f"[TOOL RESULT]: {risultato}")

                # Append the tool result so the LLM can reference it.
                messaggi.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": risultato,
                })

            # --- Second LLM call: convert tool result to spoken confirmation ---
            risposta_finale = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messaggi,
                temperature=0.6,
                max_tokens=150,   # Confirmation should be brief
            )
            return risposta_finale.choices[0].message.content.strip()

        # No tool call — plain text response.
        return messaggio_assistente.content.strip()

    except Exception as e:
        print(f"[LLM ERROR]: {e}")
        return "A processing error occurred."
