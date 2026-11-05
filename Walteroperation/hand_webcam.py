"""
hand_webcam.py - Real-time hand tracking from a webcam using Google MediaPipe.

What this script does, step by step:
  1. Opens a webcam with OpenCV.
  2. Loads Google's pre-trained "Hand Landmarker" neural network
     (the file models/hand_landmarker.task).
  3. For every frame, asks the model where the hands are. For each hand found,
     the model returns 21 "landmarks" (key points: wrist, knuckles, fingertips)
     plus whether it is a left or right hand.
  4. Draws the hand skeleton on the frame and shows it in a window.

How to run it (with the conda environment active):
    python hand_webcam.py              # default webcam (index 0)
    python hand_webcam.py --camera 1   # another webcam, e.g. an external USB one
    python hand_webcam.py --hands 1    # track only one hand (slightly faster)

Press Q or ESC in the video window to quit.

Landmark numbering (the 21 points returned for each hand):

    0  = wrist
    1-4   = thumb   (4  = thumb tip)
    5-8   = index   (8  = index tip)
    9-12  = middle  (12 = middle tip)
    13-16 = ring    (16 = ring tip)
    17-20 = pinky   (20 = pinky tip)

Each landmark has x, y, z:
    x, y -> position in the image, NORMALIZED between 0 and 1
            (x = 0 is the left edge, x = 1 the right edge,
             y = 0 is the top edge,  y = 1 the bottom edge).
            Multiply by the image width/height to get pixels.
    z    -> relative depth with respect to the wrist (smaller = closer to camera).
"""

import argparse          # reads command-line options such as --camera
import time              # used for timestamps and the FPS counter
from pathlib import Path  # builds file paths that work on any OS

import cv2                # OpenCV: webcam access, drawing, display window
import mediapipe as mp    # Google MediaPipe: image container and the ML runtime
from mediapipe.tasks import python as mp_python  # generic task options (BaseOptions)
from mediapipe.tasks.python import vision        # vision tasks, incl. HandLandmarker


# --------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------

# Path to the pre-trained model file. It is resolved relative to THIS script, so the
# script works no matter which folder you launch it from.
MODEL_PATH = Path(__file__).parent / "models" / "hand_landmarker.task"

# Pairs of landmark indices to connect with a line, so the 21 points look like a hand.
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),          # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),          # index finger
    (5, 9), (9, 10), (10, 11), (11, 12),     # middle finger
    (9, 13), (13, 14), (14, 15), (15, 16),   # ring finger
    (13, 17), (17, 18), (18, 19), (19, 20),  # pinky
    (0, 17),                                 # closes the palm (wrist -> pinky base)
]

# Indices of the fingertips, drawn in a different colour.
FINGERTIPS = (4, 8, 12, 16, 20)

# Colours in OpenCV are BGR (Blue, Green, Red), NOT RGB.
COLOR_BONES = (255, 255, 255)   # white lines between landmarks
COLOR_JOINT = (0, 200, 0)       # green dots on joints
COLOR_TIP = (0, 0, 255)         # red dots on fingertips
COLOR_LABEL = (255, 200, 0)     # light blue "Left/Right" label
COLOR_HUD = (0, 255, 255)       # yellow FPS text


# --------------------------------------------------------------------------------------
# Model setup
# --------------------------------------------------------------------------------------

def create_detector(num_hands: int) -> vision.HandLandmarker:
    """Load the Hand Landmarker model and return a ready-to-use detector."""
    options = vision.HandLandmarkerOptions(
        # Where the model file is.
        base_options=mp_python.BaseOptions(model_asset_path=str(MODEL_PATH)),
        # VIDEO mode: frames come from a continuous stream. The model uses the
        # previous frame to track hands faster and more smoothly than detecting
        # from scratch every time (that would be IMAGE mode).
        running_mode=vision.RunningMode.VIDEO,
        # Maximum number of hands to look for.
        num_hands=num_hands,
        # Confidence thresholds, from 0 to 1. Higher = fewer false detections,
        # but hands may be lost more easily.
        min_hand_detection_confidence=0.5,  # to detect a NEW hand in the image
        min_hand_presence_confidence=0.5,   # to decide a hand is still there
        min_tracking_confidence=0.5,        # to keep tracking instead of re-detecting
    )
    return vision.HandLandmarker.create_from_options(options)


