# HandJog - Hand-gesture teleoperation of the Estun ER4-550

A normal webcam + Google MediaPipe recognise hand gestures on the PC; the robot asks the PC
for the current command about every 200 ms and makes one small step.

```
PC (Python)                                      Robot (Estun, workspace handjog) 
webcam -> hand_tracker -> gestures               Teleop_Gesti  (motion, load + Start this)
       -> robot_server (port 9500) <--- "REQ" --- Teleop_Comm   (socket, started by Teleop_Gesti)
                                   ---  "3"  --->      |
                                                 Teleop_Region (ellipsoid check, CALLed by Teleop_Gesti)
```

## Folder

```
HandJog/
├── README.md                   this file
├── src/                        Python side (run from the walter venv, see the main README)
│   ├── teleop_hands.py         RUN THIS: webcam + gestures + TCP server towards the robot
│   ├── hand_tracker.py         webcam + MediaPipe, the only file using MediaPipe
│   │                           (python hand_tracker.py = demo, check the Right/Left label)
│   ├── gestures.py             gesture rules for both hands + Stabilizer
│   │                           (python gestures.py = practice mode, no robot)
│   ├── robot_server.py         TCP server on port 9500 and the command-code table (COMMANDS)
│   ├── keyboard_teleop.py      drive the robot from the keyboard, no webcam (Windows only)
│   ├── fake_robot.py           pretends to be the robot: test the Python side without Estun
│   └── models/
│       └── hand_landmarker.task   MediaPipe pre-trained hand model (do not delete)
└── handjog/                    Estun workspace, import handjog.ers
    ├── handjog.ers             workspace file
    └── Project/
        ├── _global.erd         global variables (pose_home, TARGET, Gripper)
        └── Teleop.er/          the teleoperation project
            ├── Teleop_Gesti.erp    MOTION PROGRAM, load this one and press Start.
            │                       SETTINGS at the top: PC IP, port, step sizes, J5/J6 limits
            ├── Teleop_Comm.erp     socket program, started by Teleop_Gesti with RUN
            │                       (never start it by hand): REQ -> number -> I_CMD
            ├── Teleop_Region.erp   working region: ellipsoid around home, called with CALL
            │                       before every Cartesian step. SETTINGS at the top
            └── prjglobal.erd       project variables (English names, one per setting)
```
Every Python file and every Estun program has its **SETTINGS block at the top**.
Files ending in `.mk`, `.var`, the `VarC` / `VarE` folders and the empty `.erd` files are
written by Estun Editor itself: leave them alone.

## Gestures

Move as in front of a mirror. If both hands give a command the right hand wins.

| Hand | Gesture | Command | Robot |
|---|---|---|---|
| Right | index pointing left / right | `left` / `right` | +Y / -Y (step of 20 mm) |
| Right | index pointing up / down | `up` / `down` | +Z / -Z |
| Right | fist, thumb up / down | `forward` / `backward` | +X / -X |
| Left | index pointing up / down | `j5_up` / `j5_down` | J5 +5 / -5 deg (tilts the gripper) |
| Left | fist, thumb up / down | `j6_cw` / `j6_ccw` | J6 +10 / -10 deg (turns the gripper) |
| Left | horns (index + pinky up) | `close` | close gripper (hold ~0.3 s) |
| Left | open palm (five fingers) | `open` | open gripper (hold ~0.3 s) |
| any | anything else / no hand | `stop` | stand still |

Keys in the video window: **Q** quit (robot goes home), **O / C** open / close gripper.

**Left / right hand check (do it once):** run `python hand_tracker.py`, raise only your RIGHT
hand: the label must say `Right`. If it says `Left`, set `SWAP_HANDEDNESS = True` at the top of
`hand_tracker.py`. (`cv2.flip` only mirrors the picture so the window feels like a mirror; the
Right/Left label comes from the model, so the fix is this flag, not removing the flip: removing
it would also reverse every left/right command.)

## 1. Python setup (once)

Use the `walter` virtual environment of the whole repository: run `setup.bat` in the
repository root, then `walter\Scripts\activate` (see *Setup* in the [main README](../README.md)).
Then go to this folder:
```bat
cd HandJog\src
```

## 2. Three ways to run it

### A. Python only (no Estun at all) - test gestures and protocol
```bat
:: terminal 1
python teleop_hands.py          (or: python keyboard_teleop.py)
:: terminal 2
python fake_robot.py
```
`fake_robot.py` behaves like the robot program (same steps, limits and ellipsoid) and prints the
simulated position.

