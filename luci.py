"""
luci.py — Smart light control via the Tuya LAN protocol.

Controls a single Tuya smart bulb ("Cami") directly over the local network
without going through the Tuya cloud. Requires the device ID, local IP, and
local key obtained from the Tuya / Smart Life app.

Security note: never commit real credentials. Store them in environment
variables or a .env file and load them at runtime.
"""

import tinytuya

# ---------------------------------------------------------------------------
# Device credentials — replace with your own values (do NOT commit these)
# ---------------------------------------------------------------------------

DEVICE_ID  = "bf6b0b999b130f0af7mrc3"
IP_ADDRESS = "192.168.0.183"
LOCAL_KEY  = "0P>5||/{SfrM:E7m"


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

def get_lampadina():
    """Create and return a configured BulbDevice instance.

    set_socketPersistent(False) closes the socket after each command so the
    connection does not linger and block subsequent calls.

    Returns:
        tinytuya.BulbDevice: Ready-to-use bulb device object.
    """
    d = tinytuya.BulbDevice(
        dev_id=DEVICE_ID,
        address=IP_ADDRESS,
        local_key=LOCAL_KEY,
        version=3.3,
    )
    # Close the socket after every command to avoid connection hangs.
    d.set_socketPersistent(False)
    return d


# ---------------------------------------------------------------------------
# Light control
# ---------------------------------------------------------------------------

def controlla_luce_cami(azione: str, colore: str = None, luminosita: int = None) -> str:
    """Control the Cami smart bulb: power, colour, and brightness.

    Args:
        azione (str): Command to execute.
            - "accendi"    → turn the light on
            - "spegni"     → turn the light off
            - "colore"     → set colour (requires `colore` argument)
            - "luminosita" → set brightness level (requires `luminosita` argument)
        colore (str | None): Colour name. Supported values:
            "rosso", "verde", "blu", "bianco", "giallo", "viola", "rosa", "arancione".
        luminosita (int | None): Brightness percentage (0–100).
            Internally scaled to Tuya's native range of 10–1000.

    Returns:
        str: Human-readable description of the result, or an error message.
    """
    azione = azione.lower()

    # Named colours mapped to RGB tuples.
    colori = {
        "rosso":    (255, 0,   0),
        "verde":    (0,   255, 0),
        "blu":      (0,   0,   255),
        "bianco":   (255, 255, 255),
        "giallo":   (255, 255, 0),
        "viola":    (128, 0,   128),
        "rosa":     (255, 105, 180),
        "arancione": (255, 165, 0),
    }

    try:
        lampadina = get_lampadina()

        if azione == "accendi":
            lampadina.turn_on()
            return "Cami light turned on."

        elif azione == "spegni":
            lampadina.turn_off()
            return "Cami light turned off."

        elif azione == "colore" and colore:
            # Fall back to white if the requested colour is not in the map.
            rgb = colori.get(colore.lower(), (255, 255, 255))
            lampadina.set_colour(rgb[0], rgb[1], rgb[2])
            return f"Cami light set to {colore}."

        elif azione == "luminosita" and luminosita is not None:
            # Tuya brightness range is 10–1000; scale from the 0–100 percentage.
            val = max(10, min(1000, int(luminosita * 10)))
            lampadina.set_brightness(val)
            return f"Cami brightness set to {luminosita}%."

        return "Invalid light command."

    except Exception as e:
        return f"Communication error with Cami light: {e}"
