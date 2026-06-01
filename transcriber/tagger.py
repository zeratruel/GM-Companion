"""
Transcript Tagger
Analyzes a transcript and tags segments with contextual markers:
- [COMBAT] — initiative, attacks, damage, saving throws
- [NPC] — references a known NPC
- [NEW_NPC] — DM introduces a previously unknown named character
- [LOCATION] — scene changes, new areas described
- [LOOT] — items, gold, rewards mentioned
- [ROLEPLAY] — in-character dialogue and interactions
- [PLANNING] — party discussion about what to do next

Uses session0.json for base config and a campaign knowledge file that
grows with each tagged session (iterative learning).

Usage:
    python tagger.py <transcript.json>
    python tagger.py <transcript.json> --campaign Yarith
"""

import json
import re
import sys
import argparse
from pathlib import Path
from datetime import timedelta, date


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
    r"^\".*\"$",
    r"\bi\s+(bow|kneel|shake|wave|nod|smile|frown|laugh|cry)\b",
]

PLANNING_PATTERNS = [
    r"\b(what\s+should\s+we|what\s+do\s+we|should\s+we|let's|we\s+could|we\s+should|i\s+think\s+we)\b",
    r"\b(plan|strategy|idea|option|approach)\b",
    r"\b(long\s+rest|short\s+rest|camp|sleep|prepare)\b",
    r"\b(before\s+we\s+go|first\s+we|next\s+we)\b",
]


