@echo off
pyinstaller --noconfirm --clean --onefile --noconsole --icon=icon.ico main.py
echo Build complete. Check the "dist" folder for main.exe
pause
