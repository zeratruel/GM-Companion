# GM Companion

A Discord bot by **Safe Port Gaming** that records voice channel audio during tabletop RPG sessions and transcribes them locally using Whisper. Free, private, runs entirely on your hardware.

## Features

- **One-click launch** — double-click `start.bat` and everything runs
- **Web control panel** — manage recordings, transcribe, and configure from your browser
- **Light/dark theme** — matches Safe Port Gaming's visual style
- Record per-user audio streams (perfect speaker attribution)
- Transcribe locally with faster-whisper (free, no API keys)
- Auto-detects GPU for fast transcription, falls back to CPU
- Map Discord display names to character names (no Developer Mode needed)
- Multiple transcription presets (fast → best quality)
- Condense transcripts by removing filler words and table talk
- JSON output compatible with campaign management tools

## Prerequisites

Before you start, make sure you have these installed:

- **Node.js** 18 or newer — [download here](https://nodejs.org/) (pick the LTS version)
- **Python** 3.10 or newer — [download here](https://www.python.org/downloads/) (check "Add Python to PATH" during install)

You'll also need a **Discord bot token** — the setup script walks you through creating one.

## Quick Start

### Step 1: Download

Download or clone this repository to your computer:
- Click the green **Code** button on GitHub → **Download ZIP**
- Or use git: `git clone https://github.com/zeratruel/GM-Companion.git`

### Step 2: Run Setup

Open the folder you downloaded and:

**Windows:** Double-click `setup.bat`

**Mac/Linux:**
```bash
chmod +x setup.sh
./setup.sh
```

The setup script will:
1. Verify Node.js and Python are installed
2. Install all dependencies automatically
3. Detect if you have an NVIDIA GPU (optional, speeds things up)
4. Ask you to paste a Discord bot token (instructions below)

### Step 3: Create a Discord Bot

This is a one-time process. You're creating a bot account that will join your voice channel.

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** — give it any name (e.g., "Session Recorder")
3. In the left sidebar, click **Bot**
4. Click **Reset Token**, then **Copy** the token — you'll paste this during setup
5. Scroll down to **Privileged Gateway Intents** and enable:
   - ✅ **Server Members Intent**
   - ✅ **Message Content Intent**
6. Click **Save Changes**

### Step 4: Add the Bot to Your Discord Server

Still in the Developer Portal:

1. In the left sidebar, click **OAuth2 → URL Generator**
2. Under **Scopes**, check: ✅ **bot**
3. Under **Bot Permissions**, check:
   - ✅ Connect
   - ✅ Speak
   - ✅ View Channels
   - ✅ Send Messages
   - ✅ Read Message History
4. Copy the **Generated URL** at the bottom
5. Open that URL in your browser
6. Select your Discord server from the dropdown and click **Authorize**

The bot should now appear in your server's member list.

### Step 5: Start the Bot

**Windows:** Double-click `start.bat`

This opens a terminal window (keep it open/minimized) and launches the control panel in your browser at **http://localhost:3000**.

**Mac/Linux:** Run `npm start`, then open http://localhost:3000

To stop the bot, close the terminal window.

## How to Record a Session

1. **Join a voice channel** in Discord (you and your players)
2. In any text channel, type: `!join`
   - The bot will join your voice channel
3. Type: `!session start "Session Title"`
   - Recording begins — everyone's audio is captured separately
4. Play your session normally
5. When done, type: `!session stop`
   - Audio files are saved locally
6. Open the **control panel** (http://localhost:3000) → **Recordings** tab → click **Transcribe**

> **Important:** You must be in a voice channel when you type `!join`. The bot joins whatever channel you're currently in.

## Control Panel

The control panel runs at **http://localhost:3000** whenever the bot is running.

| Tab | What it does |
|-----|-------------|
| **Recordings** | View all recorded sessions, click to transcribe or delete |
| **Transcripts** | View, read, condense, or delete full transcripts |
| **Condensed** | View and manage condensed transcript versions |
| **Characters** | Map Discord names to character names |
| **Settings** | Configure bot token and command prefix |

## Character Map

Map your players' Discord display names to their in-game character names. This makes transcripts read like a script instead of showing Discord usernames.

Open the **Characters** tab in the control panel, or edit `config/characters.json`:

```json
{
  "characterMap": {
    "Heather": "Gilbert",
    "Mike": "John McClean",
    "Sarah": "Thornwick"
  },
  "dmUsername": "Brandon"
}
```

Just use the name as it appears in Discord — no special IDs or Developer Mode needed.

## Discord Commands

Type these in any text channel where the bot can see messages:

| Command | Description |
|---------|-------------|
| `!join` | Bot joins your current voice channel (you must be in one) |
| `!leave` | Bot leaves voice channel (stops recording if active) |
| `!session start "Title"` | Start recording with a session title |
| `!session stop` | Stop recording and save audio files |
| `!status` | Check current recording status |
| `!help` | Show available commands |

## Transcription Presets

When transcribing from the control panel, you can choose a quality level:

| Preset | Speed | Accuracy | Best For |
|--------|-------|----------|----------|
| **Fast** | Very fast | Fair | Quick test, checking if audio recorded properly |
| **Balanced** | Moderate | Good | Regular use on most computers |
| **Quality** | Slower | Great | Recommended default for final transcripts |
| **Best** | Slow on CPU, fast on GPU | Excellent | Best results if you have an NVIDIA GPU |

### CLI Alternative

If you prefer the command line:

```bash
cd transcriber
venv\Scripts\activate       # Windows
source venv/bin/activate    # Mac/Linux

# Use a preset
python transcribe.py --preset quality

# Specify a recording folder directly
python transcribe.py ../recordings/2026-05-27_Session_Title --model large-v3

# Force CPU even if GPU is available
python transcribe.py --preset best --device cpu

# List all presets
python transcribe.py --list-presets
```

## Condensing Modes

After transcribing, you can condense the transcript to remove noise:

| Mode | What it removes |
|------|----------------|
| **Normal** | Filler words (um, uh, like), merges short segments |
| **Aggressive** | Also removes table talk (mic checks, "brb", "whose turn") |
| **Game Only** | Keeps only in-game content + all DM narration |

### CLI Alternative

```bash
cd transcriber
venv\Scripts\activate

# Normal condensing
python condense.py ../transcripts/session.json

# Aggressive mode
python condense.py ../transcripts/session.json --mode aggressive

# Game-only mode with custom output path
python condense.py ../transcripts/session.json --mode game-only -o clean_session.json
```

## Output Format

Transcripts are saved as JSON files:

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
    }
  ],
  "notes": "[0:00:00] DM: You enter the cavern...",
  "recap": "",
  "whatsNext": "",
  "loot": ""
}
```

## Hardware Requirements

| Your Setup | Transcription Speed | Recommended Preset |
|------------|--------------------|--------------------|
| Any modern computer, 8GB RAM | ~15-20 min per hour of audio | Balanced |
| 16GB RAM | ~10-15 min per hour of audio | Quality |
| NVIDIA GPU (6GB+ VRAM) | ~2-5 min per hour of audio | Best |

## Troubleshooting

**Bot doesn't respond to commands:**
- Make sure **Message Content Intent** is enabled in the Developer Portal (Bot settings)
- Make sure the bot has permission to read the text channel you're typing in

**Bot joins voice but "Failed to join":**
- Make sure the bot has **Connect** and **Speak** permissions on that voice channel
- Try: Server Settings → Roles → find the bot's role → enable Connect and Speak

**No audio files after recording:**
- Try `!leave` then `!join` again before starting a session
- Make sure at least one person talks after `!session start`

**Transcription produces wrong text:**
- This can happen with very short recordings or silence
- Try a longer recording with clear speech
- Use the **Quality** or **Best** preset for better accuracy

**GPU not detected:**
- Make sure your NVIDIA drivers are up to date
- The **Balanced** and **Quality** presets work great on CPU — GPU is optional

**Control panel won't open:**
- Make sure the bot is running (terminal window open or `start-hidden.vbs` active)
- Try opening http://localhost:3000 manually in your browser

## Project Structure

```
├── src/                 # Bot source code
├── ui/                  # Control panel (web interface)
├── transcriber/         # Python transcription scripts
├── config/              # Character map configuration
├── recordings/          # Recorded audio (created automatically)
├── transcripts/         # Transcription output (created automatically)
├── start.bat            # Windows launcher
├── start-hidden.vbs     # Windows launcher (no terminal window)
├── setup.bat            # Windows first-time setup
└── setup.sh             # Mac/Linux first-time setup
```

## License

MIT License — see [LICENSE](LICENSE) for details.

Made with care by Safe Port Gaming.
