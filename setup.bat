@echo off
rem Creates the "walterai" virtual environment (once) and installs requirements.txt
cd /d "%~dp0"
if not exist walterai\Scripts\python.exe python -m venv walterai
walterai\Scripts\python -m pip install --upgrade pip
walterai\Scripts\python -m pip install -r requirements.txt
echo.
echo Done. Activate with:  walterai\Scripts\activate
pause
