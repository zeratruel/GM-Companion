"""
D&D Session Transcriber
Processes recorded PCM audio files and produces a structured JSON transcript.

Usage:
    python transcriber/transcribe.py [session_folder]

If no folder is specified, processes the most recent recording in ./recordings/
"""

import os
import sys
import json
import wave
import struct
import argparse
from pathlib import Path
from datetime import timedelta

# Add NVIDIA CUDA DLLs to PATH for GPU acceleration
_nvidia_path = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
if _nvidia_path.exists():
    _dll_dirs = [str(d) for d in _nvidia_path.glob("*/bin") if d.is_dir()]
    if _dll_dirs:
        os.environ["PATH"] = os.pathsep.join(_dll_dirs) + os.pathsep + os.environ.get("PATH", "")
        for d in _dll_dirs:
            os.add_dll_directory(d)

from faster_whisper import WhisperModel


# Model presets for different user needs
MODEL_PRESETS = {
    "fast": {
        "model": "tiny",
        "description": "Fastest transcription, lower accuracy. Good for quick drafts.",
    },
    "balanced": {
        "model": "small",
        "description": "Good balance of speed and accuracy. Works well on most hardware.",
    },
    "quality": {
        "model": "medium",
        "description": "High accuracy, moderate speed. Recommended for most users.",
    },
    "best": {
        "model": "large-v3",
        "description": "Best possible accuracy. Requires GPU or patience on CPU.",
    },
}


def detect_device() -> tuple[str, str]:
    """
    Auto-detect the best available device for transcription.
    Returns (device, compute_type) tuple.
    """
    # Try CUDA (NVIDIA GPU)
    try:
        import ctranslate2
        if "cuda" in ctranslate2.get_supported_compute_types("cuda"):
            print("NVIDIA GPU detected — using CUDA acceleration")
            return "cuda", "float16"
    except Exception:
        pass

    # Fallback to CPU
    print("No GPU detected — using CPU (this will be slower)")
    return "cpu", "int8"


# Audio settings matching Discord's output
SAMPLE_RATE = 48000
CHANNELS = 1  # Discord sends mono per-user streams
SAMPLE_WIDTH = 2  # 16-bit