### B. Estun simulation (virtual controller, no real robot)
1. Estun Editor -> import `handjog/handjog.ers` -> **Connect -> Virtual controller -> ER4-550**.
2. Right-click the workspace -> **Download**.
3. `Teleop_Gesti.erp`, SETTINGS: `t_p.S_PC_IP.value = "127.0.0.1"`.
4. Start the Python side **first**: `python teleop_hands.py` (or `keyboard_teleop.py`).
5. Load `Teleop.er / Teleop_Gesti` -> Enable -> Start. The pendant shows *TELEOP CONNECTED TO PC*.

### C. Real robot
1. PC wired to the robot network, **static IP** on that adapter (same subnet as the controller).
2. `Teleop_Gesti.erp`, SETTINGS: `t_p.S_PC_IP.value = "<your PC IP>"` (from `ipconfig`).
3. Start `python teleop_hands.py` first, then load and Start `Teleop_Gesti`.
4. First runs: manual mode, low global speed, single step, E-stop at hand.

## 3. IP / connection checklist

| Check | Where | Value |
|---|---|---|
| IP of the PC that runs Python, as seen by the robot | `Teleop_Gesti.erp`, line `t_p.S_PC_IP.value = ...` (this line overwrites the variable at every start, so change it **here**) | `127.0.0.1` virtual controller, PC IP for the real robot |
| Port | `t_p.I_PC_PORT.value` in Teleop_Gesti and `PORT` in `teleop_hands.py`, `keyboard_teleop.py`, `robot_server.py`, `fake_robot.py` | `9500` everywhere (9000 is taken by Estun Editor) |
| PC IP | `ipconfig`, adapter connected to the robot | same subnet as the controller, static |
| Editor -> controller | Estun Editor Connect | **controller** IP (different from the PC IP!), test with `ping` |
| Firewall | first run of the Python script | allow Python on Private **and** Public networks, or once as admin: `netsh advfirewall firewall add rule name="Estun teleop 9500" dir=in action=allow protocol=TCP localport=9500` |
| `fake_robot.py` on another PC | `python fake_robot.py --ip <PC running teleop_hands>` | |
| Pendant message *PC CONNECTION ERROR* | Python was not started first, wrong IP, or firewall | |

## 4. Working region (ellipsoid)

`Teleop_Region.erp` accepts a step only if the new point is inside an ellipsoid fixed to the
home pose (home is about x 274, y 14, z 231 mm):

    ((x-cx)/AX)^2 + ((y-cy)/AY)^2 + ((z-cz)/AZ)^2 <= 1,   centre = home + (60, 10, -50) mm,
    semi axes AX 100, AY 110, AZ 75 mm  ->  x 234..434, y -86..134, z 106..256

Why an ellipsoid and not a box: the corners of a box are the dangerous places (far + low =
arm fully stretched, close to the base = wrist near the J1 axis). The ellipsoid cuts them and
matches the box your team already tested (x 254..434, y -86..134, z 111..231) on its main
extents. Home is inside with margin (0.81 of the limit).
Note: home is in the upper part of the ellipsoid, where it is narrower; to reach far forward,
go down a bit first.
**Before using it on the real robot, jog to the six extreme points with the pendant** and change
the SETTINGS in `Teleop_Region.erp` (and the same numbers in `fake_robot.py`) if needed.
J5 / J6 use step counters instead (J5 within +-30 deg, J6 within +-180 deg from home), which keeps
J5 away from its zero (the wrist singularity) - check the J5 value at home on the pendant.

## 5. First run on Estun - things to verify

These instructions were written by hand and not yet run on the controller. If the Editor marks
one in red, delete it and insert it again from *Command Navigation* with the same parameters:

| Line | Program | Why check |
|---|---|---|
| `GetCurCPos{P=t_g.TARGET}` | Teleop_Gesti | reads the real pose after a J5/J6 step |
| `WaitFinish{Percent=100}` | Teleop_Gesti | waits the end of the joint step |
| `MovJRel{P=t_p.D_JOINT,V=t_s.V30}` | Teleop_Gesti | joint step |
| `StrToI ( t_p.S_Rx.value )` | Teleop_Comm | turns the answer "3" into 3 |

Also check: motion is still smooth with the `CALL Teleop_Region` between steps (if it becomes
stop-and-go, copy the region lines inside Teleop_Gesti instead of the CALL), and the signs of
J5 / J6 (if a gesture turns the wrong way, swap the words in `LEFT_HAND` in `gestures.py`).

## Protocol (both sides must use the same table)

| code | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| word | left | right | forward | backward | up | down | stop | quit | open | close | j5_up | j5_down | j6_cw | j6_ccw |

0 = timeout / invalid (robot stays still). Python table: `COMMANDS` in `robot_server.py`.
