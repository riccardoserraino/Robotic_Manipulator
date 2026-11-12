# Robotic Manipulator Control

## Authors

- Riccardo Serraino — [GitHub](https://github.com/riccardoserraino) | [LinkedIn](https://www.linkedin.com/in/riccardoserraino/)
- Giuliano Livi — [GitHub](https://github.com/Giuliano-Livi) | [LinkedIn](https://www.linkedin.com/in/giuliano-livi-524a81335/)
- Enrico Castelli — [GitHub](https://github.com/chettante) | [LinkedIn](https://www.linkedin.com/in/enrico-castelli-4a3b16323/)
- Matteo Giovanelli — [GitHub](https://github.com/mattigiova22) | [LinkedIn](https://www.linkedin.com/in/matteo-giovanelli-4a0029230/)
---
## Introduction
This repository contains the material and resources for a two-phase robotics laboratory based on the **ER4-550-MI** industrial robot, from **Estun**, and a **HIKrobot industrial camera**.
The robot is programmed and operated through the available software environment, while the vision system is used to acquire and process camera data for the robotic application.

---

## Setup (once per PC)
All the Python code of the project (fake camera of Phase 1, MediaPipe teleoperation of Phase 2)
runs in one small virtual environment called **`walter`**, created by `setup.bat`.

1. **Python 3.12 or 3.13** installed from [python.org](https://www.python.org/downloads/), with
   *"Add python.exe to PATH"* ticked. Check in a terminal: `python --version`.
2. **Run `setup.bat`** (in the repository root): double-click it in File Explorer, or from a terminal
   ```bat
   cd <your_path/to/ws>
   .\setup.bat
   ```
   A `.bat` file is already executable on Windows, nothing to enable. The first time it creates
   the `walter` folder (the venv) and installs everything listed in `requirements.txt`
   (MediaPipe, OpenCV, NumPy); running it again only updates the packages.
3. **Use it**
   ```bat
   .\walter\Scripts\activate
   python HandJog\src\teleop_hands.py
   ```
   The prompt starts with `(walter)` when it is active; `deactivate` to leave it.
   In VS Code, open the `ws` folder: `.vscode/settings.json` already selects
   `walter\Scripts\python.exe`, and new terminals activate it by themselves.

Note: If Windows blocks the activation in PowerShell (*"running scripts is disabled"*), run once
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or use a Command Prompt terminal.


---
## Repository map

```
ws/
├── README.md                  
├── setup.bat                  creates the walter venv and installs requirements.txt
├── requirements.txt           Python packages for the whole project
├── PickAndPlace/              PHASE 1
│   ├── README.md              
│   ├── CheckPresence.scsln    
│   ├── fake_cam.py            
│   └── pickandplace/          
└── HandJog/                   PHASE 2
    ├── README.md              
    ├── teleop_v1/             
    └── src/                   
```

Each phase folder is self-contained: everything you need for it is inside, and its README
explains how to run it and its general info.

## Phase 1 - Pick And Place
The camera finds up to 6 cylinders and the groove angle of each one; the robot picks them
one by one, rotates them and inserts them into the matching holes.
See [PickAndPlace](PickAndPlace/README.md).

## Phase 2 - Teleoperation with the hands
Step 1 (HandJog): the right hand jogs the tool in X/Y/Z, the left hand moves the wrist
(J5, J6) and opens/closes the gripper, all through a normal webcam and MediaPipe.
See [HandJog](HandJog/README.md).


