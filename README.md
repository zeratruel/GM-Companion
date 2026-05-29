# D&D Session Recorder Bot

A Discord bot that records voice channel audio during D&D sessions and transcribes it locally using Whisper. Free, private, runs entirely on your hardware.

## Features

- Record per-user audio streams (perfect speaker attribution)
- Transcribe locally with faster-whisper (free, no API keys)
- Auto-detects GPU for fast transcription, falls back to CPU
- Map Discord usernames to character names
- Multiple transcription presets (fast → best quality)
- Condense transcripts by removing filler words and table talk
- JSON output compatible with campaign management tools

## Quick Start

### Windows
```
setup.bat
```

### Mac/Linux
```bash
chmod +x setup.sh
./setup.sh
```

The setup script will:
1. Check that Node.js and Python are installed
2. Install all dependencies
3. Detect GPU and install acceleration libraries if available
4. Walk you through bot token configuration

## Prerequisites

- **Node.js** 18+ — [download](https://nodejs.org/)
- **Python** 3.10+ — [download](https://www.python.org/downloads/)
- A Discord bot token — [create one](https://discord.com/developers/applications)

## Manual Setup

If you prefer to set up manually:

```bash
# Install Node.js dependencies
npm install

# Set up Python environment
cd transcriber
python -m venv venv
venv\Scripts\activate       # Windows
source venv/bin/activate    # Mac/Linux
pip install -r requirements.txt

# Optional: GPU acceleration (NVIDIA only)
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

Copy `.env.example` to `.env` and add your bot token.
Copy `config/characters.example.json` to `config/characters.json` and add your player mappings.

## Configuration

### Bot Token (.env)
```
DISCORD_TOKEN=your_bot_token_here
PREFIX=!
```

### Character Map (config/characters.json)

Map Discord user IDs to character names. Enable Developer Mode in Discord (Settings > Advanced) to copy user IDs by right-clicking usernames.

```json
{
  "characterMap": {
    "123456789012345678": "DM",
    "987654321098765432": "Gilbert",
    "111222333444555666": "Thornwick"
  },
  "dmUsername": "123456789012345678"
}
```

### Discord Bot Permissions

When adding the bot to your server via OAuth2 URL Generator:
- **Scopes:** bot
- **Permissions:** Connect, Speak, View Channels, Send Messages, Read Message History

Under Bot settings, enable **Privileged Gateway Intents:**
- Server Members Intent
- Message Content Intent

## Usage

### Start the bot
```bash
npm start
```

### Discord Commands

| Command | Description |
|---------|-------------|
| `!join` | Bot joins your current voice channel |
| `!leave` | Bot leaves voice channel (stops recording) |
| `!session start "Title"` | Start recording with a session title |
| `!session stop` | Stop recording and save audio files |
| `!status` | Check current recording status |
| `!help` | Show available commands |

### Transcribe a Session

```bash
cd transcriber
venv\Scripts\activate       # Windows
source venv/bin/activate    # Mac/Linux

# Use a preset (auto-detects GPU)
python transcribe.py --preset quality

# Available presets
python transcribe.py --list-presets

# Specify a session folder and model directly
python transcribe.py ../recordings/2026-05-27_Session_Title --model large-v3

# Force CPU even if GPU is available
python transcribe.py --preset best --device cpu
```

### Condense a Transcript

```bash
# Normal: remove fillers, merge consecutive segments
python condense.py transcripts/session.json

# Aggressive: also removes table talk (mic checks, breaks, etc.)
python condense.py transcripts/session.json --mode aggressive

# Game-only: keeps only D&D content + all DM narration
python condense.py transcripts/session.json --mode game-only
```

## Transcription Presets

| Preset | Model | Best For |
|--------|-------|----------|
| `fast` | tiny | Quick drafts, testing |
| `balanced` | small | Most hardware, good accuracy |
| `quality` | medium | Recommended default |
| `best` | large-v3 | Best accuracy (GPU recommended) |

## Output Format

```json
{
  "sessionId": "uuid",
  "title": "Confrontation at Night's Rest",
  "date": "2026-05-27",
  "duration": "2:34:12",
  "transcript": [
    {
      "start": 0.0,
      "end": 3.45,
      "speaker": "DM",
      "text": "You enter the cavern and the air grows cold..."
    },
    {
      "start": 3.8,
      "end": 6.2,
      "speaker": "Gilbert",
      "text": "I draw my sword and look around cautiously."
    }
  ],
  "notes": "[0:00:00] DM: You enter the cavern...",
  "recap": "",
  "whatsNext": "",
  "loot": ""
}
```

## Project Structure

```
├── src/
│   ├── bot.js           # Discord bot entry point
│   ├── recorder.js      # Audio recording logic
│   ├── opus-decoder.js  # Opus to PCM stream decoder
│   └── utils.js         # Shared utilities
├── transcriber/
│   ├── transcribe.py    # Main transcription pipeline
│   ├── condense.py      # Transcript condensing
│   └── requirements.txt # Python dependencies
├── config/
│   ├── characters.example.json  # Template for character mapping
│   └── characters.json          # Your character mapping (gitignored)
├── recordings/          # Raw audio files (gitignored)
├── transcripts/         # Output JSON/TXT files (gitignored)
├── setup.bat            # Windows setup script
├── setup.sh             # Mac/Linux setup script
└── package.json
```

## Hardware Requirements

| Setup | RAM | Transcription Speed | Recommended Preset |
|-------|-----|--------------------|--------------------|
| CPU only, 8GB RAM | 8GB+ | ~15-20 min per hour of audio | balanced |
| CPU only, 16GB RAM | 16GB+ | ~10-15 min per hour of audio | quality |
| NVIDIA GPU, 6GB VRAM | 16GB+ | ~3-5 min per hour of audio | best |
| NVIDIA GPU, 8GB+ VRAM | 16GB+ | ~2-3 min per hour of audio | best |

## Troubleshooting

**Bot doesn't respond to commands:**
- Make sure Message Content Intent is enabled in the Discord Developer Portal
- Check that the bot has View Channels permission in the text channel

**Bot joins but "Failed to join voice channel":**
- Ensure the bot has Connect and Speak permissions on the voice channel
- Check that Privileged Gateway Intents are enabled

**No audio files after recording:**
- The voice connection may not have fully established
- Try `!leave` then `!join` again before starting a session

**Transcription hallucinating (wrong text):**
- Make sure you're transcribing a recording made with the current bot version
- Try a larger model (--preset quality or --preset best)

**CUDA/GPU errors:**
- Run with `--device cpu` to fall back to CPU
- Make sure NVIDIA drivers are up to date
