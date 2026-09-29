@echo off
set PROJECT_DIR=C:\path\to\dynamic-cell-culture-drive
set BACKEND_DIR=%PROJECT_DIR%\backend
set FRONTEND_DIR=%PROJECT_DIR%\frontend

REM Create and prepare the backend Python environment
if not exist "%BACKEND_DIR%\venv\Scripts\python.exe" (
    echo Creating backend virtual environment...
    py -3 -m venv "%BACKEND_DIR%\venv"
    if errorlevel 1 exit /b 1
)

call "%BACKEND_DIR%\venv\Scripts\activate.bat"
if errorlevel 1 exit /b 1

echo Installing backend dependencies...
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1
python -m pip install -r "%BACKEND_DIR%\requirements.txt"
if errorlevel 1 exit /b 1


REM Start Docker Desktop (no-op if already running)
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
REM Wait for Docker Engine to become available
echo Waiting for Docker Engine...
:waitfordocker
docker info >nul 2>&1
if errorlevel 1 (
    timeout /t 2 >nul
    goto waitfordocker
)

REM Start services
cd /d "%PROJECT_DIR%"
docker compose -f docker-compose-win.yml up -d
if errorlevel 1 (
    echo Docker Compose failed to start the database services.
    pause
    exit /b 1
)

timeout /t 10 >nul
REM ==========================
REM Start Backend (PowerShell)
REM ==========================
start "Backend API" powershell -NoExit -ExecutionPolicy Bypass -Command "cd '%BACKEND_DIR%'; .\venv\Scripts\Activate.ps1; python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

REM ==========================
REM Start Frontend
REM ==========================
start "Frontend Server" cmd /k "cd /d %FRONTEND_DIR% && npm install && npm run dev"

REM Open browser
timeout /t 2 > nul
start http://localhost:5173