def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format."""
    td = timedelta(seconds=int(seconds))
    return str(td)


def load_session0(config_dir: Path) -> dict:
    """Load the base session0 config."""
    session0_path = config_dir / "session0.json"
    if session0_path.exists():
        with open(session0_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"campaign": "Default", "playerCharacters": []}


def load_campaign_knowledge(config_dir: Path, campaign_name: str) -> dict:
    """Load the accumulated campaign knowledge file."""
    campaign_path = config_dir / "campaigns" / f"{campaign_name.lower().replace(' ', '_')}.json"
    if campaign_path.exists():
        with open(campaign_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "campaign": campaign_name,
        "lastUpdated": "",
        "sessionsProcessed": [],
        "playerCharacters": [],
        "npcs": {},
        "locations": {},
        "keywords": [],
    }


def save_campaign_knowledge(config_dir: Path, campaign_name: str, knowledge: dict):
    """Save the updated campaign knowledge file."""
    campaigns_dir = config_dir / "campaigns"
    campaigns_dir.mkdir(parents=True, exist_ok=True)
    campaign_path = campaigns_dir / f"{campaign_name.lower().replace(' ', '_')}.json"
    with open(campaign_path, 'w', encoding='utf-8') as f:
        json.dump(knowledge, f, indent=2, ensure_ascii=False)
    print(f"  Campaign knowledge updated: {campaign_path}")


def detect_tags(text: str, speaker: str, known_npcs: set, known_locations: set) -> list[str]:
    """Detect all applicable tags for a transcript segment."""
    tags = []
    text_lower = text.lower()

    # Combat detection
    for pattern in COMBAT_PATTERNS:
        if re.search(pattern, text_lower):
            tags.append("COMBAT")
            break

    # Location detection (primarily from DM)
    if speaker.lower() == "dm":
        for pattern in LOCATION_PATTERNS:
            if re.search(pattern, text_lower):
                tags.append("LOCATION")
                break

    # Check for known location mentions (any speaker)
    for loc in known_locations:
        if loc.lower() in text_lower:
            if "LOCATION" not in tags:
                tags.append("LOCATION")
            break

    # Loot detection
    for pattern in LOOT_PATTERNS:
        if re.search(pattern, text_lower):
            tags.append("LOOT")
            break

    # Roleplay detection (from players)
    if speaker.lower() != "dm":
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


def detect_npcs(text: str, speaker: str, player_characters: set, known_npcs: set) -> tuple[list[str], list[str]]:
    """
    Detect NPC names mentioned in DM narration.
    Returns (known_npc_mentions, new_npc_discoveries).
    Only detects new NPCs via explicit naming patterns (e.g., "named X", "called X").
    """
    if speaker.lower() != "dm":
        return [], []

    known_mentions = []
    new_discoveries = []

    # Check for known NPC mentions
    for npc in known_npcs:
        if npc.lower() in text.lower():
            known_mentions.append(npc)

    # Look for names after introducing phrases (high confidence only)
    intro_pattern = r'\b(?:named|called|known\s+as|introduces?\s+(?:himself|herself|themselves)\s+as)\s+([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)'
    intro_matches = re.findall(intro_pattern, text)

    # Also: "a/an/the [descriptor] named X"
    descriptor_pattern = r'\b(?:a|an|the)\s+\w+\s+(?:named|called)\s+([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)'
    descriptor_matches = re.findall(descriptor_pattern, text)
    intro_matches.extend(descriptor_matches)

    # Words that indicate a location, not a person
    location_words = {"inn", "tavern", "keep", "tower", "castle", "city", "town",
                      "village", "port", "road", "forest", "cave", "ruins", "rest",
                      "barrel", "bridge", "gate", "wall", "market", "square", "hall"}

    for name in intro_matches:
        name_lower = name.lower()
        # Skip player characters
        if name_lower in player_characters:
            continue
        # Skip if already known
        if name_lower in {n.lower() for n in known_npcs}:
            if name not in known_mentions:
                known_mentions.append(name)
            continue
        # Skip if it contains location-sounding words
        if set(name_lower.split()) & location_words:
            continue

        if name not in new_discoveries:
            new_discoveries.append(name)

    return known_mentions, new_discoveries


def detect_new_locations(text: str, speaker: str, known_locations: set) -> list[str]:
    """Detect potential new location names from DM narration."""
    if speaker.lower() != "dm":
        return []

    new_locations = []

    # Look for location-introducing patterns followed by a proper name
    loc_intro_patterns = [
        r'\b(?:arrive\s+at|enter|reach|come\s+to|approach)\s+(?:the\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})',
        r'\b(?:place\s+called|tavern\s+called|inn\s+called|city\s+of|town\s+of|village\s+of)\s+(?:the\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})',
    ]

    # Words that indicate a person, not a location
    person_indicators = {"named", "called"}

    for pattern in loc_intro_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            if match.lower() not in {loc.lower() for loc in known_locations}:
                # Make sure this isn't actually a person name (check surrounding context)
                # Skip if the match appears right after "named" in the text
                name_check = re.search(r'\bnamed\s+' + re.escape(match), text)
                if not name_check:
                    new_locations.append(match)

    return new_locations


def tag_transcript(input_path: Path, config_dir: Path, campaign_override: str = None) -> dict:
    """
    Tag a transcript with contextual markers.
    Uses session0 + campaign knowledge for context.
    Updates campaign knowledge with new discoveries.
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Load configs
    session0 = load_session0(config_dir)
    campaign_name = campaign_override or session0.get("campaign", "Default")
    knowledge = load_campaign_knowledge(config_dir, campaign_name)

    # Merge player characters from both sources
    player_characters = set(
        name.lower() for name in
        session0.get("playerCharacters", []) + knowledge.get("playerCharacters", [])
    )

    # Build known entity sets
    known_npcs = set(knowledge.get("npcs", {}).keys())
    known_locations = set(knowledge.get("locations", {}).keys())

    session_title = data.get("title", "Unknown Session")
    segments = data.get("transcript", [])

    print(f"Campaign: {campaign_name}")
    print(f"Session: {session_title}")
    print(f"Tagging {len(segments)} segments...")
    print(f"  Known PCs: {list(player_characters)}")
    print(f"  Known NPCs: {list(known_npcs) or 'none yet'}")
    print(f"  Known Locations: {list(known_locations) or 'none yet'}")
    print()

    # Track discoveries this session
    session_new_npcs = {}
    session_new_locations = {}
    session_known_npc_mentions = {}
    session_known_loc_mentions = {}
    tag_counts = {"COMBAT": 0, "LOCATION": 0, "LOOT": 0, "ROLEPLAY": 0, "PLANNING": 0, "NPC": 0, "NEW_NPC": 0}

    for seg in segments:
        text = seg.get("text", "")
        speaker = seg.get("speaker", "")

        # Detect standard tags
        tags = detect_tags(text, speaker, known_npcs, known_locations)

        # Detect NPCs
        known_mentions, new_discoveries = detect_npcs(text, speaker, player_characters, known_npcs)

        if known_mentions:
            tags.append("NPC")
            for npc in known_mentions:
                session_known_npc_mentions[npc] = session_known_npc_mentions.get(npc, 0) + 1

        if new_discoveries:
            tags.append("NEW_NPC")
            for npc in new_discoveries:
                session_new_npcs[npc] = session_new_npcs.get(npc, 0) + 1
                # Add to known set so subsequent segments recognize it
                known_npcs.add(npc)

        # Detect new locations
        new_locs = detect_new_locations(text, speaker, known_locations)
        if new_locs:
            if "LOCATION" not in tags:
                tags.append("LOCATION")
            for loc in new_locs:
                session_new_locations[loc] = session_new_locations.get(loc, 0) + 1
                known_locations.add(loc)

        # Check known location mentions
        for loc in knowledge.get("locations", {}).keys():
            if loc.lower() in text.lower():
                session_known_loc_mentions[loc] = session_known_loc_mentions.get(loc, 0) + 1

        # Add tags to segment
        seg["tags"] = tags
        for tag in tags:
            if tag in tag_counts:
                tag_counts[tag] += 1

    # --- Update campaign knowledge ---
    if session_title not in knowledge.get("sessionsProcessed", []):
        knowledge.setdefault("sessionsProcessed", []).append(session_title)

    knowledge["lastUpdated"] = str(date.today())

    # Merge player characters
    for pc in session0.get("playerCharacters", []):
        if pc not in knowledge.get("playerCharacters", []):
            knowledge.setdefault("playerCharacters", []).append(pc)

    # Add new NPCs
    for npc, count in session_new_npcs.items():
        if npc not in knowledge.get("npcs", {}):
            knowledge.setdefault("npcs", {})[npc] = {
                "firstSeen": session_title,
                "mentions": count,
            }
        else:
            knowledge["npcs"][npc]["mentions"] = knowledge["npcs"][npc].get("mentions", 0) + count

    # Update known NPC mention counts
    for npc, count in session_known_npc_mentions.items():
        if npc in knowledge.get("npcs", {}):
            knowledge["npcs"][npc]["mentions"] = knowledge["npcs"][npc].get("mentions", 0) + count

    # Add new locations
    for loc, count in session_new_locations.items():
        if loc not in knowledge.get("locations", {}):
            knowledge.setdefault("locations", {})[loc] = {
                "firstSeen": session_title,
                "mentions": count,
            }
        else:
            knowledge["locations"][loc]["mentions"] = knowledge["locations"][loc].get("mentions", 0) + count

    # Update known location mention counts
    for loc, count in session_known_loc_mentions.items():
        if loc in knowledge.get("locations", {}):
            knowledge["locations"][loc]["mentions"] = knowledge["locations"][loc].get("mentions", 0) + count

    # Save updated knowledge
    save_campaign_knowledge(config_dir, campaign_name, knowledge)

    # --- Build output ---
    summary = {
        "tagCounts": tag_counts,
        "newNPCs": session_new_npcs,
        "knownNPCMentions": session_known_npc_mentions,
        "newLocations": session_new_locations,
        "totalSegments": len(segments),
        "taggedSegments": sum(1 for s in segments if s.get("tags")),
    }

    output = data.copy()
    output["transcript"] = segments
    output["tags_summary"] = summary

    # Rebuild notes with tags
    notes_lines = []
    for seg in segments:
        timestamp = format_timestamp(seg["start"])
        tag_str = " ".join(f"[{t}]" for t in seg.get("tags", []))
        prefix = f"{tag_str} " if tag_str else ""
        notes_lines.append(f"[{timestamp}] {prefix}{seg['speaker']}: {seg['text']}")

    output["notes"] = "\n".join(notes_lines)

    # Print results
    print(f"Results:")
    print(f"  Combat segments: {tag_counts['COMBAT']}")
    print(f"  Location segments: {tag_counts['LOCATION']}")
    print(f"  Loot segments: {tag_counts['LOOT']}")
    print(f"  Roleplay segments: {tag_counts['ROLEPLAY']}")
    print(f"  Planning segments: {tag_counts['PLANNING']}")
    print(f"  Known NPC mentions: {tag_counts['NPC']}")
    print(f"  New NPCs discovered: {tag_counts['NEW_NPC']}")
    if session_new_npcs:
        print(f"    -> {', '.join(session_new_npcs.keys())}")
    if session_new_locations:
        print(f"  New locations discovered: {', '.join(session_new_locations.keys())}")

    return output


def main():
    parser = argparse.ArgumentParser(description="Tag a D&D session transcript with contextual markers")
    parser.add_argument("transcript", help="Path to the transcript JSON file")
    parser.add_argument("--campaign", help="Campaign name (overrides session0.json)")
    parser.add_argument("--config-dir", default=None, help="Path to config directory")
    parser.add_argument("--output", "-o", help="Output file path (default: adds _tagged suffix)")
    # Keep --session0 for backwards compat but it's now loaded automatically
    parser.add_argument("--session0", help="(deprecated) Path to session0.json")
    args = parser.parse_args()

    input_path = Path(args.transcript)
    if not input_path.exists():
        print(f"File not found: {input_path}")
        sys.exit(1)

    # Determine config directory
    if args.config_dir:
        config_dir = Path(args.config_dir)
    else:
        # Try relative paths from common locations
        candidates = [
            Path("../config"),
            Path("config"),
            input_path.parent.parent / "config",
        ]
        config_dir = next((c for c in candidates if c.exists()), Path("../config"))

    output = tag_transcript(input_path, config_dir, campaign_override=args.campaign)

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
