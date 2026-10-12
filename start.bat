@echo off
setlocal enabledelayedexpansion
title Network Health Monitoring and SDN System Manager

:: Ensure current working directory is the repository folder
cd /d "%~dp0"

:CHECK_PYTHON
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set PY_CMD=python
    goto CHECK_DEPS
)
where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set PY_CMD=py
    goto CHECK_DEPS
)
echo [ERROR] Python was not found in your system PATH!
echo Please install Python 3 and ensure it is added to your PATH.
echo.
pause
exit /b 1

:CHECK_DEPS
%PY_CMD% -c "import flask, psutil" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ========================================================================
    echo  [*] Installing required Python packages from requirements.txt...
    echo ========================================================================
    if exist requirements.txt (
        %PY_CMD% -m pip install -r requirements.txt
    ) else (
        %PY_CMD% -m pip install flask psutil
    )
    if %ERRORLEVEL% neq 0 (
        echo [WARNING] Automatic pip install failed. Please run 'pip install -r requirements.txt' manually.
    )
)

:MENU
cls
echo ========================================================================
echo   NETWORKING COURSE PROJECT: HEALTH MONITORING AND SDN SYSTEM
echo ========================================================================
echo.
echo   [1] Start Local Simulation (Controller + Server + 3 Agents + UI)
echo   [2] Run Automated Verification Suite (demo_runner.py)
echo   [3] Open Web Dashboard in Browser (http://127.0.0.1:5050)
echo   [4] Launch Mininet Topology in WSL (Linux: topology.py)
echo   [5] Stop All Running Components
echo   [Q] Quit
echo.
echo ========================================================================
set "CHOICE="
set /p CHOICE="Select an option [1-5, Q] (Default: 1): "

if not defined CHOICE set CHOICE=1
if "%CHOICE%"=="1" goto START_SIMULATION
if "%CHOICE%"=="2" goto RUN_TESTS
if "%CHOICE%"=="3" goto OPEN_BROWSER
if "%CHOICE%"=="4" goto LAUNCH_WSL
if "%CHOICE%"=="5" goto STOP_ALL
if /i "%CHOICE%"=="Q" goto QUIT
goto MENU

:START_SIMULATION
echo.
echo ========================================================================
echo   LAUNCHING LOCAL NETWORK HEALTH AND SDN SIMULATION
echo ========================================================================
echo [*] Starting SDN Controller on port 8080...
start "SDN Controller" %PY_CMD% sdn_controller.py
timeout /t 1 /nobreak >nul

echo [*] Starting Central Monitoring Server on port 5050...
start "Central Server" %PY_CMD% server.py
timeout /t 2 /nobreak >nul

echo [*] Launching 3 Host Agents: Node-1, Node-2, Node-3...
start "Agent Node-1" %PY_CMD% agent.py --agent-id Node-1 --c2-port 5001
start "Agent Node-2" %PY_CMD% agent.py --agent-id Node-2 --c2-port 5002
start "Agent Node-3" %PY_CMD% agent.py --agent-id Node-3 --c2-port 5003

echo.
echo [*] Waiting 3 seconds for sockets to initialize...
timeout /t 3 /nobreak >nul

echo [*] Opening Web Dashboard in default browser: http://127.0.0.1:5050
start http://127.0.0.1:5050

echo.
echo ========================================================================
echo   SYSTEM IS RUNNING!
echo   - Web Dashboard:  http://127.0.0.1:5050
echo   - SDN REST API:   http://127.0.0.1:8080
echo   - UDP Telemetry:  Port 5000
echo ========================================================================
echo.
echo Options:
echo   [T] Run Automated Verification Suite (demo_runner.py)
echo   [K] Stop / Kill all background components
echo   [M] Return to Main Menu
echo.

:SIM_LOOP
set "SUBCHOICE="
set /p SUBCHOICE="Action [T / K / M]: "
if /i "%SUBCHOICE%"=="T" goto RUN_TESTS
if /i "%SUBCHOICE%"=="K" goto STOP_ALL
if /i "%SUBCHOICE%"=="M" goto MENU
goto SIM_LOOP

:RUN_TESTS
echo.
echo ========================================================================
echo   RUNNING AUTOMATED EVALUATION TEST SUITE
echo ========================================================================
%PY_CMD% -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5050/api/metrics', timeout=1)" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [*] No running server detected. Starting local cluster for test suite...
    start "SDN Controller" /min %PY_CMD% sdn_controller.py
    start "Central Server" /min %PY_CMD% server.py
    timeout /t 2 /nobreak >nul
    start "Agent Node-1" /min %PY_CMD% agent.py --agent-id Node-1 --c2-port 5001
    start "Agent Node-2" /min %PY_CMD% agent.py --agent-id Node-2 --c2-port 5002
    start "Agent Node-3" /min %PY_CMD% agent.py --agent-id Node-3 --c2-port 5003
    timeout /t 3 /nobreak >nul
    echo [*] Test cluster active. Running tests...
    echo.
)
%PY_CMD% demo_runner.py --server-url http://127.0.0.1:5050
echo.
pause
goto MENU

:OPEN_BROWSER
start http://127.0.0.1:5050
goto MENU

:LAUNCH_WSL
where wsl >nul 2>&1
if %ERRORLEVEL% neq 0 goto NO_WSL

echo.
echo ========================================================================
echo   LAUNCHING MININET TOPOLOGY INSIDE WSL
echo ========================================================================
echo Note: Mininet requires a Linux distribution in WSL with root privileges.
echo [*] Checking Python 3 inside WSL...
wsl python3 --version >nul 2>&1
if %ERRORLEVEL% neq 0 goto WSL_NO_PYTHON

echo [*] Starting Mininet topology in WSL...
wsl sudo python3 topology.py
echo.
pause
goto MENU

:WSL_NO_PYTHON
echo.
echo [ERROR] Python 3 is not found in your default WSL Linux environment.
echo Mininet and topology.py require an Ubuntu/Debian WSL distribution with Mininet and Python 3.
echo.
echo TIP: If you want to run and test the complete system on Windows right now:
echo   --^> Select Option [1] "Start Local Simulation" from the menu!
echo       It runs the controller, server, 3 agents, and live web UI natively on Windows.
echo.
pause
goto MENU

:NO_WSL
echo.
echo [ERROR] WSL (Windows Subsystem for Linux) is not detected on this machine.
echo Mininet requires Linux or WSL to run kernel network namespaces and Open vSwitch.
echo.
echo TIP: To run the system on Windows without WSL:
echo   --^> Select Option [1] "Start Local Simulation" from the menu!
echo.
pause
goto MENU

:STOP_ALL
echo.
echo [*] Stopping running simulation components...
taskkill /F /FI "WINDOWTITLE eq SDN Controller*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Central Server*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Agent Node-1*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Agent Node-2*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Agent Node-3*" >nul 2>&1
echo [OK] All components terminated.
timeout /t 1 /nobreak >nul
goto MENU

:QUIT
exit /b 0