# --------------------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------------------

def draw_hands(frame, result) -> None:
    """Draw every detected hand on `frame` (modified in place)."""
    height, width = frame.shape[:2]

    # result.hand_landmarks -> one list of 21 landmarks per detected hand
    # result.handedness     -> for each hand, its "Left"/"Right" classification
    for landmarks, handedness in zip(result.hand_landmarks, result.handedness):
        # Convert normalized coordinates (0..1) into pixel coordinates.
        points = [(int(lm.x * width), int(lm.y * height)) for lm in landmarks]

        # Draw the "bones" first, so the dots are drawn on top of them.
        for start, end in HAND_CONNECTIONS:
            cv2.line(frame, points[start], points[end], COLOR_BONES, 2)

        # Draw one dot per landmark: red for fingertips, green for the rest.
        for index, point in enumerate(points):
            color = COLOR_TIP if index in FINGERTIPS else COLOR_JOINT
            cv2.circle(frame, point, 5, color, -1)  # -1 = filled circle

        # Write "Left"/"Right" and the model's confidence just below the wrist.
        best_guess = handedness[0]           # the most likely classification
        label = best_guess.category_name     # "Left" or "Right"
        score = best_guess.score             # confidence from 0 to 1
        wrist_x, wrist_y = points[0]
        cv2.putText(frame, f"{label} {score:.2f}", (wrist_x - 40, wrist_y + 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLOR_LABEL, 2)


# --------------------------------------------------------------------------------------
# Main loop
# --------------------------------------------------------------------------------------

def main() -> None:
    # Read the command-line options.
    parser = argparse.ArgumentParser(description="Real-time hand tracking demo.")
    parser.add_argument("--camera", type=int, default=0,
                        help="webcam index (0 = default camera)")
    parser.add_argument("--hands", type=int, default=2,
                        help="maximum number of hands to track")
    args = parser.parse_args()

    # Open the webcam. CAP_DSHOW (DirectShow) opens cameras faster on Windows.
    cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise SystemExit(f"Could not open webcam {args.camera}")

    start_time = time.monotonic()   # reference time for the model timestamps
    previous_time = start_time      # used to compute FPS

    # "with" makes sure the model is released correctly when we exit the loop.
    with create_detector(args.hands) as detector:
        while True:
            # 1) Grab a frame from the webcam.
            ok, frame = cap.read()
            if not ok:
                print("Could not read a frame, exiting.")
                break

            # 2) Mirror the image horizontally so it behaves like a mirror.
            #    Note: this also swaps what the model calls "Left" and "Right".
            frame = cv2.flip(frame, 1)

            # 3) OpenCV gives BGR images, MediaPipe expects RGB: convert, then wrap
            #    the pixels in a MediaPipe Image object.
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            # 4) Run the model. In VIDEO mode every frame needs a timestamp in
            #    milliseconds that always increases.
            timestamp_ms = int((time.monotonic() - start_time) * 1000)
            result = detector.detect_for_video(mp_image, timestamp_ms)

            # 5) Draw the detected hands on the original (BGR) frame.
            draw_hands(frame, result)

            # 6) Compute and show FPS (frames per second) and the number of hands.
            now = time.monotonic()
            fps = 1.0 / max(now - previous_time, 1e-6)  # avoid division by zero
            previous_time = now
            cv2.putText(frame, f"FPS {fps:.0f}  hands: {len(result.hand_landmarks)}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, COLOR_HUD, 2)

            # 7) Show the frame. waitKey(1) waits 1 ms for a key press and is also
            #    what makes the window refresh. Quit on Q or ESC (key code 27).
            cv2.imshow("Walter - Hand Tracking (press Q to quit)", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break

    # Release the webcam and close the window.
    cap.release()
    cv2.destroyAllWindows()


# Run main() only when the file is executed directly (python hand_webcam.py),
# not when it is imported from another script.
if __name__ == "__main__":
    main()
