"""
Fake camera to test the Estun pick&place program (6 slots).

Robot program flow (one single connection for the whole run):
  1. SocketCreate towards the camera (port 8192)
  2. "scheme CheckPresence"  -> answer "OK"
  3. WHILE CONTINUA == 1:
       "runonce" -> string with presences + angles
       TranStrToReal(answer, ";", G:Dati_Array)
       finds the first present slot (1..6), picks it and goes back home
       if no slot is present -> CONTINUA = 0
  4. SocketClose

Format of the answer to "runonce" (12 values, 2 per slot):
  presence1;angle1;presence2;angle2;...;presence6;angle6
  - presence: 1 = cylinder present, 0 = absent
  - angle:    orientation of the groove in degrees, random real in
              [-180, +180] if the cylinder is present, 0 if absent
E.g. "0;0;0;0;1;-73.42;0;0;0;0;0;0" = cylinder in slot 3 at -73.42 deg
On the robot: slot i -> presence in Dati_Array[2*i-1], angle in Dati_Array[2*i]

Like the real camera, every answer to "runonce" is preceded by "OK"
(ReturnExecuteOK of SCMVS): e.g. "OK0;0;0;0;1;-73.42;0;0;0;0;0;0".
The robot program (LeggiVisione) drops the first two characters if they are "OK".
The prefix is switched on/off with OK_PREFIX below or with the command "k".

Commands at the answer prompt (manual mode):
  1..6        -> cylinder only in that slot (random angle)
  1,3,5       -> cylinders in several slots (the robot picks the first one)
  0           -> no cylinder (the robot leaves the WHILE)
  r           -> one random slot
  t           -> TRAY: fills random slots; at every photo it removes the cylinder
                 the robot has just picked (the first present one), until the
                 tray is empty -> the robot receives all 0 and leaves the loop
  t1,3,5      -> tray with cylinders in the given slots
  a           -> automatic: slots 1..6 in rotation (the cycle never ends)
  n           -> answer "NG" (non-numeric string)
  x           -> no answer (tests the 10 s timeout)
  k           -> toggle the "OK" prefix (then asks for the slot again)
  text with ; -> sent as it is (e.g. "1;45.5;0;0")
"""

import random
import socket

PORT = 8192           # must match SocketCreate(...,8192,...) / I_Porta_Camera
N_SLOTS = 6           # slots checked by the FOR loop of the robot program
ANGLE_MIN = -180.0
ANGLE_MAX = 180.0
DECIMALS = 2          # decimal digits of the angle (separator ".")
TERMINATOR = ""       # if SocketReadStr reads nothing, try "\r" or "\r\n"
OK_PREFIX = True      # True = put "OK" before every answer to runonce (like the real camera)

mode = "manual"       # "manual" | "auto" | "tray"
auto_slot = 0         # last slot used in automatic mode
tray = {}             # slot -> angle of the cylinders still in the tray


def random_angle():
    """Random groove angle, rounded to DECIMALS digits."""
    return round(random.uniform(ANGLE_MIN, ANGLE_MAX), DECIMALS)


def string_from_dict(present):
    """present: dict slot -> angle. Returns 'p1;a1;p2;a2;...' for all N_SLOTS slots."""
    values = []
    for i in range(1, N_SLOTS + 1):
        if i in present:
            values += ["1", f"{present[i]:.{DECIMALS}f}"]
        else:
            values += ["0", "0"]
    return ";".join(values)


def presence_string(present_slots):
    """Answer string with a random angle for each slot in present_slots."""
    return string_from_dict({s: random_angle() for s in present_slots})


def parse_slots(text):
    """'1,3,5' -> {1,3,5}; None if not valid."""
    try:
        slots = {int(s) for s in text.split(",") if s.strip()}
    except ValueError:
        return None
    if slots and all(1 <= s <= N_SLOTS for s in slots):
        return slots
    return None


