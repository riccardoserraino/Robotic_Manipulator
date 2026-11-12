"""
hand_tracker.py - Webcam + MediaPipe hand tracking. The ONLY file that talks to MediaPipe.

What it does, step by step:
  1. Opens the webcam with OpenCV.
  2. Loads Google's pre-trained "Hand Landmarker" network (models/hand_landmarker.task).
  3. For every frame it returns the hands found. Each hand has
       side       "Right" or "Left" (the operator's real hand, see MIRROR / handedness below)
       landmarks  21 points with x, y in [0, 1] (normalised image coordinates)
       score      how sure the model is about the side (0..1)
  4. draw_hands() draws the skeleton and the side label on the frame.

Used as a library by gestures.py and teleop_hands.py:
    tracker = HandTracker()
    frame, hands = tracker.read()      # one frame + list of Hand
    draw_hands(frame, hands)
    tracker.close()

Standalone demo:  python hand_tracker.py   (Q or ESC to quit)

Landmark numbering (21 points per hand):
    0 wrist | 1-4 thumb (4 = tip) | 5-8 index (8 = tip) | 9-12 middle | 13-16 ring | 17-20 pinky
    x = 0 left edge, 1 right edge | y = 0 top edge, 1 bottom edge (y grows DOWNWARDS)

About left/right:
    MIRROR_VIEW flips the image like a mirror, so moving your hand to the right moves it
    to the right on screen too (natural for teleoperation).
    The model decides "Left"/"Right" from the hand shape and, by MediaPipe's convention,
    expects exactly this mirrored (selfie) image, so with MIRROR_VIEW = True the label
    should already be your real hand. If on your PC it is still inverted, set
    SWAP_HANDEDNESS = True. Quick check: raise only your RIGHT hand, the label must say Right.
"""

import sys
import time
from collections import namedtuple
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

# ==== SETTINGS ===========================================================================
CAMERA_INDEX = 0          # 0 = default webcam, 1 = external USB webcam, ...
MAX_HANDS = 2             # right hand moves the robot, left hand wrist + gripper
MIRROR_VIEW = True        # True = the window behaves like a mirror (recommended)
SWAP_HANDEDNESS = False   # True only if, with your camera, Right and Left come out inverted
MIN_CONFIDENCE = 0.5      # detection / tracking confidence (higher = fewer false hands)
MODEL_PATH = Path(__file__).parent / "models" / "hand_landmarker.task"
# =========================================================================================

# One detected hand
Hand = namedtuple("Hand", "side landmarks score")

# Lines between landmarks, used only for drawing
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),          # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),          # index
    (5, 9), (9, 10), (10, 11), (11, 12),     # middle
    (9, 13), (13, 14), (14, 15), (15, 16),   # ring
    (13, 17), (17, 18), (18, 19), (19, 20),  # pinky
    (0, 17),                                 # palm
]
FINGERTIPS = (4, 8, 12, 16, 20)
# OpenCV colours are BGR (blue, green, red)
COLOR = {"Right": (255, 200, 0), "Left": (0, 165, 255)}   # light blue / orange


class HandTracker:
    """Webcam + MediaPipe Hand Landmarker in VIDEO mode (tracks hands from frame to frame)."""

    def __init__(self, camera=CAMERA_INDEX, max_hands=MAX_HANDS):
        # Windows: DirectShow opens webcams faster. It does not exist on Linux (V4L2 there).
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(camera, backend)
        if not self.cap.isOpened():
            raise SystemExit(f"Could not open webcam {camera} (try another CAMERA_INDEX)")
        options = vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(MODEL_PATH)),
            running_mode=vision.RunningMode.VIDEO,   # reuse the previous frame -> faster, smoother
            num_hands=max_hands,
            min_hand_detection_confidence=MIN_CONFIDENCE,
            min_hand_presence_confidence=MIN_CONFIDENCE,
            min_tracking_confidence=MIN_CONFIDENCE,
        )
        self.detector = vision.HandLandmarker.create_from_options(options)
        self.t0 = time.monotonic()

    def read(self):
        """Grab one frame and detect the hands. Returns (frame, [Hand, ...]) or (None, [])."""
        ok, frame = self.cap.read()
        if not ok:
            return None, []
        if MIRROR_VIEW:
            frame = cv2.flip(frame, 1)                       # 1 = flip left-right
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)          # OpenCV is BGR, MediaPipe wants RGB
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        t_ms = int((time.monotonic() - self.t0) * 1000)      # VIDEO mode needs increasing timestamps
        result = self.detector.detect_for_video(image, t_ms)
        hands = []
        for landmarks, handedness in zip(result.hand_landmarks, result.handedness):
            side, score = handedness[0].category_name, handedness[0].score
            if SWAP_HANDEDNESS:
                side = "Left" if side == "Right" else "Right"
            hands.append(Hand(side, landmarks, score))
        return frame, hands

    def close(self):
        self.detector.close()
        self.cap.release()
        cv2.destroyAllWindows()


def draw_hands(frame, hands, labels=None):
    """Draw skeleton + side label of every hand. labels: optional {side: extra text}."""
    h, w = frame.shape[:2]
    for hand in hands:
        pts = [(int(p.x * w), int(p.y * h)) for p in hand.landmarks]   # normalised -> pixels
        color = COLOR.get(hand.side, (255, 255, 255))
        for a, b in HAND_CONNECTIONS:
            cv2.line(frame, pts[a], pts[b], color, 2)
        for i, p in enumerate(pts):
            cv2.circle(frame, p, 5, (0, 0, 255) if i in FINGERTIPS else (0, 200, 0), -1)
        text = f"{hand.side} {hand.score:.2f}"
        if labels and hand.side in labels:
            text += f"  {labels[hand.side]}"
        cv2.putText(frame, text, (pts[0][0] - 40, pts[0][1] + 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)


def main():
    """Demo: show the tracked hands and their side. Q or ESC to quit."""
    tracker = HandTracker()
    t_prev = time.monotonic()
    try:
        while True:
            frame, hands = tracker.read()
            if frame is None:
                print("Could not read a frame, exiting.")
                break
            draw_hands(frame, hands)
            now = time.monotonic()
            fps = 1.0 / max(now - t_prev, 1e-6)
            t_prev = now
            cv2.putText(frame, f"FPS {fps:.0f}  hands {len(hands)}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            cv2.imshow("Hand tracker (Q to quit)", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
    finally:
        tracker.close()


if __name__ == "__main__":
    main()
