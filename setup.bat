@echo off
title D&D Session Recorder - Setup
echo.
echo ============================================================
echo   D^&D Session Recorder - Setup
echo ============================================================
echo.

:: Check for Node.js
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Node.js is not installed.
    echo         Download it from: https://nodejs.org/
    echo         Install the LTS version, then re-run this script.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('node -v') do set NODE_VER=%%i
echo [OK] Node.js found: %NODE_VER%

:: Check for Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed.
    echo         Download it from: https://www.python.org/downloads/
    echo         Make sure to check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do set PY_VER=%%i
echo [OK] Python found: %PY_VER%

:: Check for NVIDIA GPU (optional)
echo.
where nvidia-smi >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [OK] NVIDIA GPU detected - transcription will use GPU acceleration
    set HAS_GPU=1
) else (
    echo [--] No NVIDIA GPU detected - transcription will use CPU (slower but works fine)
    set HAS_GPU=0
)

:: Install Node.js dependencies
echo.
echo ------------------------------------------------------------
echo Installing Node.js dependencies...
echo ------------------------------------------------------------
call npm install
if %ERRORLEVEL% neq 0 (
    echo [ERROR] npm install failed. Check the errors above.
    pause
    exit /b 1
)
echo [OK] Node.js dependencies installed

:: Set up Python virtual environment
echo.
echo ------------------------------------------------------------
echo Setting up Python transcription environment...
echo ------------------------------------------------------------
cd transcriber
if not exist "venv" (
    python -m venv venv
)
call venv\Scripts\activate.bat

pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python dependency install failed. Check the errors above.
    pause
    exit /b 1
)

:: Install GPU support if NVIDIA detected
if "%HAS_GPU%"=="1" (
    echo.
    echo Installing GPU acceleration libraries...
    pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
    echo [OK] GPU libraries installed
)

call deactivate
cd ..

:: Configure bot token
echo.
echo ============================================================
echo   Configuration
echo ============================================================
echo.

if exist ".env" (
    findstr /c:"your_bot_token_here" .env >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        goto :ask_token
    ) else (
        echo [OK] Bot token already configured in .env
        goto :skip_token
    )
)

:ask_token
echo You need a Discord bot token to run this bot.
echo.
echo To get one:
echo   1. Go to https://discord.com/developers/applications
echo   2. Click "New Application" and give it a name
echo   3. Go to "Bot" in the left sidebar
echo   4. Click "Reset Token" and copy the token
echo   5. Under "Privileged Gateway Intents", enable:
echo      - Server Members Intent
echo      - Message Content Intent
echo.
set /p BOT_TOKEN="Paste your bot token here (or press Enter to skip): "

if "%BOT_TOKEN%"=="" (
    echo.
    echo [--] Skipped. Edit the .env file manually before running the bot.
) else (
    echo DISCORD_TOKEN=%BOT_TOKEN%> .env
    echo PREFIX=!>> .env
    echo [OK] Token saved to .env
)

:skip_token

:: Reset character map if it still has placeholders
findstr /c:"DiscordUsername1" config\characters.json >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo.
    echo ------------------------------------------------------------
    echo   Character Map Setup
    echo ------------------------------------------------------------
    echo.
    echo You'll need to map Discord user IDs to character names.
    echo.
    echo To get a user ID:
    echo   1. In Discord, go to Settings ^> Advanced ^> enable Developer Mode
    echo   2. Right-click a username ^> Copy User ID
    echo.
    echo Edit config\characters.json with your player mappings:
    echo   {
    echo     "characterMap": {
    echo       "123456789012345678": "CharacterName",
    echo       "987654321098765432": "AnotherCharacter"
    echo     },
    echo     "dmUsername": "123456789012345678"
    echo   }
    echo.
)

:: Invite URL reminder
echo.
echo ============================================================
echo   Almost done! Add the bot to your Discord server:
echo ============================================================
echo.
echo   1. Go to your app at https://discord.com/developers/applications
echo   2. Click OAuth2 ^> URL Generator
echo   3. Check: bot (under Scopes)
echo   4. Check permissions: Connect, Speak, View Channels,
echo      Send Messages, Read Message History
echo   5. Copy the URL and open it in your browser
echo   6. Select your server and authorize
echo.
echo ============================================================
echo   Setup complete! To start the bot, run:
echo.
echo       npm start
echo.
echo   Commands in Discord:
echo       !join              - Bot joins your voice channel
echo       !session start "X" - Start recording
echo       !session stop      - Stop recording
echo       !leave             - Bot leaves voice channel
echo.
echo   After recording, transcribe with:
echo       cd transcriber
echo       venv\Scripts\activate
echo       python transcribe.py --preset quality
echo ============================================================
echo.
pause