def start_tray(argument):
    """Fill the tray (given slots, or random ones) and return the first 'photo'."""
    global mode, tray
    slots = parse_slots(argument) if argument else None
    if slots is None:
        n = random.randint(1, N_SLOTS)
        slots = set(random.sample(range(1, N_SLOTS + 1), n))
    tray = {s: random_angle() for s in sorted(slots)}
    mode = "tray"
    print("Tray loaded: " + ", ".join(f"slot {s} ({a} deg)" for s, a in tray.items()))
    return next_tray()


def next_tray():
    """Photo of the current tray; then removes the cylinder the robot will pick.

    The robot always picks the FIRST present slot, so we remove min(tray).
    """
    global mode
    answer = string_from_dict(tray)
    if tray:
        picked = min(tray)
        del tray[picked]
    else:
        print("Tray empty: the robot should leave the loop. Back to manual.")
        mode = "manual"
    return answer


def next_auto():
    """Automatic mode: one cylinder, slot 1,2,...,6,1,2,... at every photo."""
    global auto_slot
    auto_slot = auto_slot % N_SLOTS + 1
    return presence_string({auto_slot})


def build_answer(choice):
    """Translate the typed command into the string to send (None = do not answer)."""
    global mode
    if choice == "x":
        return None
    if choice == "n":
        return "NG"
    if choice == "0":
        return presence_string(set())
    if choice == "r":
        return presence_string({random.randint(1, N_SLOTS)})
    if choice.startswith("t"):
        return start_tray(choice[1:].strip())
    if choice == "a":
        mode = "auto"
        return next_auto()
    if ";" in choice:
        return choice
    slots = parse_slots(choice)
    if slots is not None:
        return presence_string(slots)
    return choice  # anything else is sent as it is


def describe(text):
    """Readable print of the answer: present slots and their angle."""
    if text.startswith("OK"):
        text = text[2:]
    parts = text.split(";")
    if len(parts) != 2 * N_SLOTS:
        return ""
    lines = [f"slot {i // 2 + 1}: {parts[i + 1]} deg"
             for i in range(0, len(parts), 2) if parts[i] == "1"]
    if not lines:
        return "  (no cylinder)"
    return "  (" + ", ".join(lines) + f" -> the robot picks slot {lines[0].split(':')[0][5:]})"


def send(conn, text):
    """Send one answer to the robot and print it."""
    conn.sendall((text + TERMINATOR).encode())
    print(f"Answered: {text!r}{describe(text)}")


# --- Server: wait for the robot, then answer its commands ------------------------------
srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", PORT))
srv.listen(1)
print(f"Fake camera listening on port {PORT} ({N_SLOTS} slots)...")

session = 0
while True:
    conn, addr = srv.accept()          # blocks until the robot runs SocketCreate
    session += 1
    photos = 0
    print(f"\n=== Session {session}: robot connected from {addr}")
    with conn:
        while True:
            try:
                data = conn.recv(1024)
            except ConnectionResetError:
                data = b""
            if not data:               # empty read = the robot closed the socket
                print(f"<<< Robot disconnected (photos taken: {photos})")
                break
            cmd = data.decode(errors="ignore").strip()
            print(f"\nReceived: {cmd!r}")

            if cmd.startswith("scheme"):     # recipe change -> just confirm
                send(conn, "OK")
                continue

            if cmd.startswith("runonce"):    # "take a photo"
                photos += 1
                print(f"--- Photo {photos}")
                if mode == "auto":
                    answer = next_auto()
                elif mode == "tray":
                    answer = next_tray()
                else:
                    while True:
                        prefix_state = "on" if OK_PREFIX else "off"
                        choice = input(f"Present slots [1-{N_SLOTS} | 1,3 | 0 | r | t | t1,3 | a | n | x"
                                       f" | k (OK: {prefix_state})]: ").strip()
                        if choice != "k":
                            break
                        OK_PREFIX = not OK_PREFIX
                        print(f"OK prefix {'on' if OK_PREFIX else 'off'}")
                    answer = build_answer(choice)
                if answer is None:
                    print("No answer (the robot will time out after 10 s)")
                    continue
                if OK_PREFIX:
                    answer = "OK" + answer
                send(conn, answer)
                continue

            print("Unexpected command, no answer")
