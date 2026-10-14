"""
calendario.py — macOS Calendar integration.

Reading events uses Swift + EventKit via subprocess.
EventKit's predicateForEvents(withStart:end:) returns ALL occurrences of
recurring events that fall in the requested date range — something AppleScript
cannot do, because its 'whose start date' filter matches only the master event's
original start date, not the individual recurrence instances.

Creating events still uses AppleScript (simpler, no compilation step needed).
"""

import subprocess
import tempfile
import os
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Swift EventKit helper — reads events for a given date
# ---------------------------------------------------------------------------

def _swift_leggi_eventi(anno: int, mese: int, giorno: int) -> Optional[str]:
    """Run a Swift script that queries EventKit for events on a specific date.

    EventKit's predicate returns every occurrence of recurring events that
    falls within the 24-hour window, fixing the AppleScript limitation where
    recurring events are invisible after their original start date.

    The script is written to a temp file and run with `swift`. Compilation
    takes 2-4 seconds on first run; subsequent runs may be faster.

    Args:
        anno: 4-digit year.
        mese: Month (1–12).
        giorno: Day of month.

    Returns:
        Newline-separated event strings, or None if Swift/EventKit fails.
    """
    swift_code = f"""
import Foundation
import EventKit

let store = EKEventStore()
let sema = DispatchSemaphore(value: 0)

// Request calendar access — completes immediately if already granted.
if #available(macOS 14.0, *) {{
    store.requestFullAccessToEvents {{ _, _ in sema.signal() }}
}} else {{
    store.requestAccess(to: .event) {{ _, _ in sema.signal() }}
}}
sema.wait()

// Build the start/end NSDate for the target day.
var comps = DateComponents()
comps.year = {anno}; comps.month = {mese}; comps.day = {giorno}
comps.hour = 0; comps.minute = 0; comps.second = 0
let cal = Calendar.current
guard let start = cal.date(from: comps),
      let end   = cal.date(byAdding: .day, value: 1, to: start) else {{
    print("Data non valida"); exit(1)
}}

// predicateForEvents returns ALL occurrences (including recurring ones).
let pred   = store.predicateForEvents(withStart: start, end: end, calendars: nil)
let events = store.events(matching: pred).sorted {{ $0.startDate < $1.startDate }}

if events.isEmpty {{
    print("Nessun evento il {anno}-{mese:02d}-{giorno:02d}.")
}} else {{
    let fmt = DateFormatter()
    fmt.dateFormat = "HH:mm"
    for e in events {{
        let title = e.title ?? "Senza titolo"
        if e.isAllDay {{
            print("\\(title) (tutto il giorno)")
        }} else {{
            print("\\(title) alle \\(fmt.string(from: e.startDate))")
        }}
    }}
}}
"""
    # Write script to a temp file — swift requires a file path, not stdin.
    with tempfile.NamedTemporaryFile(suffix=".swift", mode="w", delete=False) as f:
        f.write(swift_code)
        tmp = f.name

    try:
        result = subprocess.run(
            ["swift", tmp],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None
    except Exception:
        return None
    finally:
        os.unlink(tmp)


# ---------------------------------------------------------------------------
# Public read functions
# ---------------------------------------------------------------------------

def leggi_eventi_data(data: str) -> str:
    """Read all events (including recurring ones) for a specific date.

    Tries Swift EventKit first; falls back to AppleScript if Swift fails.

    Args:
        data (str): Target date in 'YYYY-MM-DD' format.

    Returns:
        str: Event list, a no-events message, or an error string.
    """
    try:
        dt = datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        return f"Formato data non valido: {data}"

    # Primary path: Swift EventKit (handles recurring events).
    risultato = _swift_leggi_eventi(dt.year, dt.month, dt.day)
    if risultato:
        return risultato

    # Fallback: AppleScript (misses recurring events whose master date is past).
    return _applescript_leggi_eventi(dt.year, dt.month, dt.day)


def leggi_eventi_oggi() -> str:
    """Read all events (including recurring ones) for today.

    Returns:
        str: Event list, a no-events message, or an error string.
    """
    oggi = datetime.now()
    risultato = _swift_leggi_eventi(oggi.year, oggi.month, oggi.day)
    if risultato:
        return risultato
    return _applescript_leggi_eventi(oggi.year, oggi.month, oggi.day)


# ---------------------------------------------------------------------------
# AppleScript fallback — non-recurring events only
# ---------------------------------------------------------------------------

def _applescript_leggi_eventi(anno: int, mese: int, giorno: int) -> str:
    """Read events via AppleScript. Does NOT return recurring event occurrences
    whose original start date is before the target date.

    Used only as a fallback when Swift is unavailable.
    """
    script = f"""
    set targetDate to current date
    set year of targetDate to {anno}
    set month of targetDate to {mese}
    set day of targetDate to {giorno}
    set hours of targetDate to 0
    set minutes of targetDate to 0
    set seconds of targetDate to 0
    set fineGiorno to targetDate + (24 * hours)

    tell application "Calendar"
        set output to ""
        repeat with cal in every calendar
            try
                set listaEventi to (every event of cal whose start date is greater than or equal to targetDate and start date is less than fineGiorno)
                repeat with evt in listaEventi
                    try
                        set h to hours of (start date of evt) as integer
                        set m to minutes of (start date of evt) as integer
                        set hStr to text -2 thru -1 of ("0" & (h as string))
                        set mStr to text -2 thru -1 of ("0" & (m as string))
                        set output to output & (summary of evt) & " alle " & hStr & ":" & mStr & "; "
                    on error
                        set output to output & (summary of evt) & " (tutto il giorno); "
                    end try
                end repeat
            on error
            end try
        end repeat
        if output is "" then
            return "Nessun evento."
        else
            return output
        end if
    end tell
    """
    try:
        res = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, check=True,
        )
        return res.stdout.strip()
    except Exception as e:
        return f"Errore nella lettura del calendario: {e}"


# ---------------------------------------------------------------------------
# Create event — AppleScript (no recurring-event complexity needed)
# ---------------------------------------------------------------------------

def crea_evento(titolo: str, data_ora: str, durata_minuti: int = 60) -> str:
    """Create a new event in the default macOS Calendar.

    Each date component is set individually to avoid locale-dependent
    AppleScript date string parsing failures.

    Args:
        titolo (str): Event title.
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
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, check=True,
        )
        return f"Evento '{titolo}' aggiunto per il {data_ora}."
    except Exception as e:
        return f"Errore nella creazione dell'evento: {e}"
