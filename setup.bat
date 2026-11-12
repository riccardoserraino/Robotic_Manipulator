@echo off
rem Creates the "walter" virtual environment (once) and installs requirements.txt
cd /d "%~dp0"
if not exist walter\Scripts\python.exe python -m venv walter
walter\Scripts\python -m pip install --upgrade pip
walter\Scripts\python -m pip install -r requirements.txt
echo.
echo Done. Activate with:  walter\Scripts\activate
pause
