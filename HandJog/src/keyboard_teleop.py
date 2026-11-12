"""
keyboard_teleop.py - Drive the robot from the KEYBOARD (no webcam). Windows only.

Same robot program (Teleop_Gesti + Teleop_Comm) and same protocol as teleop_hands.py,
so it is the quickest way to test the Estun side, also with the virtual controller.

A direction is active ONLY WHILE ITS KEY IS HELD: on release the robot gets stop.
(The press is read from this console with msvcrt, the release from the physical key
state with GetAsyncKeyState, so keep this console window focused.)

Keys
    w / s   forward / backward (+X / -X)      a / d   left / right (+Y / -Y)
    r / f   up / down (+Z / -Z)               i / k   J5 up / down
    j / l   J6 cw / ccw                        o / c   open / close gripper (once)
    p       single-step mode on/off (each key press = exactly one step)
    q       quit (robot goes home), then close      h   help

Usage:  python keyboard_teleop.py
"""

import ctypes
import msvcrt
import threading
import time

from robot_server import RobotServer

# ==== SETTINGS ===========================================================================
PORT = 9500
HELD_KEYS = {          # key -> command, valid while the key is held
    "w": "forward", "s": "backward", "a": "left", "d": "right", "r": "up", "f": "down",
    "i": "j5_up", "k": "j5_down", "j": "j6_cw", "l": "j6_ccw",
}
ONCE_KEYS = {"o": "open", "c": "close"}   # key -> command sent for a single REQ
# =========================================================================================

_user32 = ctypes.WinDLL("user32")
_user32.GetAsyncKeyState.restype = ctypes.c_short


def key_is_down(key):
    """True if the letter key is physically pressed now (virtual-key code = upper-case ASCII)."""
    return bool(_user32.GetAsyncKeyState(ord(key.upper())) & 0x8000)


class KeyboardCommand:
    """Current command chosen from the keyboard, read by the server thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self.word, self.held, self.single_step, self._once = "stop", None, False, None

    def read(self):
        with self._lock:
            if self._once:                             # one-shot command (open/close/single step)
                word, self._once = self._once, None
                return word, time.monotonic()
            return self.word, time.monotonic()

    def press(self, key):
        with self._lock:
            if key in ONCE_KEYS:
                self._once = ONCE_KEYS[key]
            elif key in HELD_KEYS:
                if self.single_step:
                    self._once = HELD_KEYS[key]        # one step, then stop
                elif self.held != key:
                    self.held, self.word = key, HELD_KEYS[key]
                    print(f"-> {self.word}")

    def check_release(self):
        with self._lock:
            if self.held and not key_is_down(self.held):
                self.held, self.word = None, "stop"
                print("-> stop")


def main():
    cmd = KeyboardCommand()
    server = RobotServer(cmd.read, PORT)
    server.start()
    print(__doc__.split("Keys")[1].split("Usage")[0])
    try:
        while server.is_alive():
            while msvcrt.kbhit():
                key = msvcrt.getwch().lower()
                if key == "q":
                    if not server.connected:
                        return
                    print("Quit: sending 'quit' to the robot...")
                    server.request_quit()
                elif key == "p":
                    cmd.single_step = not cmd.single_step
                    print(f"single-step mode {'ON' if cmd.single_step else 'OFF'}")
                elif key == "h":
                    print(__doc__.split("Keys")[1].split("Usage")[0])
                else:
                    cmd.press(key)
            cmd.check_release()
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("Interrupted (Ctrl+C).")
    finally:
        server.stop()


if __name__ == "__main__":
    main()
