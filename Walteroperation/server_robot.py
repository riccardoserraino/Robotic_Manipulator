"""
server_robot.py - Server TCP verso il robot Estun (stesso protocollo di
sim_comm/teleop_server_tastiera.py), indipendente da chi sceglie il comando.

Protocollo (PC = server, robot = client, programma Teleop_Comm.erp):
    robot -> "REQ"
    PC    -> una parola: left right forward backward up down stop quit open close
             (senza terminatore di default)

Il comando da mandare lo fornisce una funzione `fonte()` passata dal chiamante
(per esempio il rilevatore di gesti). Il server gira in un thread a parte:

    server = ServerRobot(fonte=lambda: comando_corrente, porta=9500)
    server.avvia()
    ...
    server.richiedi_quit()   # alla prossima REQ manda "quit"
    server.ferma()

Sicurezza: se `fonte()` non e' stata aggiornata da piu' di `scadenza_s` secondi
(camera bloccata, programma impallato) si risponde "stop".
"""

import csv
import select
import socket
import threading
import time
from datetime import datetime

INTERVALLO_RIASSUNTO = 1.0   # [s] riassunto delle REQ con risposta stop


def ora():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


class ServerRobot:
    def __init__(self, fonte, porta=9500, terminatore="", log=None, verbose=False):
        """
        fonte:  funzione senza argomenti -> (parola, istante_aggiornamento_monotonic)
        """
        self.fonte = fonte
        self.porta = porta
        self.terminatore = terminatore
        self.verbose = verbose
        self.scadenza_s = 0.5
        self._quit = False
        self.quit_inviato = False
        self.connesso = False
        self._ferma = threading.Event()
        self._thread = None
        self._file_log = open(log, "w", newline="") if log else None
        self._csv = csv.writer(self._file_log) if self._file_log else None
        if self._csv:
            self._csv.writerow(["timestamp", "n_req", "delta_ms", "comando"])
        self.n_req = 0
        self._t_prec = None
        self._stop_contati = 0
        self._t_riassunto = time.perf_counter()
        self.ultima_risposta = "stop"

    # -- controllo dall'esterno ---------------------------------------------------------
    def avvia(self):
        self._thread = threading.Thread(target=self._ciclo, name="ServerRobot", daemon=True)
        self._thread.start()

    def richiedi_quit(self):
        """Alla prossima REQ si manda 'quit' (il robot chiude e torna in home)."""
        self._quit = True

    def ferma(self, attesa_s=2.0):
        self._ferma.set()
        if self._thread:
            self._thread.join(attesa_s)
        if self._file_log:
            self._file_log.close()

    def terminato(self):
        return self._thread is not None and not self._thread.is_alive()

    # -- risposta -------------------------------------------------------------------------
    def _parola(self):
        if self._quit:
            self.quit_inviato = True
            return "quit"
        parola, istante = self.fonte()
        if time.monotonic() - istante > self.scadenza_s:
            return "stop"   # rilevatore fermo: per sicurezza niente moto
        return parola

    def _registra(self, parola):
        adesso = time.perf_counter()
        delta = (adesso - self._t_prec) * 1000 if self._t_prec is not None else 0.0
        self._t_prec = adesso
        self.n_req += 1
        if self._csv:
            self._csv.writerow([datetime.now().isoformat(timespec="milliseconds"),
                                self.n_req, f"{delta:.1f}", parola])
        if parola == "stop" and not self.verbose:
            self._stop_contati += 1
            self._riassumi()
            return
        self._riassumi(forza=True)
        print(f"[{ora()}] REQ #{self.n_req}  dt={delta:6.0f} ms  -> {parola}")

    def _riassumi(self, forza=False):
        adesso = time.perf_counter()
        if forza or adesso - self._t_riassunto >= INTERVALLO_RIASSUNTO:
            if self._stop_contati:
                print(f"[{ora()}] {self._stop_contati} REQ -> stop")
                self._stop_contati = 0
            self._t_riassunto = adesso

    # -- ciclo del thread -----------------------------------------------------------------
    def _ciclo(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", self.porta))
        srv.listen(1)
        print(f"[{ora()}] Server robot in ascolto sulla porta {self.porta}")
        conn, buffer = None, ""
        try:
            while not self._ferma.is_set():
                sorgente = srv if conn is None else conn
                pronti, _, _ = select.select([sorgente], [], [], 0.05)
                if not pronti:
                    self._riassumi()
                    continue
                if conn is None:
                    conn, addr = srv.accept()
                    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    buffer, self.connesso = "", True
                    print(f"[{ora()}] Robot connesso da {addr}")
                    continue
                try:
                    data = conn.recv(1024)
                except (ConnectionResetError, ConnectionAbortedError):
                    data = b""
                if not data:
                    self._riassumi(forza=True)
                    print(f"[{ora()}] Robot disconnesso")
                    conn.close()
                    conn, self.connesso = None, False
                    if self.quit_inviato:
                        return
                    self._quit = False
                    continue
                buffer += data.decode(errors="ignore")
                n = buffer.count("REQ")
                if n == 0:
                    buffer = buffer[-2:]   # pezzo di "REQ" spezzato tra due recv
                    continue
                buffer = buffer[buffer.rfind("REQ") + 3:]
                try:
                    for _ in range(n):
                        parola = self._parola()
                        conn.sendall((parola + self.terminatore).encode())
                        self.ultima_risposta = parola
                        self._registra(parola)
                except OSError:
                    pass   # gestito al prossimo recv
        finally:
            self._riassumi(forza=True)
            if conn is not None:
                conn.close()
            srv.close()
