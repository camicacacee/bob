import subprocess
from datetime import datetime

def leggi_eventi_oggi() -> str:
    """Legge gli eventi in programma per oggi dall'app Calendario di macOS."""
    script = '''
    set oggi to current date
    set inizioGiorno to oggi - (time of oggi)
    set fineGiorno to inizioGiorno + (24 * hours)
    
    tell application "Calendar"
        set output to ""
        set listaEventi to (every event of every calendar whose start date is greater than or equal to inizioGiorno and start date is less than fineGiorno)
        repeat with evt in listaEventi
            set output to output & (summary of evt) & " alle " & (time string of (start date of evt)) & "; "
        end repeat
        if output is "" then
            return "Nessun impegno in programma per oggi."
        else
            return output
        end if
    end tell
    '''
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception as e:
        return f"Errore nella lettura del calendario: {e}"

def crea_evento(titolo: str, data_ora: str, durata_minuti: int = 60) -> str:
    """
    Crea un evento nel calendario predefinito.
    data_ora deve essere nel formato 'YYYY-MM-DD HH:MM' (es. '2026-09-14 15:30').
    """
    try:
        dt = datetime.strptime(data_ora, "%Y-%m-%d %H:%M")
        script = f'''
        set startDate to current date
        set year of startDate to {dt.year}
        set month of startDate to {dt.month}
        set day of startDate to {dt.day}
        set hours of startDate to {dt.hour}
        set minutes of startDate to {dt.minute}
        set seconds of startDate to 0
        set endDate to startDate + ({durata_minuti} * minutes)

        tell application "Calendar"
            tell calendar 1
                make new event with properties {{summary:"{titolo}", start date:startDate, end date:endDate}}
            end tell
        end tell
        '''
        subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True)
        return f"Evento '{titolo}' aggiunto per il {data_ora}."
    except Exception as e:
        return f"Errore nella creazione dell'evento: {e}"