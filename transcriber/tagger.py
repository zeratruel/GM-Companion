"""
Transcript Tagger
Analyzes a transcript and tags segments with contextual markers:
- [COMBAT] — initiative, attacks, damage, saving throws
- [NPC] — DM introduces or references named characters
- [LOCATION] — scene changes, new areas described
- [LOOT] — items, gold, rewards mentioned
- [ROLEPLAY] — in-character dialogue and interactions
- [PLANNING] — party discussion about what to do next

Uses a Session 0 config to track known entities and detect new ones.

Usage:
    python tagger.py <transcript.json>
    python tagger.py <transcript.json> --session0 ../config/session0.json
"""

import json
import re
import sys
import argparse
from pathlib import Path


# --- Detection Patterns ---

COMBAT_PATTERNS = [
    r"\b(roll|rolls|rolled)\s+(for\s+)?(initiative|attack|damage|saving throw|save|to hit)",
    r"\b(hits?|misses?|crits?|critical)\b.*\b(for|dealing)\s+\d+",
    r"\b\d+\s*(points?\s+of\s+)?(damage|healing)\b",
    r"\b(attack|attacks|attacked)\s+(the|a|an)\b",
    r"\b(armor class|ac)\s*\d+",
    r"\b(hit points?|hp)\b",
    r"\b(saving throw|save)\s+(against|vs|dc)",
    r"\b(bonus action|reaction|action surge|second wind)\b",
    r"\b(opportunity attack|sneak attack|smite|rage)\b",
    r"\b(falls?\s+(unconscious|to\s+0)|death\s+save)",
]

LOCATION_PATTERNS = [
    r"\byou\s+(enter|arrive|approach|step\s+into|find\s+yourself|come\s+upon|reach)\b",
    r"\b(before\s+you|ahead\s+of\s+you|in\s+the\s+distance)\b.*\b(stands?|lies?|looms?|stretches?)\b",
    r"\b(tavern|inn|dungeon|cave|cavern|forest|castle|tower|village|town|city|temple|shrine|ruins|camp|fortress|keep|manor|crypt|tomb)\b",
    r"\b(the\s+room|this\s+place|the\s+area|the\s+chamber)\s+(is|appears|looks|smells|feels)\b",
    r"\b(north|south|east|west|left|right|ahead|behind)\s+(you\s+see|there\s+is|lies)\b",
]

LOOT_PATTERNS = [
    r"\b(you\s+(find|receive|discover|pick\s+up|loot|gain|are\s+given|obtain))\b",
    r"\b\d+\s*(gold|gp|silver|sp|copper|cp|platinum|pp)\b",
    r"\b(potion|scroll|ring|amulet|sword|shield|staff|wand|armor|weapon|cloak|boots|helm|gauntlet)\s+of\b",
    r"\b(magic(al)?\s+(item|weapon|armor))\b",
    r"\b(treasure|chest|reward|payment|bounty)\b",
]

ROLEPLAY_PATTERNS = [
    r"\bi\s+(say|tell|ask|whisper|shout|yell|respond|reply)\b",
    r"\b(in\s+character|speaking\s+as)\b",
    r"^\".*\"$",  # Quoted speech
    r"\bi\s+(bow|kneel|shake|wave|nod|smile|frown|laugh|cry)\b",
]

PLANNING_PATTERNS = [
    r"\b(what\s+should\s+we|what\s+do\s+we|should\s+we|let's|we\s+could|we\s+should|i\s+think\s+we)\b",
    r"\b(plan|strategy|idea|option|approach)\b",
    r"\b(long\s+rest|short\s+rest|camp|sleep|prepare)\b",
    r"\b(before\s+we\s+go|first\s+we|next\s+we)\b",
]


def detect_tags(text: str, speaker: str, known_entities: dict) -> list[str]:
    """Detect all applicable tags for a transcript segment."""
    tags = []
    text_lower = text.lower()

    # Combat detection
    for pattern in COMBAT_PATTERNS:
        if re.search(pattern, text_lower):
            tags.append("COMBAT")
            break

    # Location detection (primarily from DM)
    if speaker == "DM" or speaker.lower() == "dm":
        for pattern in LOCATION_PATTERNS:
            if re.search(pattern, text_lower):
                tags.append("LOCATION")
                break

    # Loot detection
    for pattern in LOOT_PATTERNS:
        if re.search(pattern, text_lower):
            tags.append("LOOT")
            break

    # Roleplay detection (from players)
    if speaker != "DM" and speaker.lower() != "dm":
        for pattern in ROLEPLAY_PATTERNS:
            if re.search(pattern, text_lower):
                tags.append("ROLEPLAY")
                break

    # Planning detection
    for pattern in PLANNING_PATTERNS:
        if re.search(pattern, text_lower):
            tags.append("PLANNING")
            break

    return tags


