import os
import json
from groq import Groq

# Inizializzazione client Groq
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Modello specificato su Groq
MODEL_NAME = "openai/gpt-oss-120b"
FILE_MEMORIA = "memoria.json"

def carica_memoria():
    """Carica i fatti persistenti dal file JSON."""
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
    """Aggiorna il file JSON preservando la struttura a categorie composte."""
    memoria_attuale = carica_memoria()
    memoria_attuale.update(nuovi_dati)
    with open(FILE_MEMORIA, "w", encoding="utf-8") as f:
        json.dump(memoria_attuale, f, ensure_ascii=False, indent=4)

def estrai_e_aggiorna_memoria(testo_utente):
    """
    Analizza il testo per estrarre informazioni personali dell'utente.
    Usa chiavi semantiche composte per evitare collisioni (es. pizza vs fiore).
    """
    prompt_estrazione = f"""
Sei un estrattore logico di dati per la memoria a lungo termine di un assistente.
Analizza il messaggio dell'utente: "{testo_utente}"

Se l'utente esprime una preferenza, un'abitudine o un fatto personale, estrailo in formato JSON con CHIAVI SEMANTICHE COMPOSTE E SPECIFICHE.
Regole per le chiavi:
- NON usare chiavi generiche come 'preferito', 'cibo', 'nome'.
- USA sempre il prefisso dell'oggetto: ad esempio 'pizza_preferita', 'fiore_preferito', 'film_preferito', 'colore_preferito'.
- Se non ci sono informazioni personali da salvare, restituisci solo un JSON vuoto: {{}}

Rispondi ESCLUSIVAMENTE con il blocco JSON valido, senza testo o markdown aggiuntivo.
"""
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt_estrazione}],
            temperature=0.1
        )
        risposta_testo = completion.choices[0].message.content.strip()
        if risposta_testo.startswith("```json"):
            risposta_testo = risposta_testo[7:-3].strip()
        elif risposta_testo.startswith("```"):
            risposta_testo = risposta_testo[3:-3].strip()
            
        dati = json.loads(risposta_testo)
        if dati and isinstance(dati, dict):
            salva_memoria(dati)
            print(f"[MEMORIA AGGIORNATA]: {dati}")
    except Exception as e:
        print(f"[ERRORE AGGIORNAMENTO MEMORIA]: {e}")

def trascrivi_audio(file_path):
    """Trascrive il file audio usando Whisper su Groq."""
    try:
        with open(file_path, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(file_path), file.read()),
                model="whisper-large-v3",
                response_format="json"
            )
            return transcription.text.strip()
    except Exception as e:
        print(f"[ERRORE TRASCRIZIONE]: {e}")
        return ""

def chiedi_a_bob(testo_utente, cronologia=None):
    """
    Genera la risposta di Bob integrando memoria a lungo termine,
    cronologia a breve termine e uno spirito imprenditoriale misurato.
    """
    estrai_e_aggiorna_memoria(testo_utente)
    
    memoria_fatti = carica_memoria()
    stringa_memoria = json.dumps(memoria_fatti, ensure_ascii=False)

    system_prompt = f"""
Sei Bob, un assistente desktop esecutivo, bilingue (italiano e inglese) e dotato di uno spiccato spirito imprenditoriale.

Le tue caratteristiche fondamentali e linee guida di risposta:
1. **Sii diretto e naturale:** Rispondi alle domande di cortesia o chiuse (es. "Come stai?", "Tutto bene?") in modo sintetico e naturale (es. "Tutto bene, grazie"), senza MAI aggiungere domande forzate o non necessarie.
2. **Proattività misurata:** Fai domande SOLO se il contesto lo richiede veramente per brainstorming o chiarimenti (es. se l'utente chiede "Hai delle idee?", puoi rispondere "Su che argomento?"). Non chiudere mai con una domanda a meno che non sia indispensabile.
3. Se e solo se poni una domanda reale, chiudi l'intervento con un punto interrogativo (?), in questo modo il sistema saprà di dover lasciare aperto il microfono.
4. **Mentalità orientata all'azione:** Quando opportuno e richiesto, sii incisivo e cerca sempre il risvolto pratico o l'opportunità strategica.
5. **Memoria fattuale a lungo termine:**
Ecco i dati noti sull'utente:
{stringa_memoria}

Regole operative:
- Distingui con precisione le entità omonime (es. 'pizza_preferita' è distinta da 'fiore_preferito').
- Se un dato non è presente nella memoria, dichiara onestamente di non saperlo.
- Rispondi nella stessa lingua utilizzata dall'utente nel suo ultimo comando.
"""

    messaggi = [{"role": "system", "content": system_prompt}]
    
    if cronologia:
        messaggi.extend(cronologia)
    else:
        messaggi.append({"role": "user", "content": testo_utente})

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messaggi,
            temperature=0.6,
            max_tokens=300
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ERRORE LLM]: {e}")
        return "Si è verificato un errore di elaborazione."