def find_latest_session(recordings_dir: str) -> Path:
    """Find the most recently modified session folder."""
    recordings = Path(recordings_dir)
    if not recordings.exists():
        print("No recordings directory found.")
        sys.exit(1)

    sessions = sorted(recordings.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    if not sessions:
        print("No session recordings found.")
        sys.exit(1)

    return sessions[0]


def pcm_to_wav(pcm_path: Path, wav_path: Path):
    """Convert raw PCM file to WAV format for Whisper."""
    pcm_data = pcm_path.read_bytes()

    with wave.open(str(wav_path), 'wb') as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(SAMPLE_WIDTH)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(pcm_data)

    return wav_path


def transcribe_audio(model: WhisperModel, wav_path: Path) -> list[dict]:
    """Transcribe a WAV file and return timestamped segments."""
    segments, info = model.transcribe(
        str(wav_path),
        beam_size=5,
        language="en",
        vad_filter=True,
        vad_parameters=dict(
            min_silence_duration_ms=500,
            speech_pad_ms=200,
        ),
    )

    results = []
    for segment in segments:
        results.append({
            "start": round(segment.start, 2),
            "end": round(segment.end, 2),
            "text": segment.text.strip(),
        })

    return results


def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format."""
    td = timedelta(seconds=int(seconds))
    return str(td)


def build_transcript(session_dir: Path, model_size: str = "medium", force_device: str = None) -> dict:
    """
    Main transcription pipeline.
    1. Load session metadata
    2. Convert PCM files to WAV
    3. Transcribe each speaker
    4. Merge and sort by timestamp
    5. Output structured JSON
    """
    meta_path = session_dir / "session_meta.json"
    if not meta_path.exists():
        print(f"No session_meta.json found in {session_dir}")
        sys.exit(1)

    with open(meta_path, 'r') as f:
        metadata = json.load(f)

    print(f"Session: {metadata['title']}")
    print(f"Date: {metadata['date']}")
    print(f"Loading Whisper model ({model_size})... This may take a moment on first run.")

    # Detect hardware and select optimal settings
    if force_device and force_device != "auto":
        device = force_device
        compute_type = "float16" if device == "cuda" else "int8"
        print(f"Device: {device} ({compute_type}) [forced]")
    else:
        device, compute_type = detect_device()
        print(f"Device: {device} ({compute_type})")

    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    print("Model loaded. Beginning transcription...\n")

    character_map = metadata.get("characterMap", {})
    speakers = metadata.get("speakers", {})

    # Also load the current character map from config as fallback
    config_map_path = session_dir.parent.parent / "config" / "characters.json"
    if config_map_path.exists():
        with open(config_map_path, 'r') as f:
            config_data = json.load(f)
            config_map = config_data.get("characterMap", {})
            # Merge: config map takes precedence over stale metadata
            for user_id, name in config_map.items():
                if user_id not in character_map or character_map[user_id] in (None, ""):
                    character_map[user_id] = name

    all_segments = []

    for user_id, speaker_info in speakers.items():
        pcm_file = session_dir / speaker_info["file"]
        if not pcm_file.exists():
            print(f"  Warning: Audio file not found for user {user_id}, skipping.")
            continue

        # Skip empty files
        if pcm_file.stat().st_size == 0:
            print(f"  Skipping empty file for user {user_id}")
            continue

        # Determine speaker name
        speaker_name = speaker_info.get("characterName") or character_map.get(user_id, f"Unknown ({user_id})")
        print(f"  Transcribing: {speaker_name}...")

        # Get the time offset (when this speaker started relative to session start)
        offset_seconds = speaker_info.get("offsetMs", 0) / 1000.0

        # Convert PCM to WAV
        wav_path = session_dir / f"{user_id}.wav"
        pcm_to_wav(pcm_file, wav_path)

        # Transcribe
        segments = transcribe_audio(model, wav_path)

        # Tag segments with speaker and apply time offset
        for seg in segments:
            seg["start"] = round(seg["start"] + offset_seconds, 2)
            seg["end"] = round(seg["end"] + offset_seconds, 2)
            seg["speaker"] = speaker_name
            all_segments.append(seg)

        # Clean up WAV file
        wav_path.unlink()

        print(f"    -> {len(segments)} segments transcribed")

    # Sort all segments by start time
    all_segments.sort(key=lambda s: s["start"])

    # Build full transcript text
    full_text_lines = []
    for seg in all_segments:
        timestamp = format_timestamp(seg["start"])
        full_text_lines.append(f"[{timestamp}] {seg['speaker']}: {seg['text']}")

    full_transcript_text = "\n".join(full_text_lines)

    # Build output matching the campaign session schema
    output = {
        "sessionId": metadata["sessionId"],
        "title": metadata["title"],
        "date": metadata["date"],
        "duration": format_timestamp(metadata.get("durationMs", 0) / 1000),
        "transcript": all_segments,
        "notes": full_transcript_text,
        "recap": "",
        "whatsNext": "",
        "loot": "",
    }

    return output


def save_output(output: dict, session_dir: Path):
    """Save the transcript to the transcripts directory."""
    transcripts_dir = Path("transcripts")
    transcripts_dir.mkdir(exist_ok=True)

    # Full transcript
    filename = f"{output['date']}_{output['title'].replace(' ', '_')[:50]}.json"
    output_path = transcripts_dir / filename

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Full transcript saved to: {output_path}")

    # Also save a plain text version
    txt_path = output_path.with_suffix('.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f"Session: {output['title']}\n")
        f.write(f"Date: {output['date']}\n")
        f.write(f"Duration: {output['duration']}\n")
        f.write(f"{'=' * 60}\n\n")
        f.write(output['notes'])

    print(f"✓ Plain text transcript saved to: {txt_path}")

    return output_path


def main():
    parser = argparse.ArgumentParser(description="Transcribe a D&D session recording")
    parser.add_argument("session_folder", nargs="?", help="Path to session recording folder")
    parser.add_argument("--model", default=None,
                        choices=["tiny", "base", "small", "medium", "large-v3"],
                        help="Whisper model size (overrides --preset)")
    parser.add_argument("--preset", default="quality",
                        choices=["fast", "balanced", "quality", "best"],
                        help="Transcription preset: fast, balanced, quality (default), or best")
    parser.add_argument("--device", default=None, choices=["auto", "cpu", "cuda"],
                        help="Force a specific device (default: auto-detect)")
    parser.add_argument("--list-presets", action="store_true",
                        help="Show available presets and exit")
    args = parser.parse_args()

    if args.list_presets:
        print("Available presets:\n")
        for name, info in MODEL_PRESETS.items():
            print(f"  {name:10s} (model: {info['model']:10s}) — {info['description']}")
        print(f"\nYou can also specify a model directly with --model [tiny|base|small|medium|large-v3]")
        sys.exit(0)

    # Resolve model: explicit --model overrides --preset
    if args.model:
        model_size = args.model
    else:
        model_size = MODEL_PRESETS[args.preset]["model"]

    if args.session_folder:
        session_dir = Path(args.session_folder)
    else:
        session_dir = find_latest_session("recordings")

    print(f"Processing session: {session_dir.name}")
    print(f"Model: {model_size} (preset: {args.preset})")
    print("-" * 60)

    output = build_transcript(session_dir, model_size=model_size, force_device=args.device)
    save_output(output, session_dir)

    print(f"\nDone! {len(output['transcript'])} total segments transcribed.")


if __name__ == "__main__":
    main()
