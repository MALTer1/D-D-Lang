@echo off
echo Installing PyInstaller (only needed the first time)...
pip install pyinstaller

echo.
echo Building DndLangIDE.exe...
pyinstaller --onefile --windowed --icon=dndlang_icon.ico --name DndLangIDE ide.py

echo.
echo Done! Your .exe is inside the "dist" folder: dist\DndLangIDE.exe
pause
