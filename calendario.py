"""
calendario.py — macOS Calendar integration via AppleScript.

Reads today's events and creates new ones by driving the Calendar app
through osascript. Requires macOS and the Calendar privacy permission
(System Settings → Privacy & Security → Calendars).
"""

import subprocess
from datetime import datetime


def leggi_eventi_oggi() -> str:
    """Read all events scheduled for today from macOS Calendar.

    Queries the Calendar app via AppleScript for events whose start time
    falls between midnight and midnight of the current day.

    Returns:
        str: Comma-separated list in the format "Title at HH:MM:SS; ...",
             or "No events scheduled for today." if the calendar is empty.
             Returns an error string if AppleScript execution fails.
    """
    script = '''
    set oggi to current date
    set inizioGiorno to oggi - (time of oggi)
    set fineGiorno to inizioGiorno + (24 * hours)

    tell application "Calendar"
        set output to ""
        set listaEventi to (every event of every calendar whose start date is greater than or equal to inizioGiorno and start date is less than fineGiorno)
        repeat with evt in listaEventi
            set output to output & (summary of evt) & " at " & (time string of (start date of evt)) & "; "
        end repeat
        if output is "" then
            return "No events scheduled for today."
        else
            return output
        end if
    end tell
    '''
    try:
        res = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception as e:
        return f"Error reading calendar: {e}"


def crea_evento(titolo: str, data_ora: str, durata_minuti: int = 60) -> str:
    """Create a new event in the default macOS Calendar.

    Builds an AppleScript that sets the event's start and end dates by
    decomposing the parsed datetime into individual AppleScript date fields,
    which is the most reliable way to avoid locale-dependent date parsing.

    Args:
        titolo (str): Event title / summary.
        data_ora (str): Start time in "YYYY-MM-DD HH:MM" format
                        (e.g. "2026-09-14 15:30").
        durata_minuti (int): Event duration in minutes. Defaults to 60.

    Returns:
        str: Confirmation message on success, or an error string on failure.
    """
    try:
        dt = datetime.strptime(data_ora, "%Y-%m-%d %H:%M")

        # AppleScript does not handle ISO date strings reliably across locales,
        # so each date component is set individually via property assignment.
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
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=True,
        )
        return f"Event '{titolo}' added for {data_ora}."
    except Exception as e:
        return f"Error creating event: {e}"
