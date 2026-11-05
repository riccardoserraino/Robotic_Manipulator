"""
Camera finta per testare il programma Estun di pick&place (6 slot).

Flusso del programma robot (una sola connessione per tutta l'esecuzione):
  1. SocketCreate verso la camera (porta 8192)
  2. "scheme CheckPresence"  -> risposta "OK"
  3. WHILE CONTINUA == 1:
       "runonce" -> stringa presenze + angoli
       TranStrToReal(risposta, ";", G:Dati_Array)
       cerca il primo slot presente (1..6), lo prende e torna in home
       se nessuno slot è presente -> CONTINUA = 0
  4. SocketClose

Formato della risposta a "runonce" (12 valori, 2 per slot):
  presenza1;angolo1;presenza2;angolo2;...;presenza6;angolo6
  - presenza: 1 = cilindro presente, 0 = assente
  - angolo:   orientamento della scanalatura in gradi, reale casuale in
              [-180, +180] se il cilindro è presente, 0 se assente
Es. "0;0;0;0;1;-73.42;0;0;0;0;0;0" = cilindro nello slot 3 a -73.42°
Sul robot: slot i -> presenza in Dati_Array[2*i-1], angolo in Dati_Array[2*i]

Come la camera reale, ogni risposta a "runonce" viene preceduta da "OK"
(ReturnExecuteOK di SCMVS): es. "OK0;0;0;0;1;-73.42;0;0;0;0;0;0".
Il programma robot (LeggiVisione) scarta i primi due caratteri se sono "OK".
Il prefisso si attiva/disattiva con PREFISSO_OK qui sotto o col comando "k".

Comandi alla richiesta di risposta (modalità manuale):
  1..6        -> cilindro solo in quello slot (angolo casuale)
  1,3,5       -> cilindri in più slot (il robot prende il primo)
  0           -> nessun cilindro (il robot esce dal WHILE)
  r           -> uno slot casuale
  v           -> VASSOIO: riempie slot casuali; a ogni foto toglie il cilindro
                 che il robot ha appena preso (il primo presente), finché il
                 vassoio è vuoto -> il robot riceve tutti 0 ed esce dal ciclo
  v1,3,5      -> vassoio con i cilindri negli slot indicati
  a           -> automatico: slot 1..6 a rotazione (il ciclo non termina mai)
  n           -> risposta "NG" (stringa non numerica)
  x           -> nessuna risposta (test del timeout di 10 s)
  k           -> attiva/disattiva il prefisso "OK" (poi richiede di nuovo lo slot)
  testo con ; -> inviato così com'è (es. "1;45.5;0;0")
"""

import random
import socket

PORTA = 8192          # deve coincidere con SocketCreate(...,8192,...)
N_SLOT = 6            # slot controllati dal FOR del programma robot
ANGOLO_MIN = -180.0
ANGOLO_MAX = 180.0
DECIMALI = 2          # cifre decimali dell'angolo (separatore ".")
TERMINATORE = ""      # se SocketReadStr non legge nulla, prova "\r" o "\r\n"
PREFISSO_OK = True    # True = antepone "OK" a ogni risposta a runonce (come la camera reale)

modo = "manuale"      # "manuale" | "auto" | "vassoio"
slot_auto = 0
vassoio = {}          # slot -> angolo dei cilindri ancora presenti


def angolo_casuale():
    return round(random.uniform(ANGOLO_MIN, ANGOLO_MAX), DECIMALI)


def stringa_da_dict(presenti):
    """presenti: dict slot -> angolo. Restituisce 'p1;a1;p2;a2;...'."""
    valori = []
    for i in range(1, N_SLOT + 1):
        if i in presenti:
            valori += ["1", f"{presenti[i]:.{DECIMALI}f}"]
        else:
            valori += ["0", "0"]
    return ";".join(valori)


def stringa_presenze(slot_presenti):
    return stringa_da_dict({s: angolo_casuale() for s in slot_presenti})


def leggi_slot(testo):
    """'1,3,5' -> {1,3,5}; None se non valido."""
    try:
        slot = {int(s) for s in testo.split(",") if s.strip()}
    except ValueError:
        return None
    if slot and all(1 <= s <= N_SLOT for s in slot):
        return slot
    return None


