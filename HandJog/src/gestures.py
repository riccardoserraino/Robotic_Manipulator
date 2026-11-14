"""
gestures.py - From hand landmarks to ONE robot command word.

RIGHT hand = Cartesian jog of the tool (MovL steps on the robot)
    index pointing LEFT / RIGHT     -> left / right      (robot +Y / -Y)
    index pointing UP / DOWN        -> up / down         (robot +Z / -Z)
    fist + THUMB UP / THUMB DOWN    -> forward / backward (robot +X / -X)

LEFT hand = wrist joints and gripper
    index pointing UP / DOWN        -> lifts / lowers the gripper (J5)
    fist + THUMB UP / THUMB DOWN    -> j6_cw / j6_ccw    (J6, rotates the gripper)
    HORNS (index + pinky up)        -> close             (close the gripper)
    OPEN PALM (all five fingers)    -> open              (open the gripper, hold it a moment)

Anything else (no hand, unclear gesture) -> stop.
If both hands give a command, the RIGHT hand wins (motion first, the left hand waits).

Directions are those of the MIRRORED image (hand_tracker.MIRROR_VIEW): move as in front of
a mirror. If a robot direction comes out reversed from where you stand, swap the words in
RIGHT_HAND / LEFT_HAND below, not the robot program.

How a gesture is recognised (only distances and angles relative to the palm size, so it
works at any distance from the camera):
    finger extended  -> its tip is clearly farther from the wrist than its middle joint
    finger folded    -> its tip is about as close to the wrist as its middle joint, or closer
    pointing         -> direction of the finger vector, within ANGLE_TOL_DEG of an axis

Standalone (no robot, to practise and tune):  python gestures.py
"""

import math
import time

# ==== SETTINGS ===========================================================================
RIGHT_HAND = {                      # gesture -> command word, RIGHT hand
    "index_left": "left",
    "index_right": "right",
    "index_up": "up",
    "index_down": "down",
    "thumb_up": "forward",
    "thumb_down": "backward",
}
LEFT_HAND = {                       # gesture -> command word, LEFT hand
    "index_up": "j5_down",       # swapped: on our robot j5_down is the one that lifts the gripper
    "index_down": "j5_up",
    "thumb_up": "j6_cw",
    "thumb_down": "j6_ccw",
    "horns": "close",
    "open_palm": "open",
}
ANGLE_TOL_DEG = 35.0   # max deviation from horizontal / vertical, more = unclear gesture
MIN_LENGTH = 0.45      # pointing finger length relative to the palm, shorter = points at camera
N_CONFIRM = 3          # identical frames needed to start a motion command (~0.1 s at 30 fps)
N_CONFIRM_GRIP = 8     # identical frames needed for open / close (~0.3 s, avoids accidents)
T_LOSS_S = 0.15        # the active command is dropped (-> stop) after this time without it
# =========================================================================================

WRIST = 0
THUMB = (1, 2, 3, 4)          # CMC, MCP, IP, tip
INDEX = (5, 6, 7, 8)          # MCP, PIP, DIP, tip
MIDDLE = (9, 10, 11, 12)
RING = (13, 14, 15, 16)
PINKY = (17, 18, 19, 20)


# ---- geometry helpers --------------------------------------------------------------------
def _dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def extended(lm, finger):
    """Finger (not thumb) straight: tip 15% farther from the wrist than the PIP joint."""
    return _dist(lm[WRIST], lm[finger[3]]) > _dist(lm[WRIST], lm[finger[1]]) * 1.15


def folded(lm, finger):
    """Finger (not thumb) closed: tip not farther than 5% beyond the PIP joint."""
    return _dist(lm[WRIST], lm[finger[3]]) < _dist(lm[WRIST], lm[finger[1]]) * 1.05


def thumb_out(lm, palm):
    """Thumb sticking out: tip far from the base of the index finger."""
    return _dist(lm[THUMB[3]], lm[INDEX[0]]) > 0.55 * palm


def direction(start, end, palm):
    """'left' / 'right' / 'up' / 'down' of the vector start->end, None if short or oblique."""
    vx, vy = end.x - start.x, end.y - start.y
    if math.hypot(vx, vy) < MIN_LENGTH * palm:
        return None
    angle = math.degrees(math.atan2(-vy, vx))      # -vy because image y grows downwards
    for name, centre in (("right", 0.0), ("up", 90.0), ("left", 180.0), ("down", -90.0)):
        if abs((angle - centre + 180.0) % 360.0 - 180.0) <= ANGLE_TOL_DEG:
            return name
    return None


