const fs = require('fs');
const path = require('path');

/**
 * Load the character map from config/characters.json
 * Returns a map of Discord userId -> character name
 */
function loadCharacterMap() {
  const configPath = path.join(process.cwd(), 'config', 'characters.json');

  try {
    const raw = fs.readFileSync(configPath, 'utf-8');
    const config = JSON.parse(raw);
    return config.characterMap || {};
  } catch (err) {
    console.warn('Could not load character map:', err.message);
    return {};
  }
}

/**
 * Convert seconds to a human-readable duration string
 */
function formatDuration(seconds) {
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  if (hrs > 0) {
    return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

module.exports = { loadCharacterMap, formatDuration };
