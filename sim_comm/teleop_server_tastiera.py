"""
Server di teleoperazione da tastiera per il programma Estun Teleop_Gesti.erp.

Simula il PC che in futuro riconoscera' i gesti della mano: per ora il
comando corrente si sceglie da tastiera. Protocollo e programma robot
restano gli stessi quando arrivera' MediaPipe.

Flusso (una sola connessione per tutta l'esecuzione del programma robot):
  1. il robot fa SocketCreate verso questo PC (porta 9500: la 9000 e' occupata dall'Estun Editor)
  2. WHILE TELEOP == 1:
       robot -> "REQ"
       PC    -> una parola (il comando corrente), senza terminatore
       il robot la confronta con strcmp ed esegue un passo (MovL con blending)
  3. con "quit" il robot esce dal ciclo, chiude il socket e torna in home

Parole valide:
  left right forward backward up down  -> un passo di R_PASSO mm in terna base
  stop                                 -> fermo
  quit                                 -> fine teleoperazione
  open / close                         -> pinza aperta / chiusa

La risposta parte automaticamente a ogni REQ: da tastiera si cambia solo il
comando corrente. Di default una direzione vale SOLO MENTRE IL TASTO E'
PREMUTO: al rilascio il comando torna stop (la pressione si legge dalla
console, il rilascio dallo stato fisico del tasto con GetAsyncKeyState).
Con --persistente il comando resta attivo finche' non si preme un altro
tasto (comportamento precedente: serve spazio per fermarsi).

Comandi da tastiera:
  w / freccia su        -> forward
  s / freccia giu'      -> backward
  a / freccia sinistra  -> left
  d / freccia destra    -> right
  r                     -> up
  f                     -> down
  spazio                -> stop (serve solo con --persistente)
  o / c                 -> open / close (inviato una sola volta, poi stop)
  p                     -> modalita' passo singolo on/off: ogni tasto di
                           direzione vale per UNA sola REQ, poi torna stop
  q                     -> quit alla REQ successiva, poi chiude lo script
  h                     -> questo aiuto

Uso:
  python teleop_server_tastiera.py
  python teleop_server_tastiera.py --log prova.csv
  python teleop_server_tastiera.py --persistente
  python teleop_server_tastiera.py --terminatore "\\r\\n" --verbose
"""

import argparse
import codecs
import csv
import ctypes
import msvcrt
import select
import socket
import time
from datetime import datetime

# Tasto -> parola inviata al robot
TASTI = {
    "w": "forward",
    "s": "backward",
    "a": "left",
    "d": "right",
    "r": "up",
    "f": "down",
    " ": "stop",
    "o": "open",
    "c": "close",
}
# Frecce: msvcrt restituisce '\xe0' (o '\x00') seguito da questo codice
FRECCE = {
    "H": "forward",   # su
    "P": "backward",  # giu'
    "K": "left",      # sinistra
    "M": "right",     # destra
}
# Codice tasto virtuale di Windows di ogni tasto di direzione (per sentire il rilascio)
VK = {
    "w": 0x57, "s": 0x53, "a": 0x41, "d": 0x44, "r": 0x52, "f": 0x46,
    "H": 0x26, "P": 0x28, "K": 0x25, "M": 0x27,   # frecce su, giu', sinistra, destra
}
_user32 = ctypes.WinDLL("user32")
_user32.GetAsyncKeyState.restype = ctypes.c_short
DIREZIONI = {"left", "right", "forward", "backward", "up", "down"}
MONOUSO = {"open", "close"}   # inviati a una sola REQ, poi si torna a stop
INTERVALLO_RIASSUNTO = 1.0    # [s] ogni quanto riassumere le REQ con risposta stop


