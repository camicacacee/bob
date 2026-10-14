import tinytuya

# Parametri lampadina Cami
DEVICE_ID = "bf6b0b999b130f0af7mrc3"
IP_ADDRESS = "192.168.0.183"
LOCAL_KEY = "0P>5||/{SfrM:E7m"

def get_lampadina():
    """Inizializza la connessione alla lampadina Cami."""
    d = tinytuya.BulbDevice(
        dev_id=DEVICE_ID,
        address=IP_ADDRESS,
        local_key=LOCAL_KEY,
        version=3.3
    )
    d.set_socketPersistent(False)  # Chiude il socket dopo il comando per evitare blocchi
    return d

def controlla_luce_cami(azione: str, colore: str = None, luminosita: int = None) -> str:
    """Controlla la lampadina 'Cami': accensione, spegnimento, colore e intensità."""
    azione = azione.lower()
    try:
        lampadina = get_lampadina()

        if azione == "accendi":
            lampadina.turn_on()
            return "Luce Cami accesa."
            
        elif azione == "spegni":
            lampadina.turn_off()
            return "Luce Cami spenta."
            
        elif azione == "colore" and colore:
            colori = {
                "rosso": (255, 0, 0),
                "verde": (0, 255, 0),
                "blu": (0, 0, 255),
                "bianco": (255, 255, 255),
                "giallo": (255, 255, 0),
                "viola": (128, 0, 128),
                "rosa": (255, 105, 180),
                "arancione": (255, 165, 0)
            }
            rgb = colori.get(colore.lower(), (255, 255, 255))
            lampadina.set_colour(rgb[0], rgb[1], rgb[2])
            return f"Luce Cami impostata su colore {colore}."
            
        elif azione == "luminosita" and luminosita is not None:
            val = max(10, min(1000, int(luminosita * 10)))
            lampadina.set_brightness(val)
            return f"Luminosità di Cami regolata al {luminosita}%."
            
        return "Comando per la luce non valido."
        
    except Exception as e:
        return f"Errore di comunicazione con la luce Cami: {e}"