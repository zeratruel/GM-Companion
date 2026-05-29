"""
Transcript Condenser
Takes a full transcript JSON and produces a condensed version by:
1. Removing filler words and repeated phrases
2. Merging consecutive segments from the same speaker
3. Removing very short/empty segments
4. Optionally removing table talk (non-game chatter)

Usage:
    python transcriber/condense.py <transcript.json>
    python transcriber/condense.py <transcript.json> --aggressive
    python transcriber/condense.py <transcript.json> --mode game-only
"""

import json
import re
import sys
import argparse
from pathlib import Path
from datetime import timedelta


# Common filler words/phrases to strip
FILLER_PATTERNS = [
    r'\b(um+|uh+|er+|ah+|hmm+|hm+|mhm+)\b',
    r'\b(like,?\s*)+(?=\w)',  # repeated "like"
    r'\b(you know,?\s*)+',
    r'\b(I mean,?\s*)+(?=\w)',
    r'^\s*(okay|ok|right)\s*[,.]?\s*(?=\w)',  # leading "okay", "right"
    r'\b(basically)\s*,?\s*',
    r'\b(actually)\s*,?\s*(?=\w)',
]

# Phrases that indicate non-game table talk
TABLE_TALK_PATTERNS = [
    r"can you hear me",
    r"is (my|the) mic",
    r"hold on.*(sec|second|minute)",
    r"brb|be right back",
    r"sorry.*(dog|cat|phone|door|doorbell|pizza)",
    r"what did you (roll|get)",
    r"whose turn (is it)?",
    r"let me (check|look|pull up)",
    r"one sec(ond)?",
    r"i('m| am) (back|here)",
    r"can (everyone|you all) hear",
    r"my (internet|wifi|connection)",
    r"you('re| are) (muted|on mute)",
    r"(bathroom|bio) break",
    r"gonna grab (a|some)",
    r"what time is it",
    r"how long have we been",
    r"should we (take a break|stop|wrap up)",
    r"let me (get|grab) (a drink|water|food|snack)",
]

# Patterns that indicate in-game content (used in game-only mode)
GAME_CONTENT_PATTERNS = [
    r"(roll|rolls|rolled)\s*(a|for|initiative|perception|insight|stealth|athletics|arcana|investigation|persuasion|deception|intimidation|history|nature|religion|medicine|survival|acrobatics|sleight|animal)",
    r"(attack|cast|spell|damage|hit points|hp|ac|armor class|saving throw|save|ability check)",
    r"(you see|you notice|you hear|you feel|you find|you enter|you approach)",
    r"(tavern|dungeon|cave|forest|castle|tower|village|town|city|temple|shrine)",
    r"(sword|shield|bow|arrow|staff|wand|potion|scroll|armor|weapon|gold|gp|sp|cp)",
    r"(dragon|goblin|orc|skeleton|zombie|demon|devil|undead|monster|creature|beast)",
    r"(initiative|combat|round|turn|action|bonus action|reaction|movement)",
    r"(character|npc|quest|mission|adventure|campaign)",
    r"(i want to|i('d| would) like to|can i|i attempt|i try)",
]


def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format."""
    td = timedelta(seconds=int(seconds))
    return str(td)


def remove_fillers(text: str) -> str:
    """Remove filler words from text."""
    result = text
    for pattern in FILLER_PATTERNS:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    # Clean up extra spaces and leading/trailing punctuation
    result = re.sub(r'\s{2,}', ' ', result).strip()
    result = re.sub(r'^[,.\s]+', '', result).strip()
    return result


def is_table_talk(text: str) -> bool:
    """Check if a segment is likely table talk rather than game content."""
    text_lower = text.lower()
    for pattern in TABLE_TALK_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False


def is_game_content(text: str) -> bool:
    """Check if a segment likely contains in-game content."""
    text_lower = text.lower()
    for pattern in GAME_CONTENT_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False


def merge_consecutive_segments(segments: list[dict], max_gap_seconds: float = 2.0) -> list[dict]:
    """Merge consecutive segments from the same speaker if they're close together."""
    if not segments:
        return []

    merged = [segments[0].copy()]

    for seg in segments[1:]:
        prev = merged[-1]
        # Same speaker and close in time
        if seg["speaker"] == prev["speaker"] and (seg["start"] - prev["end"]) <= max_gap_seconds:
            prev["text"] = prev["text"] + " " + seg["text"]
            prev["end"] = seg["end"]
        else:
            merged.append(seg.copy())

    return merged


