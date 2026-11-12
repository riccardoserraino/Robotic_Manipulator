"""
fake_robot.py - Pretends to be the Estun robot, to test the Python side WITHOUT Estun Editor.

It connects to teleop_hands.py / keyboard_teleop.py exactly like Teleop_Comm.erp does
(sends "REQ" every CYCLE_S, reads one number) and applies the same rules as Teleop_Gesti.erp:
    Cartesian step of STEP_MM, only if the new point is inside the ellipsoid (Teleop_Region.erp)
    J5 / J6 steps with the same limits, gripper open / close, quit
and prints the simulated robot state. Keep the SETTINGS equal to the .erp files.

Usage (in a second terminal, after starting teleop_hands.py or keyboard_teleop.py):
    python fake_robot.py
    python fake_robot.py --ip 192.168.6.1      # PC running the server is another machine
"""

import argparse
import socket
import time

# ==== SETTINGS (same values as Teleop_Gesti.erp and Teleop_Region.erp) ====================
PORT = 9500
CYCLE_S = 0.2                         # the robot asks about every 200 ms
STEP_MM = 20.0                        # R_STEP
J5_STEP, J6_STEP = 5.0, 10.0          # R_J5_STEP, R_J6_STEP in degrees
N5_LIMIT, N6_LIMIT = 6, 18            # N5_MAX / N6_MAX (and minus for the minimum)
HOME = (274.3, 14.4, 230.7)           # t_g.pose_home x, y, z in mm
CENTRE_OFFSET = (60.0, 10.0, -50.0)   # R_CX_OFF, R_CY_OFF, R_CZ_OFF
SEMI_AXES = (100.0, 110.0, 75.0)      # R_AX, R_AY, R_AZ
# =========================================================================================

NAMES = {1: "left", 2: "right", 3: "forward", 4: "backward", 5: "up", 6: "down", 7: "stop",
         8: "quit", 9: "open", 10: "close", 11: "j5_up", 12: "j5_down", 13: "j6_cw", 14: "j6_ccw"}
STEPS = {1: (0, 1, 0), 2: (0, -1, 0), 3: (1, 0, 0), 4: (-1, 0, 0), 5: (0, 0, 1), 6: (0, 0, -1)}


def inside_region(p):
    """Same test as Teleop_Region.erp: sum of the squared normalised distances <= 1."""
    total = 0.0
    for value, home, offset, axis in zip(p, HOME, CENTRE_OFFSET, SEMI_AXES):
        u = (value - home - offset) / axis
        total += u * u
    return total <= 1.0


def main():
    ap = argparse.ArgumentParser(description="Fake Estun robot for the teleop server")
    ap.add_argument("--ip", default="127.0.0.1", help="IP of the PC running the server")
    args = ap.parse_args()

    assert inside_region(HOME), "home must be inside the region, check the settings"
    pos, n5, n6, grip, warned = list(HOME), 0, 0, "open", False
    sock = socket.create_connection((args.ip, PORT), timeout=1.0)
    print(f"Connected to {args.ip}:{PORT} (like Teleop_Comm). Ctrl+C to stop.")
    last_state = None
    try:
        while True:
            sock.sendall(b"REQ")
            try:
                code = int(sock.recv(64).decode().strip())
            except (socket.timeout, ValueError):
                code = 0                                    # timeout / garbage -> nothing
            if code in STEPS:
                new = [p + STEP_MM * d for p, d in zip(pos, STEPS[code])]
                if inside_region(new):
                    pos, warned = new, False
                elif not warned:                            # message only once, like the robot
                    print("  LIMIT - outside working region")
                    warned = True
            elif code == 11 and n5 < N5_LIMIT:
                n5 += 1
            elif code == 12 and n5 > -N5_LIMIT:
                n5 -= 1
            elif code == 13 and n6 < N6_LIMIT:
                n6 += 1
            elif code == 14 and n6 > -N6_LIMIT:
                n6 -= 1
            elif code == 9:
                grip = "open"
            elif code == 10:
                grip = "closed"
            state = (f"cmd {NAMES.get(code, 'none'):8s} | x {pos[0]:6.1f} y {pos[1]:6.1f} "
                     f"z {pos[2]:6.1f} | J5 {n5 * J5_STEP:+5.0f} J6 {n6 * J6_STEP:+5.0f} | {grip}")
            if state != last_state:
                print(state)
                last_state = state
            if code == 8:
                print("quit received: going home and closing (like the robot).")
                break
            time.sleep(CYCLE_S)
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()


if __name__ == "__main__":
    main()
