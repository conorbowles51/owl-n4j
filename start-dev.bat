@echo off
echo Starting backend and frontend...

:: Backend window
start powershell -NoExit -Command "cd 'C:\Users\35386\Documents\Projects\investigations\owl-n4j\backend'; ..\.venv\Scripts\Activate.ps1; python main.py"

:: Frontend window
start powershell -NoExit -Command "cd 'C:\Users\35386\Documents\Projects\investigations\owl-n4j\frontend_v2'; npm run dev"

exit
