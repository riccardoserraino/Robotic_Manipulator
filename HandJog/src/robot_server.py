"""
robot_server.py - TCP server that answers the Estun robot (program Teleop_Comm.erp).

Protocol (PC = server, robot = client):
    robot -> "REQ"
    PC    -> ONE number, the code of the current command (table COMMANDS below)
The robot asks about every 200 ms. Who decides the command does not matter here:
the caller passes a function get_command() -> (word, time_of_last_update).

    server = RobotServer(get_command)
    server.start()            # runs in a background thread
    server.request_quit()     # the next answer is "quit": robot closes and goes home
    server.stop()

Safety: if get_command() was not updated for more than STALE_S seconds (camera frozen,
program stuck) the answer is "stop".
"""

import socket
import threading
import time
from datetime import datetime

# ==== SETTINGS ===========================================================================
PORT = 9500          # must match I_PC_PORT in Teleop_Gesti.erp (9000 is used by Estun Editor)
STALE_S = 0.5        # command older than this -> answer stop
LOG_FILE = None      # e.g. "teleop_log.csv" to save one row per REQ, None = no file
# =========================================================================================

# Command word -> number sent to the robot. SAME table as the comments in Teleop_Gesti.erp.
COMMANDS = {
    "left": 1, "right": 2, "forward": 3, "backward": 4, "up": 5, "down": 6,
    "stop": 7, "quit": 8, "open": 9, "close": 10,
    "j5_up": 11, "j5_down": 12, "j6_cw": 13, "j6_ccw": 14,
}


def now_str():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


class RobotServer(threading.Thread):
    """Answers every "REQ" of the robot with the code of the current command."""

    def __init__(self, get_command, port=PORT):
        super().__init__(daemon=True)
        self.get_command = get_command
        self.port = port
        self.connected = False      # shown in the video window
        self.quit_sent = False
        self._quit = False
        self._stop_event = threading.Event()
        self.n_req = 0
        self._last_word = None
        self._log = open(LOG_FILE, "w") if LOG_FILE else None
        if self._log:
            self._log.write("time,n_req,word\n")

    # ---- control from the main program ----
    def request_quit(self):
        self._quit = True

    def stop(self):
        self._stop_event.set()
        self.join(2.0)
        if self._log:
            self._log.close()

    # ---- thread ----
    def run(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # restart without "address in use"
        srv.bind(("0.0.0.0", self.port))                            # listen on every network card
        srv.listen(1)
        srv.settimeout(0.2)              # short timeouts so the thread notices stop() quickly
        print(f"[{now_str()}] Waiting for the robot on port {self.port}")
        try:
            while not self._stop_event.is_set() and not self.quit_sent:
                try:
                    conn, addr = srv.accept()
                except socket.timeout:
                    continue
                print(f"[{now_str()}] Robot connected from {addr[0]}")
                self.connected = True
                self._serve(conn)
                self.connected = False
                print(f"[{now_str()}] Robot disconnected")
        finally:
            srv.close()

    def _serve(self, conn):
        """Answer the REQs of one connection until the robot closes it."""
        conn.settimeout(0.2)
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)   # send short answers at once
        buffer = ""
        with conn:
            while not self._stop_event.is_set():
                try:
                    data = conn.recv(1024)
                except socket.timeout:
                    continue
                except OSError:
                    data = b""
                if not data:                       # empty read = robot closed the socket
                    return
                # TCP is a stream: two REQ can arrive together, or one can arrive in pieces
                buffer += data.decode(errors="ignore")
                while "REQ" in buffer:
                    buffer = buffer.split("REQ", 1)[1]
                    word = self._choose_word()
                    try:
                        conn.sendall(str(COMMANDS[word]).encode())
                    except OSError:
                        return
                    self._report(word)
                buffer = buffer[-2:]               # keep a possible "RE" split between two recv

    def _choose_word(self):
        if self._quit:
            self.quit_sent = True
            return "quit"
        word, updated = self.get_command()
        if time.monotonic() - updated > STALE_S:
            return "stop"                          # nobody is updating the command: stop
        return word if word in COMMANDS else "stop"

    def _report(self, word):
        """Print only when the answer changes (keeps the console readable)."""
        self.n_req += 1
        if word != self._last_word:
            print(f"[{now_str()}] REQ #{self.n_req} -> {word} ({COMMANDS[word]})")
            self._last_word = word
        if self._log:
            self._log.write(f"{now_str()},{self.n_req},{word}\n")