def leggi_argomenti():
    ap = argparse.ArgumentParser(description="Server di teleoperazione da tastiera (Estun)")
    ap.add_argument("--port", type=int, default=9500,
                    help="porta TCP, uguale a I_Porta_PC sul robot (default 9500)")
    ap.add_argument("--terminatore", default="",
                    help='terminatore dopo ogni risposta: "", "\\r", "\\n" o "\\r\\n" (default nessuno)')
    ap.add_argument("--log", default=None,
                    help="file CSV con una riga per ogni REQ (timestamp, delta ms, comando)")
    ap.add_argument("--verbose", action="store_true",
                    help="stampa tutte le REQ, anche quelle con risposta stop")
    ap.add_argument("--persistente", action="store_true",
                    help="la direzione resta attiva anche dopo il rilascio del tasto (fermarsi con spazio)")
    args = ap.parse_args()
    # "\\r\\n" scritto da riga di comando -> "\r\n" vero
    args.terminatore = codecs.decode(args.terminatore, "unicode_escape")
    return args


def ora():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def stampa_aiuto():
    print(__doc__.split("Comandi da tastiera:")[1].split("Uso:")[0].rstrip())


class Stato:
    """Comando corrente e modalita' scelti da tastiera."""

    def __init__(self, persistente=False):
        self.persistente = persistente
        self.tasto_tenuto = None    # codice VK del tasto di direzione premuto (None = nessuno)
        self.comando = "stop"
        self.una_volta = False      # True = il comando vale per una sola REQ
        self.passo_singolo = False
        self.quit_richiesto = False
        self.quit_inviato = False

    def descrivi(self):
        modo = "passo singolo" if self.passo_singolo else "continua"
        if not self.persistente:
            modo += ", solo a tasto premuto"
        return f"Comando corrente: {self.comando} (modalita' {modo})"

    def imposta(self, comando):
        self.comando = comando
        self.una_volta = comando in MONOUSO or (self.passo_singolo and comando in DIREZIONI)
        print(f"[{ora()}] {self.descrivi()}")

    def risposta(self):
        """Parola da mandare alla REQ corrente (e aggiorna lo stato)."""
        if self.quit_richiesto:
            self.quit_inviato = True
            return "quit"
        parola = self.comando
        if self.una_volta:
            self.comando = "stop"
            self.una_volta = False
        return parola


def tasto_giu(vk):
    """True se il tasto e' fisicamente premuto in questo momento."""
    return bool(_user32.GetAsyncKeyState(vk) & 0x8000)


def direzione_premuta(stato, comando, vk):
    """Pressione (o ripetizione automatica) di un tasto di direzione."""
    if stato.persistente:
        stato.imposta(comando)
        return
    if stato.tasto_tenuto == vk:
        return  # ripetizione automatica del tasto gia' tenuto: niente di nuovo
    stato.tasto_tenuto = vk
    stato.imposta(comando)


def controlla_rilascio(stato):
    """Senza --persistente: al rilascio del tasto di direzione si torna a stop."""
    if stato.persistente or stato.tasto_tenuto is None:
        return
    if tasto_giu(stato.tasto_tenuto):
        return
    stato.tasto_tenuto = None
    if stato.comando in DIREZIONI:
        stato.imposta("stop")


def gestisci_tasto(stato, conn):
    """Legge un tasto (senza bloccare). Restituisce True se lo script deve uscire."""
    tasto = msvcrt.getwch()
    if tasto in ("\xe0", "\x00"):
        codice = msvcrt.getwch()
        if codice in FRECCE:
            direzione_premuta(stato, FRECCE[codice], VK[codice])
        return False
    tasto = tasto.lower()
    if tasto in VK:
        direzione_premuta(stato, TASTI[tasto], VK[tasto])
    elif tasto in TASTI:
        stato.tasto_tenuto = None
        stato.imposta(TASTI[tasto])
    elif tasto == "p":
        stato.passo_singolo = not stato.passo_singolo
        # il comando gia' attivo resta continuo: torna stop per evitare sorprese
        stato.imposta("stop")
    elif tasto == "q":
        if conn is None:
            print("Quit: nessun robot connesso, chiudo.")
            return True
        stato.quit_richiesto = True
        print(f"[{ora()}] Quit: invio 'quit' alla prossima REQ, poi chiudo.")
    elif tasto == "h":
        stampa_aiuto()
    return False