def avvia_vassoio(argomento):
    global modo, vassoio
    slot = leggi_slot(argomento) if argomento else None
    if slot is None:
        n = random.randint(1, N_SLOT)
        slot = set(random.sample(range(1, N_SLOT + 1), n))
    vassoio = {s: angolo_casuale() for s in sorted(slot)}
    modo = "vassoio"
    print(f"Vassoio caricato: " + ", ".join(f"slot {s} ({a}°)" for s, a in vassoio.items()))
    return prossima_vassoio()


def prossima_vassoio():
    """Foto del vassoio attuale; poi rimuove il cilindro che il robot prenderà."""
    global modo
    risposta = stringa_da_dict(vassoio)
    if vassoio:
        preso = min(vassoio)
        del vassoio[preso]
    else:
        print("Vassoio vuoto: il robot dovrebbe uscire dal ciclo. Torno in manuale.")
        modo = "manuale"
    return risposta


def prossima_auto():
    global slot_auto
    slot_auto = slot_auto % N_SLOT + 1
    return stringa_presenze({slot_auto})


def costruisci_risposta(scelta):
    """Traduce il comando digitato nella stringa da inviare (None = non rispondere)."""
    global modo
    if scelta == "x":
        return None
    if scelta == "n":
        return "NG"
    if scelta == "0":
        return stringa_presenze(set())
    if scelta == "r":
        return stringa_presenze({random.randint(1, N_SLOT)})
    if scelta.startswith("v"):
        return avvia_vassoio(scelta[1:].strip())
    if scelta == "a":
        modo = "auto"
        return prossima_auto()
    if ";" in scelta:
        return scelta
    slot = leggi_slot(scelta)
    if slot is not None:
        return stringa_presenze(slot)
    return scelta  # qualunque altra cosa viene inviata com'è


def descrivi(testo):
    """Stampa leggibile della risposta: slot presenti e relativo angolo."""
    if testo.startswith("OK"):
        testo = testo[2:]
    parti = testo.split(";")
    if len(parti) != 2 * N_SLOT:
        return ""
    righe = [f"slot {i // 2 + 1}: {parti[i + 1]}°"
             for i in range(0, len(parti), 2) if parti[i] == "1"]
    if not righe:
        return "  (nessun cilindro)"
    return "  (" + ", ".join(righe) + f" -> il robot prende lo slot {righe[0].split(':')[0][5:]})"


def invia(conn, testo):
    conn.sendall((testo + TERMINATORE).encode())
    print(f"Risposto: {testo!r}{descrivi(testo)}")


srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", PORTA))
srv.listen(1)
print(f"Camera finta in ascolto sulla porta {PORTA} ({N_SLOT} slot)...")

sessione = 0
while True:
    conn, addr = srv.accept()
    sessione += 1
    foto = 0
    print(f"\n=== Sessione {sessione}: robot connesso da {addr}")
    with conn:
        while True:
            try:
                data = conn.recv(1024)
            except ConnectionResetError:
                data = b""
            if not data:
                print(f"<<< Robot disconnesso (foto scattate: {foto})")
                break
            cmd = data.decode(errors="ignore").strip()
            print(f"\nRicevuto: {cmd!r}")

            if cmd.startswith("scheme"):
                invia(conn, "OK")
                continue

            if cmd.startswith("runonce"):
                foto += 1
                print(f"--- Foto {foto}")
                if modo == "auto":
                    risposta = prossima_auto()
                elif modo == "vassoio":
                    risposta = prossima_vassoio()
                else:
                    while True:
                        stato = "on" if PREFISSO_OK else "off"
                        scelta = input(f"Slot presenti [1-{N_SLOT} | 1,3 | 0 | r | v | v1,3 | a | n | x | k (OK: {stato})]: ").strip()
                        if scelta != "k":
                            break
                        PREFISSO_OK = not PREFISSO_OK
                        print(f"Prefisso OK {'attivato' if PREFISSO_OK else 'disattivato'}")
                    risposta = costruisci_risposta(scelta)
                if risposta is None:
                    print("Nessuna risposta (il robot andrà in timeout dopo 10 s)")
                    continue
                if PREFISSO_OK:
                    risposta = "OK" + risposta
                invia(conn, risposta)
                continue

            print("Comando non previsto, nessuna risposta")