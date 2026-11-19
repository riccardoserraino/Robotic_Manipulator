# HandJog - Hand-gesture teleoperation of the Estun ER4-550

A normal webcam + Google MediaPipe recognise hand gestures on the PC; the robot asks the PC
for the current command about every 200 ms and makes one small step.

```
PC (Python)                                      Robot (Estun, workspace handjog_v2)
webcam -> hand_tracker -> gestures               Teleop_Gesti  (motion, load + Start this)
       -> robot_server (port 9500) <--- "REQ" --- Teleop_Comm   (socket, started by Teleop_Gesti)
                                   ---  "3"  --->      |
                                                 Teleop_Region (region check, CALLed)
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
│   ├── plot_region.py          draws robot, tool frame at home and the working region,
│   │                           and checks your target points (same numbers as Teleop_Region)
│   └── models/
│       └── hand_landmarker.task   MediaPipe pre-trained hand model (do not delete)
└── handjog_v2/                 Estun workspace, import handjog_v2.ers
    ├── handjog_v2.ers          workspace file
    └── Project/
        ├── _global.erd         global variables (pose_home, TARGET, Gripper)
        └── Teleop.er/          the teleoperation project
            ├── Teleop_Gesti.erp    MOTION PROGRAM, load this one and press Start.
            │                       SETTINGS at the top: PC IP, port, step sizes, J5/J6 limits
            ├── Teleop_Comm.erp     socket program, started by Teleop_Gesti with RUN
            │                       (never start it by hand): REQ -> number -> I_CMD
            ├── Teleop_Region.erp   working region: ellipsoid + box + tolerance + hard limits,
            │                       called with CALL before every Cartesian step. SETTINGS at the top
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
| Left | index pointing up / down | `j5_down` / `j5_up` | lifts / lowers the gripper (J5, `R_J5_STEP` = 3 deg per cycle) |
| Left | fist, thumb up / down | `j6_cw` / `j6_ccw` | turns the gripper (J6, `R_J6_STEP` = 6 deg per cycle) |
| Left | horns (index + pinky up) | `close` | close gripper (hold ~0.3 s) |
| Left | open palm (five fingers) | `open` | open gripper (hold ~0.3 s) |
| any | anything else / no hand | `stop` | stand still |

Keys in the video window: **Q** quit (robot goes home), **O / C** open / close gripper.

**Left / right hand check (do it once):** run `python hand_tracker.py`, raise only your RIGHT
hand: the label must say `Right`. If it says `Left`, set `SWAP_HANDEDNESS = True` at the top of
`hand_tracker.py`. (`cv2.flip` only mirrors the picture so the window feels like a mirror; the
Right/Left label comes from the model, so the fix is this flag, not removing the flip: removing
it would also reverse every left/right command.)


## 1. Two ways to run it

### A. Estun simulation (virtual controller, no real robot)
1. Estun Editor -> import `handjog_v2/handjog_v2.ers` -> **Connect -> Virtual controller -> ER4-550**.
2. Right-click the workspace -> **Download**.
3. `Teleop_Gesti.erp`, SETTINGS: `t_p.S_PC_IP.value = "127.0.0.1"`.
4. Start the Python side **first**: `python teleop_hands.py` (or `keyboard_teleop.py`).
5. Load `Teleop.er / Teleop_Gesti` -> Enable -> Start. The pendant shows *TELEOP CONNECTED TO PC*.

### B. Real robot
1. PC wired to the robot network, **static IP** on that adapter (same subnet as the controller).
2. `Teleop_Gesti.erp`, SETTINGS: `t_p.S_PC_IP.value = "<your PC IP>"` (from `ipconfig`).
3. Start `python teleop_hands.py` first, then load and Start `Teleop_Gesti`.
4. First runs: manual mode, low global speed, single step, E-stop at hand.

## 2. Safe working region

Before every Cartesian step, `Teleop_Region` checks the new TCP position. If the step is not
allowed the robot just stays still (no alarm) and the pendant prints why, with the position,
e.g. `TOO FAR x512 y-180 z60`.

**Allowed = inside the ellipsoid AND inside the box, and no hard limit broken.**

- **Ellipsoid ∩ box** (the region you choose). The ellipsoid gives a rounded working volume,
  the box cuts it with flat walls (table side, cage walls). A point must be inside both.
- **Tolerance** `R_TOL` (30 mm): steps up to 30 mm outside the region are still allowed;
  the pendant prints `TOL BAND` when you enter that band.
- **Hard limits** (protect the robot, never relaxed by the tolerance):
  `TABLE` z below `R_Z_FLOOR` · `NEAR BASE` closer than `R_BASE_R` to the J1 axis (base body is
  136 mm) · `TOO FAR` / `WRIST CLOSE` wrist centre farther than `R_REACH_MAX` or closer than
  `R_REACH_MIN` to the shoulder J2 (robot limits 555 / 147 mm, manual Fig. 3-3).

| Parameter (Teleop_Region SETTINGS) | Now |
|---|---|
| ellipsoid centre `R_EX_CX/CY/CZ`, semi-axes `R_EX_AX/AY/AZ` | (300, 0, 350), (400, 400, 600) |
| box `R_BX_XMIN..XMAX`, `YMIN..YMAX`, `ZMIN..ZMAX` | 150..550, -290..290, 30..800 |
| `R_TOL`, `R_Z_FLOOR`, `R_BASE_R` | 30, 30, 150 |
| `R_REACH_MAX`, `R_REACH_MIN` | 530 (never above 555), 212 |
| `R_WRIST_UP` (wrist centre above the TCP = 80.3 + tool 90) | 170.3 |

**Joint limits** (Teleop_Gesti SETTINGS): J5 between `R_J5_MIN` and `R_J5_MAX` (±110) but never
within ±`R_J5_SING` (15°) of zero, the wrist singularity; J6 between `R_J6_MIN` and `R_J6_MAX`
(±350). A refused joint step prints `J LIMIT J5 .. J6 ..`. Joint steps are not checked against
the region.

**Before using new numbers:** set the same values in `src/plot_region.py` and run it. Your
points must come out ALLOWED (dark green in the plot). Then copy them into `Teleop_Region.erp`,
compile and Download. On the real robot a pendant WorkArea slightly larger than this region is
a good extra safety net (it stops with alarm 6181 if the TCP ever leaves it).
