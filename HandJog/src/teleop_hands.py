"""
teleop_hands.py - Teleoperation of the Estun ER4-550 with hand gestures.  RUN THIS ONE.

    webcam -> hand_tracker -> gestures (+ Stabilizer) -> shared command -> robot_server -> robot

Two threads:
    main thread   webcam, MediaPipe, gestures, video window (OpenCV wants the main thread)
    server thread answers every "REQ" of the robot with the current command

Robot side: workspace teleop_v1, load Teleop_Gesti and press Start (after this script).
Gestures: see gestures.py (practise first with  python gestures.py).

Keys in the video window
    Q / ESC  send "quit" (the robot goes home), then close
    O / C    open / close the gripper once (backup for the gestures)
"""

import threading
import time

import cv2

from gestures import Stabilizer, command_from_hands, draw_status
from hand_tracker import HandTracker, draw_hands
from robot_server import RobotServer

# ==== SETTINGS ===========================================================================
CAMERA_INDEX = 0     # webcam index
PORT = 9500          # same as I_PC_PORT in Teleop_Gesti.erp
# =========================================================================================


class SharedCommand:
    """Current command, written by the camera loop and read by the server thread (with a lock).

    It also stores WHEN it was written: the server answers stop if it gets too old.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._word, self._time = "stop", time.monotonic()
        self._once = None                       # "open" / "close" from the keyboard, sent once

    def write(self, word):
        with self._lock:
            self._word, self._time = word, time.monotonic()

    def write_once(self, word):
        with self._lock:
            self._once = word

    def read(self):
        with self._lock:
            if self._once:
                word, self._once = self._once, None
                return word, time.monotonic()
            return self._word, self._time


def main():
    command = SharedCommand()
    tracker = HandTracker(CAMERA_INDEX)          # open the camera first: if it fails, no robot
    server = RobotServer(command.read, PORT)
    server.start()
    stab = Stabilizer()
    last, closing, t_prev = None, False, time.monotonic()
    try:
        while True:
            frame, hands = tracker.read()
            if frame is None:
                print("Webcam: no frame, closing.")
                break
            now = time.monotonic()

            # hands -> raw word of this frame -> stable word -> shared with the server
            raw, info = command_from_hands(hands)
            word = "stop" if closing else stab.update(raw, now)
            command.write(word)
            if word != last:
                print(f"Command: {word}")
                last = word

            # display
            draw_hands(frame, hands, {s: g or "" for s, g in info.items()})
            draw_status(frame, word, info, 1.0 / max(now - t_prev, 1e-6))
            t_prev = now
            ok = server.connected
            cv2.putText(frame, "robot connected" if ok else "robot NOT connected",
                        (10, frame.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 200, 0) if ok else (0, 0, 255), 2)
            cv2.imshow("Teleop hands (Q = quit robot)", frame)

            # keys
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                if not server.connected:
                    break                                   # no robot: just close
                if not closing:
                    print("Quit: sending 'quit', closing when the robot disconnects.")
                    server.request_quit()
                    closing = True
            elif key == ord("o"):
                command.write_once("open")
            elif key == ord("c"):
                command.write_once("close")
            if closing and not server.is_alive():
                break                                       # robot got quit and left
    except KeyboardInterrupt:
        print("Interrupted (Ctrl+C).")
    finally:
        command.write("stop")
        server.stop()
        tracker.close()


if __name__ == "__main__":
    main()