class Registro:
    """Stampa a terminale e log CSV delle REQ."""

    def __init__(self, verbose, percorso_log):
        self.verbose = verbose
        self.n_req = 0
        self.t_prec = None
        self.stop_contati = 0
        self.t_riassunto = time.perf_counter()
        self.file_log = None
        self.csv = None
        if percorso_log:
            self.file_log = open(percorso_log, "w", newline="")
            self.csv = csv.writer(self.file_log)
            self.csv.writerow(["timestamp", "n_req", "delta_ms", "comando"])
            print(f"Log CSV: {percorso_log}")

    def req(self, parola):
        adesso = time.perf_counter()
        delta = (adesso - self.t_prec) * 1000 if self.t_prec is not None else 0.0
        self.t_prec = adesso
        self.n_req += 1
        if self.csv:
            self.csv.writerow([datetime.now().isoformat(timespec="milliseconds"),
                               self.n_req, f"{delta:.1f}", parola])
        if parola == "stop" and not self.verbose:
            self.stop_contati += 1
            self.riassumi_stop()
            return
        self.riassumi_stop(forza=True)
        print(f"[{ora()}] REQ #{self.n_req}  dt={delta:6.0f} ms  -> {parola}")

    def riassumi_stop(self, forza=False):
        """Una riga ogni INTERVALLO_RIASSUNTO s con il numero di REQ risposte stop."""
        adesso = time.perf_counter()
        if self.stop_contati and (forza or adesso - self.t_riassunto >= INTERVALLO_RIASSUNTO):
            print(f"[{ora()}] {self.stop_contati} REQ -> stop")
            self.stop_contati = 0
        if forza or adesso - self.t_riassunto >= INTERVALLO_RIASSUNTO:
            self.t_riassunto = adesso

    def chiudi(self):
        self.riassumi_stop(forza=True)
        if self.file_log:
            self.file_log.close()


def main():
    args = leggi_argomenti()
    stato = Stato(args.persistente)
    registro = Registro(args.verbose, args.log)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.port))
    srv.listen(1)
    print(f"Server teleop in ascolto sulla porta {args.port} "
          f"(terminatore {args.terminatore!r}). Premi h per l'aiuto.")
    print(stato.descrivi())

    conn = None
    buffer = ""
    try:
        while True:
            # 1. Attesa breve (10 ms) di una connessione o di dati dal robot
            sorgente = srv if conn is None else conn
            pronti, _, _ = select.select([sorgente], [], [], 0.01)

            if pronti and conn is None:
                # 2. Nuovo robot
                conn, addr = srv.accept()
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                buffer = ""
                print(f"[{ora()}] Robot connesso da {addr}")

            elif pronti:
                # 3. Dati dal robot: una risposta per ogni REQ (possono arrivare attaccate)
                try:
                    data = conn.recv(1024)
                except (ConnectionResetError, ConnectionAbortedError):
                    data = b""
                if not data:
                    registro.riassumi_stop(forza=True)
                    print(f"[{ora()}] Robot disconnesso")
                    conn.close()
                    conn = None
                    if stato.quit_inviato:
                        print("Quit inviato e robot disconnesso: chiudo.")
                        break
                    stato.quit_richiesto = False
                    print("Torno in ascolto...")
                    continue
                buffer += data.decode(errors="ignore")
                n = buffer.count("REQ")
                if n == 0:
                    # tiene solo un eventuale pezzo di "REQ" spezzato tra due recv
                    buffer = buffer[-2:]
                    continue
                buffer = buffer[buffer.rfind("REQ") + 3:]
                try:
                    for _ in range(n):
                        parola = stato.risposta()
                        conn.sendall((parola + args.terminatore).encode())
                        registro.req(parola)
                except OSError:
                    pass  # la disconnessione viene gestita al prossimo recv

            # 4. Tastiera (non bloccante)
            while msvcrt.kbhit():
                if gestisci_tasto(stato, conn):
                    return
            controlla_rilascio(stato)
            registro.riassumi_stop()
    except KeyboardInterrupt:
        print("\nInterrotto (Ctrl+C).")
    finally:
        registro.chiudi()
        if conn is not None:
            conn.close()
        srv.close()


if __name__ == "__main__":
    main()
