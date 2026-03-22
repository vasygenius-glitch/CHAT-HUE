@echo off
echo ========================================================
echo Fuzzy Search App - Installer and EXE Builder
echo ========================================================
echo.
echo Please make sure you have Python installed on your system!
echo Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Python is not installed or not added to PATH.
    echo Please download and install Python from https://www.python.org/downloads/
    echo Make sure to check the box "Add Python to PATH" during installation.
    pause
    goto :EOF
)

echo.
echo Installing required libraries...
pip install PyQt6 beautifulsoup4 python-docx rapidfuzz PyMuPDF pyinstaller

echo.
echo Building the .exe file... Please wait, this might take a minute.
pyinstaller --noconfirm --onedir --windowed --name "FuzzySearch" --icon="assets\app.ico" --add-data "style.qss;." --add-data "assets\app.ico;assets" main.py

echo.
echo ========================================================
echo SUCCESS!
echo Your program is ready.
echo You can find it inside the "dist\FuzzySearch" folder.
echo Just double-click on "FuzzySearch.exe" to run it!
echo ========================================================
pause
