"""
calendario.py — macOS Calendar integration via AppleScript.

Reads and creates events in the macOS Calendar app via osascript.
Requires macOS and Calendar privacy permission
(System Settings → Privacy & Security → Calendars).

Time formatting note: time string of (start date of evt) uses the system's
12h/24h preference and can be off by DST offsets. Instead, hours and minutes
are extracted as integers and zero-padded manually to guarantee HH:MM 24h output.
"""

import subprocess
from datetime import datetime


# ---------------------------------------------------------------------------
# Shared AppleScript helper — formats event start time as HH:MM (24h)
# ---------------------------------------------------------------------------

# Inlined into each script string so osascript has no external dependencies.
_FMT_TIME = """
set h to hours of (start date of evt) as integer
set m to minutes of (start date of evt) as integer
set hStr to text -2 thru -1 of ("0" & (h as string))
set mStr to text -2 thru -1 of ("0" & (m as string))
set oraInizio to hStr & ":" & mStr
"""

# Inner loop body shared by both read functions.
# Tries to extract HH:MM; falls back to "(all day)" for all-day events.
_LOOP_BODY = """
repeat with evt in listaEventi
    try
        set h to hours of (start date of evt) as integer
        set m to minutes of (start date of evt) as integer
        set hStr to text -2 thru -1 of ("0" & (h as string))
        set mStr to text -2 thru -1 of ("0" & (m as string))
        set output to output & (summary of evt) & " alle " & hStr & ":" & mStr & "; "
    on error
        -- all-day event: no time component available
        set output to output & (summary of evt) & " (tutto il giorno); "
    end try
end repeat
"""


# ---------------------------------------------------------------------------
# Read functions
# ---------------------------------------------------------------------------

def leggi_eventi_data(data: str) -> str:
    """Read all events for a specific date from macOS Calendar.

    Args:
        data (str): Target date in 'YYYY-MM-DD' format.

    Returns:
        str: Events list as "Title alle HH:MM; ...", a no-events message,
             or an error string on failure.
    """
    try:
        dt = datetime.strptime(data, "%Y-%m-%d")
        script = f"""
        set targetDate to current date
        set year of targetDate to {dt.year}
        set month of targetDate to {dt.month}
        set day of targetDate to {dt.day}
        set hours of targetDate to 0
        set minutes of targetDate to 0
        set seconds of targetDate to 0
        set fineGiorno to targetDate + (24 * hours)

        tell application "Calendar"
            set output to ""
            repeat with cal in every calendar
                try
                    set listaEventi to (every event of cal whose start date is greater than or equal to targetDate and start date is less than fineGiorno)
                    {_LOOP_BODY}
                on error
                    -- skip unreadable or subscribed calendars
                end try
            end repeat
            if output is "" then
                return "Nessun evento il {data}."
            else
                return output
            end if
        end tell
        """
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception as e:
        return f"Errore nella lettura del calendario per {data}: {e}"


def leggi_eventi_oggi() -> str:
    """Read all events scheduled for today from macOS Calendar.

    Returns:
        str: Events list as "Title alle HH:MM; ...", a no-events message,
             or an error string on failure.
    """
    script = f"""
    set oggi to current date
    set inizioGiorno to oggi - (time of oggi)
    set fineGiorno to inizioGiorno + (24 * hours)

    tell application "Calendar"
        set output to ""
        repeat with cal in every calendar
            try
                set listaEventi to (every event of cal whose start date is greater than or equal to inizioGiorno and start date is less than fineGiorno)
                {_LOOP_BODY}
            on error
                -- skip unreadable or subscribed calendars
            end try
        end repeat
        if output is "" then
            return "Nessun impegno in programma per oggi."
        else
            return output
        end if
    end tell
    """
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception as e:
        return f"Errore nella lettura del calendario: {e}"


# ---------------------------------------------------------------------------
# Create event
# ---------------------------------------------------------------------------

def crea_evento(titolo: str, data_ora: str, durata_minuti: int = 60) -> str:
    """Create a new event in the default macOS Calendar.

    Each date component is set individually to avoid locale-dependent
    AppleScript date string parsing failures.

    Args:
        titolo (str): Event title / summary.
        data_ora (str): Start time in 'YYYY-MM-DD HH:MM' format.
        durata_minuti (int): Duration in minutes (default 60).

    Returns:
        str: Confirmation message, or an error string on failure.
    """
    try:
        dt = datetime.strptime(data_ora, "%Y-%m-%d %H:%M")
        script = f"""
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
        """
        subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True)
        return f"Evento '{titolo}' aggiunto per il {data_ora}."
    except Exception as e:
        return f"Errore nella creazione dell'evento: {e}"