# ---- one frame ---------------------------------------------------------------------------
def classify(lm):
    """Gesture name of one hand in one frame ('index_left', 'horns', ...) or None."""
    palm = _dist(lm[WRIST], lm[MIDDLE[0]])          # wrist -> middle knuckle = hand scale
    if palm < 1e-6:
        return None
    # Open palm: all four fingers straight and thumb out
    if all(extended(lm, f) for f in (INDEX, MIDDLE, RING, PINKY)) and thumb_out(lm, palm):
        return "open_palm"
    # Horns: index and pinky straight, middle and ring folded
    if extended(lm, INDEX) and extended(lm, PINKY) and folded(lm, MIDDLE) and folded(lm, RING):
        return "horns"
    # All the other gestures need middle, ring and pinky folded
    if not all(folded(lm, f) for f in (MIDDLE, RING, PINKY)):
        return None
    if extended(lm, INDEX):                          # only the index: pointing
        way = direction(lm[INDEX[0]], lm[INDEX[3]], palm)
        return f"index_{way}" if way else None
    if folded(lm, INDEX) and thumb_out(lm, palm):    # fist with the thumb out
        way = direction(lm[THUMB[1]], lm[THUMB[3]], palm)
        if way in ("up", "down"):
            return f"thumb_{way}"
    return None


def command_from_hands(hands):
    """Command word for this frame from the list of hand_tracker.Hand.

    Returns (word, info) where info = {side: gesture} for the on-screen display.
    """
    info, words = {}, {}
    for hand in sorted(hands, key=lambda h: h.score):     # best score last -> it wins per side
        gesture = classify(hand.landmarks)
        info[hand.side] = gesture
        table = RIGHT_HAND if hand.side == "Right" else LEFT_HAND
        words[hand.side] = table.get(gesture)
    word = words.get("Right") or words.get("Left") or "stop"   # right hand has priority
    return word, info


# ---- over time ---------------------------------------------------------------------------
class Stabilizer:
    """Filters the per-frame word so a single bad frame never starts or stops the robot.

    - a new command becomes active after N_CONFIRM identical frames
      (N_CONFIRM_GRIP for open / close)
    - the active command falls back to stop after T_LOSS_S without seeing it
    """

    def __init__(self):
        self.active = "stop"
        self._candidate, self._count, self._last_seen = None, 0, 0.0

    def update(self, raw, now):
        if raw != "stop" and raw == self.active:         # same command: keep it alive
            self._last_seen = now
            self._candidate, self._count = None, 0
            return self.active
        if raw != "stop":                                  # new command: count the frames
            self._count = self._count + 1 if raw == self._candidate else 1
            self._candidate = raw
            needed = N_CONFIRM_GRIP if raw in ("open", "close") else N_CONFIRM
            if self._count >= needed:
                self.active, self._last_seen = raw, now
                self._candidate, self._count = None, 0
                return self.active
        else:
            self._candidate, self._count = None, 0
        if self.active != "stop" and now - self._last_seen >= T_LOSS_S:
            self.active = "stop"
        return self.active


def draw_status(frame, word, info, fps=None):
    """Big active command on top + raw gesture of each hand."""
    import cv2
    color = (0, 200, 0) if word != "stop" else (0, 0, 255)
    cv2.putText(frame, f"CMD: {word}", (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 1.1, color, 3)
    text = f"R: {info.get('Right') or '-'}   L: {info.get('Left') or '-'}"
    if fps is not None:
        text += f"   FPS {fps:.0f}"
    cv2.putText(frame, text, (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)


def main():
    """Practice mode WITHOUT robot: shows which command each gesture would send."""
    import cv2
    from hand_tracker import HandTracker, draw_hands

    tracker, stab = HandTracker(), Stabilizer()
    last, t_prev = None, time.monotonic()
    try:
        while True:
            frame, hands = tracker.read()
            if frame is None:
                break
            now = time.monotonic()
            raw, info = command_from_hands(hands)
            word = stab.update(raw, now)
            if word != last:
                print(f"command: {word}")
                last = word
            draw_hands(frame, hands, {s: g or "" for s, g in info.items()})
            draw_status(frame, word, info, 1.0 / max(now - t_prev, 1e-6))
            t_prev = now
            cv2.imshow("Gestures - practice, no robot (Q to quit)", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
    finally:
        tracker.close()


if __name__ == "__main__":
    main()
