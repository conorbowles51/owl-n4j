@echo off
echo Starting backend and frontend...

:: Backend window
start powershell -NoExit -Command "cd 'C:\Users\35386\Documents\Projects\investigation-console\backend'; .\.venv\Scripts\Activate.ps1; python main.py"

:: Frontend window
start powershell -NoExit -Command "cd 'C:\Users\35386\Documents\Projects\investigation-console\frontend'; npm run dev"

exit
