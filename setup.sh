#!/bin/bash
# D&D Session Recorder - Setup Script

echo ""
echo "============================================================"
echo "  D&D Session Recorder - Setup"
echo "============================================================"
echo ""

# Check for Node.js
if ! command -v node &> /dev/null; then
    echo "[ERROR] Node.js is not installed."
    echo "        Install it from: https://nodejs.org/"
    echo "        Or use your package manager (brew install node, apt install nodejs)"
    exit 1
fi
echo "[OK] Node.js found: $(node -v)"

# Check for Python
PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "[ERROR] Python is not installed."
    echo "        Install Python 3.10+ from: https://www.python.org/downloads/"
    exit 1
fi
echo "[OK] Python found: $($PYTHON_CMD --version)"

# Check for NVIDIA GPU (optional)
echo ""
HAS_GPU=0
if command -v nvidia-smi &> /dev/null; then
    echo "[OK] NVIDIA GPU detected - transcription will use GPU acceleration"
    HAS_GPU=1
else
    echo "[--] No NVIDIA GPU detected - transcription will use CPU (slower but works fine)"
fi

# Install Node.js dependencies
echo ""
echo "------------------------------------------------------------"
echo "Installing Node.js dependencies..."
echo "------------------------------------------------------------"
npm install
if [ $? -ne 0 ]; then
    echo "[ERROR] npm install failed. Check the errors above."
    exit 1
fi
echo "[OK] Node.js dependencies installed"

# Set up Python virtual environment
echo ""
echo "------------------------------------------------------------"
echo "Setting up Python transcription environment..."
echo "------------------------------------------------------------"
cd transcriber

if [ ! -d "venv" ]; then
    $PYTHON_CMD -m venv venv
fi

source venv/bin/activate

pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "[ERROR] Python dependency install failed. Check the errors above."
    exit 1
fi

# Install GPU support if NVIDIA detected
if [ "$HAS_GPU" -eq 1 ]; then
    echo ""
    echo "Installing GPU acceleration libraries..."
    pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
    echo "[OK] GPU libraries installed"
fi

deactivate
cd ..

# Configure bot token
echo ""
echo "============================================================"
echo "  Configuration"
echo "============================================================"
echo ""

if [ -f ".env" ] && ! grep -q "your_bot_token_here" .env; then
    echo "[OK] Bot token already configured in .env"
else
    echo "You need a Discord bot token to run this bot."
    echo ""
    echo "To get one:"
    echo "  1. Go to https://discord.com/developers/applications"
    echo "  2. Click 'New Application' and give it a name"
    echo "  3. Go to 'Bot' in the left sidebar"
    echo "  4. Click 'Reset Token' and copy the token"
    echo "  5. Under 'Privileged Gateway Intents', enable:"
    echo "     - Server Members Intent"
    echo "     - Message Content Intent"
    echo ""
    read -p "Paste your bot token here (or press Enter to skip): " BOT_TOKEN

    if [ -z "$BOT_TOKEN" ]; then
        echo ""
        echo "[--] Skipped. Edit the .env file manually before running the bot."
    else
        echo "DISCORD_TOKEN=$BOT_TOKEN" > .env
        echo "PREFIX=!" >> .env
        echo "[OK] Token saved to .env"
    fi
fi

# Character map reminder
if grep -q "DiscordUsername1" config/characters.json 2>/dev/null; then
    echo ""
    echo "------------------------------------------------------------"
    echo "  Character Map Setup"
    echo "------------------------------------------------------------"
    echo ""
    echo "You'll need to map Discord user IDs to character names."
    echo ""
    echo "To get a user ID:"
    echo "  1. In Discord, go to Settings > Advanced > enable Developer Mode"
    echo "  2. Right-click a username > Copy User ID"
    echo ""
    echo "Edit config/characters.json with your player mappings:"
    echo '  {'
    echo '    "characterMap": {'
    echo '      "123456789012345678": "CharacterName",'
    echo '      "987654321098765432": "AnotherCharacter"'
    echo '    },'
    echo '    "dmUsername": "123456789012345678"'
    echo '  }'
    echo ""
fi

# Done
echo ""
echo "============================================================"
echo "  Almost done! Add the bot to your Discord server:"
echo "============================================================"
echo ""
echo "  1. Go to your app at https://discord.com/developers/applications"
echo "  2. Click OAuth2 > URL Generator"
echo "  3. Check: bot (under Scopes)"
echo "  4. Check permissions: Connect, Speak, View Channels,"
echo "     Send Messages, Read Message History"
echo "  5. Copy the URL and open it in your browser"
echo "  6. Select your server and authorize"
echo ""
echo "============================================================"
echo "  Setup complete! To start the bot, run:"
echo ""
echo "      npm start"
echo ""
echo "  Commands in Discord:"
echo "      !join              - Bot joins your voice channel"
echo '      !session start "X" - Start recording'
echo "      !session stop      - Stop recording"
echo "      !leave             - Bot leaves voice channel"
echo ""
echo "  After recording, transcribe with:"
echo "      cd transcriber"
echo "      source venv/bin/activate"
echo "      python transcribe.py --preset quality"
echo "============================================================"
echo ""