def condense_transcript(input_path: Path, mode: str = "normal") -> dict:
    """
    Condense a full transcript.

    Modes:
        normal: merge segments, remove fillers, drop very short segments
        aggressive: also remove detected table talk
        game-only: keep only segments that appear to be in-game content
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    segments = data.get("transcript", [])
    original_count = len(segments)

    print(f"Original segments: {original_count}")
    print(f"Mode: {mode}")
    print()

    # Step 1: Remove filler words from all segments
    for seg in segments:
        seg["text"] = remove_fillers(seg["text"])

    # Step 2: Remove empty/very short segments (< 4 chars after filler removal)
    segments = [s for s in segments if len(s["text"].strip()) > 3]
    removed_empty = original_count - len(segments)
    if removed_empty:
        print(f"  Removed {removed_empty} empty/very short segments")

    # Step 3: Mode-specific filtering
    if mode == "aggressive":
        before = len(segments)
        segments = [s for s in segments if not is_table_talk(s["text"])]
        removed_talk = before - len(segments)
        if removed_talk:
            print(f"  Removed {removed_talk} table talk segments")

    elif mode == "game-only":
        before = len(segments)
        # Keep segments that are game content OR from DM (DM narration is always game content)
        segments = [s for s in segments if is_game_content(s["text"]) or s.get("speaker") == "DM"]
        removed_nongame = before - len(segments)
        if removed_nongame:
            print(f"  Removed {removed_nongame} non-game segments")

    # Step 4: Merge consecutive same-speaker segments
    before_merge = len(segments)
    segments = merge_consecutive_segments(segments)
    merged_count = before_merge - len(segments)
    if merged_count:
        print(f"  Merged {merged_count} consecutive segments")

    # Step 5: Rebuild notes text
    notes_lines = []
    for seg in segments:
        timestamp = format_timestamp(seg["start"])
        notes_lines.append(f"[{timestamp}] {seg['speaker']}: {seg['text']}")

    condensed_notes = "\n".join(notes_lines)

    # Build output
    output = data.copy()
    output["transcript"] = segments
    output["notes"] = condensed_notes

    final_count = len(segments)
    reduction = ((original_count - final_count) / max(original_count, 1)) * 100

    print(f"\n  Result: {original_count} -> {final_count} segments ({reduction:.1f}% reduction)")

    return output


def main():
    parser = argparse.ArgumentParser(
        description="Condense a D&D session transcript",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  normal      Remove fillers, merge consecutive segments (default)
  aggressive  Also remove table talk (mic checks, break requests, etc.)
  game-only   Keep only segments with detectable in-game content + all DM lines

Examples:
  python condense.py transcripts/session.json
  python condense.py transcripts/session.json --mode aggressive
  python condense.py transcripts/session.json --mode game-only -o session_clean.json
        """,
    )
    parser.add_argument("transcript", help="Path to the full transcript JSON file")
    parser.add_argument("--mode", default="normal",
                        choices=["normal", "aggressive", "game-only"],
                        help="Condensing mode (default: normal)")
    parser.add_argument("--output", "-o", help="Output file path (default: adds _condensed suffix)")
    # Keep --aggressive as a shortcut for backwards compat
    parser.add_argument("--aggressive", action="store_true",
                        help="Shortcut for --mode aggressive")
    args = parser.parse_args()

    input_path = Path(args.transcript)
    if not input_path.exists():
        print(f"File not found: {input_path}")
        sys.exit(1)

    # --aggressive flag overrides --mode
    mode = "aggressive" if args.aggressive else args.mode

    output = condense_transcript(input_path, mode=mode)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        suffix = f"_{mode}" if mode != "normal" else "_condensed"
        output_path = input_path.with_stem(input_path.stem + suffix)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Condensed transcript saved to: {output_path}")


if __name__ == "__main__":
    main()