def detect_npcs(text: str, speaker: str, known_entities: dict) -> list[str]:
    """Detect NPC names mentioned in DM narration."""
    if speaker != "DM" and speaker.lower() != "dm":
        return []

    found_npcs = []
    player_characters = set(name.lower() for name in known_entities.get("playerCharacters", []))
    known_npcs = set(name.lower() for name in known_entities.get("knownNPCs", []))

    # Look for capitalized names (2+ chars) that aren't player characters
    # Pattern: Two capitalized words together (likely a proper name)
    name_pattern = r'\b([A-Z][a-z]{2,}\s+[A-Z][a-z]{2,})\b'
    matches = re.findall(name_pattern, text)

    # Also look for single capitalized words after name-introducing phrases
    intro_pattern = r'\b(?:named|called|known\s+as|introduces?\s+(?:himself|herself|themselves)\s+as)\s+([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)'
    intro_matches = re.findall(intro_pattern, text)
    matches.extend(intro_matches)

    for name in matches:
        name_lower = name.lower()
        # Skip if it's a player character
        if name_lower in player_characters:
            continue
        # Skip common phrases that look like names
        skip_phrases = {"the crimson", "the golden", "the hidden", "the dark",
                        "the ancient", "the great", "the old", "the black",
                        "the white", "the red", "roll for", "roll initiative"}
        if name_lower in skip_phrases:
            continue

        found_npcs.append(name)

    return found_npcs


def detect_locations(text: str, speaker: str, known_entities: dict) -> list[str]:
    """Detect location names mentioned in DM narration."""
    if speaker != "DM" and speaker.lower() != "dm":
        return []

    known_locations = set(name.lower() for name in known_entities.get("knownLocations", []))
    found_locations = []

    # Check for known locations
    for loc in known_entities.get("knownLocations", []):
        if loc.lower() in text.lower():
            found_locations.append(loc)

    return found_locations


def tag_transcript(input_path: Path, session0_path: Path = None) -> dict:
    """
    Tag a transcript with contextual markers.
    Returns the transcript with tags added to each segment.
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Load session 0 / known entities
    known_entities = {
        "playerCharacters": [],
        "knownNPCs": [],
        "knownLocations": [],
        "keywords": [],
    }

    if session0_path and session0_path.exists():
        with open(session0_path, 'r', encoding='utf-8') as f:
            known_entities.update(json.load(f))

    # Also try loading from config
    config_path = Path("../config/session0.json")
    if not session0_path and config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            known_entities.update(json.load(f))

    segments = data.get("transcript", [])
    print(f"Tagging {len(segments)} segments...")
    print(f"Known PCs: {known_entities['playerCharacters']}")
    print(f"Known NPCs: {known_entities['knownNPCs']}")
    print(f"Known Locations: {known_entities['knownLocations']}")
    print()

    # Track discovered entities
    new_npcs = set()
    mentioned_locations = set()
    tag_counts = {"COMBAT": 0, "LOCATION": 0, "LOOT": 0, "ROLEPLAY": 0, "PLANNING": 0, "NPC": 0}

    for seg in segments:
        text = seg.get("text", "")
        speaker = seg.get("speaker", "")

        # Detect tags
        tags = detect_tags(text, speaker, known_entities)

        # Detect NPCs
        npcs = detect_npcs(text, speaker, known_entities)
        if npcs:
            tags.append("NPC")
            for npc in npcs:
                new_npcs.add(npc)

        # Detect locations
        locations = detect_locations(text, speaker, known_entities)
        if locations:
            if "LOCATION" not in tags:
                tags.append("LOCATION")
            for loc in locations:
                mentioned_locations.add(loc)

        # Add tags to segment
        seg["tags"] = tags

        for tag in tags:
            if tag in tag_counts:
                tag_counts[tag] += 1

    # Build summary
    summary = {
        "tagCounts": tag_counts,
        "npcsDetected": sorted(list(new_npcs)),
        "locationsDetected": sorted(list(mentioned_locations)),
        "totalSegments": len(segments),
        "taggedSegments": sum(1 for s in segments if s.get("tags")),
    }

    # Add to output
    output = data.copy()
    output["transcript"] = segments
    output["tags_summary"] = summary

    # Rebuild notes with tags
    notes_lines = []
    for seg in segments:
        from condense import format_timestamp
        timestamp = format_timestamp(seg["start"])
        tag_str = " ".join(f"[{t}]" for t in seg.get("tags", []))
        prefix = f"{tag_str} " if tag_str else ""
        notes_lines.append(f"[{timestamp}] {prefix}{seg['speaker']}: {seg['text']}")

    output["notes"] = "\n".join(notes_lines)

    print(f"Results:")
    print(f"  Combat segments: {tag_counts['COMBAT']}")
    print(f"  Location segments: {tag_counts['LOCATION']}")
    print(f"  Loot segments: {tag_counts['LOOT']}")
    print(f"  Roleplay segments: {tag_counts['ROLEPLAY']}")
    print(f"  Planning segments: {tag_counts['PLANNING']}")
    print(f"  NPC mentions: {tag_counts['NPC']}")
    print(f"  NPCs detected: {', '.join(sorted(new_npcs)) or 'none'}")
    print(f"  Locations detected: {', '.join(sorted(mentioned_locations)) or 'none'}")

    return output


def main():
    parser = argparse.ArgumentParser(description="Tag a D&D session transcript with contextual markers")
    parser.add_argument("transcript", help="Path to the transcript JSON file")
    parser.add_argument("--session0", help="Path to session0.json with known entities")
    parser.add_argument("--output", "-o", help="Output file path (default: adds _tagged suffix)")
    args = parser.parse_args()

    input_path = Path(args.transcript)
    if not input_path.exists():
        print(f"File not found: {input_path}")
        sys.exit(1)

    session0_path = Path(args.session0) if args.session0 else None

    output = tag_transcript(input_path, session0_path)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_stem(input_path.stem + "_tagged")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Tagged transcript saved to: {output_path}")


if __name__ == "__main__":
    main()
