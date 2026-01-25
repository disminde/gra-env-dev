@echo off
echo [INFO] Running Database Connection Test...

REM Check if venv exists
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at venv\Scripts\python.exe
    echo [INFO] Creating virtual environment...
    python -m venv venv
    echo [INFO] Installing dependencies...
    venv\Scripts\pip install -r requirements.txt
)

REM Use the python executable from the virtual environment directly
"venv\Scripts\python.exe" tests/test_db_connection.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Test completed successfully.
) else (
    echo.
    echo [FAILURE] Test failed with error code %ERRORLEVEL%.
)

pause
