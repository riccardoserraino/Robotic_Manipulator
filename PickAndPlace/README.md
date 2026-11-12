# Phase 1 - Pick And Place

The camera looks at a tray with 6 slots and returns, for each slot, whether a cylinder
is there and the angle of its groove. The robot picks the first cylinder, rotates it by that
angle, inserts it into the matching hole, goes home and asks for a new photo, until the tray
is empty.

## Folder

```
PickAndPlace/
├── README.md                   
├── CheckPresence.scsln         SCMVS solution: camera recipe that checks the 6 slots and
│                               returns presence;angle for each one (real camera only)
├── fake_cam.py                 fake camera on port 8192, answers "scheme" and "runonce"
│                               like the real one (simulation only, commands listed in the file)
└── pickandplace/               Estun workspace
    ├── pickandplace.ers        
    └── Project/                To import on the teach pendant
        ├── _global.erd 
        ├── _system.erd         
        ├── _array_global.erd                 
        ├── Demo1.er/           pick and place demo
        ├── triangle.er/        first trajectory test (not needed)
        └── GlobalProg.er/      controller default BrakeTest program (not needed)
```
Files ending in `.erd` (other than the variable files), `.mk`, `.var` and the `VarC` / `VarE`
folders are written by Estun Editor itself: leave them alone.

Not needed: `main_v1.erp` (same program as main_v2 with less modularity and without comments), `triangle.er`
(first trajectory test), `GlobalProg.er/BrakeTest` (controller default).

Please for all the software setup relative to both the robot and the camera refer to the [official Robotics Laboratory course guide](https://marco-faroni.github.io/Robotics-Laboratory-Polimi/)

## A. Simulation only (PC, no robot, no camera)

1. Estun Editor -> Connect -> Virtual controller -> ER4-550 (wait) -> File -> Open workspace -> `pickandplace` -> Tool -> Teach Pendant (wait, remember to check Safety Doors are set to '1, sim')
2. Simulation -> Full-function Simulation -> Open Scene (Students_Example.ers) -> Import Model (DRS03726_No_Robot.stl)
3. Right-click the workspace -> Download to Robot (it becomes the active workspace on the teach pendant).
3. Project variable `S_IP_Camera` (Demo1, variable list) = `127.0.0.1`, `I_Porta_Camera` = `8192`.
4. Start the fake camera first (any terminal, any Python 3 on your host)
5. Load `Demo1 / main_v2` -> Enable -> Start. When the fake camera asks, type `t` for a full
   tray cycle (all commands are listed at the top of the file).

## B. Real cell (robot + camera)

1. SCMVS: open `CheckPresence.scsln` (TCP Server port 8192, `runonce` -> OK/NG,
   scheme Auto-Switch = TriggerCommunication with string `scheme`).
2. Project variable `S_IP_Camera` = `192.168.100.100` (the camera IP).
3. Teach `PRESA_1..6`, `FORO_1..6`, `pose_home` with the pendant.
4. Load `main_v2`, run in single step at low speed first.

## IP checklist

| Check | Where | Value |
|---|---|---|
| Camera IP seen by the robot | Estun, project variable `S_IP_Camera` | `127.0.0.1` with fake camera + virtual controller, `192.168.100.100` with the real camera |
| Camera port | `I_Porta_Camera` and `PORT` in `fake_cam.py` and SCMVS TCP Server | `8192` everywhere |
| PC, camera, controller on the same subnet | Windows settings (static IP) | e.g. all `192.168.100.x` |


