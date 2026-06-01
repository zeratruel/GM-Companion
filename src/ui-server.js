const express = require('express');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

const app = express();
const PORT = 3000;

app.use(express.json());
app.use(express.static(path.join(__dirname, '..', 'ui')));

// --- API Routes ---

// Get bot status
app.get('/api/status', (req, res) => {
  const botModule = require('./bot-state');
  res.json({
    botOnline: botModule.isBotOnline(),
    activeSession: botModule.getActiveSession(),
    connectedGuilds: botModule.getConnectedGuilds(),
  });
});

// Get character map
app.get('/api/characters', (req, res) => {
  const configPath = path.join(process.cwd(), 'config', 'characters.json');
  try {
    const data = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
    res.json(data);
  } catch {
    res.json({ characterMap: {}, dmUsername: "" });
  }
});

// Save character map
app.post('/api/characters', (req, res) => {
  const configPath = path.join(process.cwd(), 'config', 'characters.json');
  const configDir = path.dirname(configPath);
  if (!fs.existsSync(configDir)) fs.mkdirSync(configDir, { recursive: true });
  fs.writeFileSync(configPath, JSON.stringify(req.body, null, 2));
  res.json({ success: true });
});

// Get list of recordings
app.get('/api/recordings', (req, res) => {
  const recordingsDir = path.join(process.cwd(), 'recordings');
  if (!fs.existsSync(recordingsDir)) return res.json([]);

  const sessions = fs.readdirSync(recordingsDir)
    .filter(f => fs.statSync(path.join(recordingsDir, f)).isDirectory())
    .map(folder => {
      const metaPath = path.join(recordingsDir, folder, 'session_meta.json');
      let meta = {};
      try { meta = JSON.parse(fs.readFileSync(metaPath, 'utf-8')); } catch {}
      return {
        folder,
        title: meta.title || folder,
        date: meta.date || '',
        duration: meta.durationMs ? Math.round(meta.durationMs / 1000) : 0,
        speakers: Object.keys(meta.speakers || {}).length,
      };
    })
    .sort((a, b) => b.folder.localeCompare(a.folder));

  res.json(sessions);
});

// Get list of transcripts (full only, excludes condensed)
app.get('/api/transcripts', (req, res) => {
  // Check both possible transcript locations
  const transcriptsDirs = [
    path.join(process.cwd(), 'transcripts'),
    path.join(process.cwd(), 'transcriber', 'transcripts'),
  ];

  let allFiles = [];

  for (const transcriptsDir of transcriptsDirs) {
    if (!fs.existsSync(transcriptsDir)) continue;

    const files = fs.readdirSync(transcriptsDir)
      .filter(f => f.endsWith('.json') && !f.includes('_condensed') && !f.includes('_aggressive') && !f.includes('_game-only') && !f.includes('_tagged'))
      .map(file => {
        const filePath = path.join(transcriptsDir, file);
        const stat = fs.statSync(filePath);
        let data = {};
        try { data = JSON.parse(fs.readFileSync(filePath, 'utf-8')); } catch {}
        return {
          file,
          dir: transcriptsDir,
          title: data.title || file,
          date: data.date || '',
          segments: (data.transcript || []).length,
          duration: data.duration || '',
          createdAt: stat.mtimeMs,
          createdAtStr: stat.mtime.toLocaleString(),
        };
      });

    allFiles = allFiles.concat(files);
  }

  allFiles.sort((a, b) => b.createdAt - a.createdAt);
  res.json(allFiles);
});

// Get list of condensed transcripts only
app.get('/api/condensed', (req, res) => {
  const transcriptsDirs = [
    path.join(process.cwd(), 'transcripts'),
    path.join(process.cwd(), 'transcriber', 'transcripts'),
  ];

  let allFiles = [];

  for (const transcriptsDir of transcriptsDirs) {
    if (!fs.existsSync(transcriptsDir)) continue;

    const files = fs.readdirSync(transcriptsDir)
      .filter(f => f.endsWith('.json') && (f.includes('_condensed') || f.includes('_aggressive') || f.includes('_game-only') || f.includes('_tagged')))
      .map(file => {
        const filePath = path.join(transcriptsDir, file);
        const stat = fs.statSync(filePath);
        let data = {};
        try { data = JSON.parse(fs.readFileSync(filePath, 'utf-8')); } catch {}

        // Determine the mode from filename
        let mode = 'condensed';
        if (file.includes('_aggressive')) mode = 'aggressive';
        else if (file.includes('_game-only')) mode = 'game-only';
        else if (file.includes('_tagged')) mode = 'tagged';

        return {
          file,
          dir: transcriptsDir,
          title: data.title || file,
          date: data.date || '',
          segments: (data.transcript || []).length,
          duration: data.duration || '',
          mode,
          createdAt: stat.mtimeMs,
          createdAtStr: stat.mtime.toLocaleString(),
        };
      });

    allFiles = allFiles.concat(files);
  }

  allFiles.sort((a, b) => b.createdAt - a.createdAt);
  res.json(allFiles);
});

// Get a specific transcript
app.get('/api/transcripts/:file', (req, res) => {
  const locations = [
    path.join(process.cwd(), 'transcripts', req.params.file),
    path.join(process.cwd(), 'transcriber', 'transcripts', req.params.file),
  ];
  const filePath = locations.find(p => fs.existsSync(p));
  if (!filePath) return res.status(404).json({ error: 'Not found' });
  const data = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
  res.json(data);
});

// Run transcription (with progress streaming via SSE)
app.get('/api/transcribe/progress', (req, res) => {
  const { folder, preset } = req.query;
  const recordingPath = folder
    ? path.join('recordings', folder)
    : undefined;

  const venvPython = path.join(process.cwd(), 'transcriber', 'venv', 'Scripts', 'python.exe');
  const scriptPath = path.join(process.cwd(), 'transcriber', 'transcribe.py');

  const args = ['-u', scriptPath]; // -u for unbuffered output
  if (recordingPath) args.push(recordingPath);
  args.push('--preset', preset || 'quality');

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  const proc = spawn(venvPython, args, { cwd: process.cwd() });

  let output = '';

  proc.stdout.on('data', (data) => {
    const text = data.toString();
    output += text;
    // Parse progress from output lines
    const lines = text.split('\n');
    for (const line of lines) {
      if (line.trim()) {
        res.write(`data: ${JSON.stringify({ type: 'log', message: line.trim() })}\n\n`);
      }
    }
  });

  proc.stderr.on('data', (data) => {
    output += data.toString();
  });

  proc.on('close', (code) => {
    if (code === 0) {
      res.write(`data: ${JSON.stringify({ type: 'done', success: true, output })}\n\n`);
    } else {
      res.write(`data: ${JSON.stringify({ type: 'done', success: false, output })}\n\n`);
    }
    res.end();
  });

  req.on('close', () => {
    proc.kill();
  });
});

// Run transcription (non-streaming fallback)
app.post('/api/transcribe', (req, res) => {
  const { folder, preset } = req.body;
  const recordingPath = folder
    ? path.join('recordings', folder)
    : undefined;

  const venvPython = path.join(process.cwd(), 'transcriber', 'venv', 'Scripts', 'python.exe');
  const scriptPath = path.join(process.cwd(), 'transcriber', 'transcribe.py');

  const args = [scriptPath];
  if (recordingPath) args.push(recordingPath);
  args.push('--preset', preset || 'quality');

  const proc = spawn(venvPython, args, { cwd: process.cwd() });

  let output = '';
  let error = '';

  proc.stdout.on('data', (data) => { output += data.toString(); });
  proc.stderr.on('data', (data) => { error += data.toString(); });

  proc.on('close', (code) => {
    if (code === 0) {
      res.json({ success: true, output });
    } else {
      res.json({ success: false, output, error });
    }
  });
});

// Run tagger
app.post('/api/tag', (req, res) => {
  const { file } = req.body;

  // Find the transcript in either location
  const locations = [
    path.join(process.cwd(), 'transcripts', file),
    path.join(process.cwd(), 'transcriber', 'transcripts', file),
  ];
  const transcriptPath = locations.find(p => fs.existsSync(p));
  if (!transcriptPath) return res.json({ success: false, error: `File not found: ${file}` });

  const session0Path = path.join(process.cwd(), 'config', 'session0.json');

  const venvPython = path.join(process.cwd(), 'transcriber', 'venv', 'Scripts', 'python.exe');
  const scriptPath = path.join(process.cwd(), 'transcriber', 'tagger.py');

  const args = [scriptPath, transcriptPath];
  if (fs.existsSync(session0Path)) {
    args.push('--session0', session0Path);
  }

  const proc = spawn(venvPython, args, { cwd: path.join(process.cwd(), 'transcriber') });

  let output = '';
  let error = '';

  proc.stdout.on('data', (data) => { output += data.toString(); });
  proc.stderr.on('data', (data) => { error += data.toString(); });

  proc.on('close', (code) => {
    if (code === 0) {
      const stem = file.replace('.json', '');
      const outputFile = `${stem}_tagged.json`;
      res.json({ success: true, output, outputFile });
    } else {
      res.json({ success: false, output, error });
    }
  });
});

// Run condenser
app.post('/api/condense', (req, res) => {
  const { file, mode } = req.body;

  // Find the transcript in either location
  const locations = [
    path.join(process.cwd(), 'transcripts', file),
    path.join(process.cwd(), 'transcriber', 'transcripts', file),
  ];
  const transcriptPath = locations.find(p => fs.existsSync(p));
  if (!transcriptPath) return res.json({ success: false, error: `File not found: ${file}` });

  const venvPython = path.join(process.cwd(), 'transcriber', 'venv', 'Scripts', 'python.exe');
  const scriptPath = path.join(process.cwd(), 'transcriber', 'condense.py');

  const args = [scriptPath, transcriptPath, '--mode', mode || 'normal'];

  const proc = spawn(venvPython, args, { cwd: path.join(process.cwd(), 'transcriber') });

  let output = '';
  let error = '';

  proc.stdout.on('data', (data) => { output += data.toString(); });
  proc.stderr.on('data', (data) => { error += data.toString(); });

  proc.on('close', (code) => {
    if (code === 0) {
      // Determine the output filename
      const stem = file.replace('.json', '');
      const suffix = mode && mode !== 'normal' ? `_${mode}` : '_condensed';
      const outputFile = `${stem}${suffix}.json`;
      res.json({ success: true, output, outputFile });
    } else {
      res.json({ success: false, output, error });
    }
  });
});

// Delete a recording
app.delete('/api/recordings/:folder', (req, res) => {
  const folderPath = path.join(process.cwd(), 'recordings', req.params.folder);
  if (!fs.existsSync(folderPath)) return res.status(404).json({ error: 'Not found' });

  fs.rmSync(folderPath, { recursive: true, force: true });
  res.json({ success: true });
});

// Delete a transcript
app.delete('/api/transcripts/:file', (req, res) => {
  const locations = [
    path.join(process.cwd(), 'transcripts', req.params.file),
    path.join(process.cwd(), 'transcriber', 'transcripts', req.params.file),
  ];
  const filePath = locations.find(p => fs.existsSync(p));
  if (!filePath) return res.status(404).json({ error: 'Not found' });

  fs.unlinkSync(filePath);
  // Also delete the .txt version if it exists
  const txtPath = filePath.replace('.json', '.txt');
  if (fs.existsSync(txtPath)) fs.unlinkSync(txtPath);

  res.json({ success: true });
});

// Get .env config (token presence only, never expose the actual token)
app.get('/api/config', (req, res) => {
  const envPath = path.join(process.cwd(), '.env');
  let hasToken = false;
  let prefix = '!';
  try {
    const content = fs.readFileSync(envPath, 'utf-8');
    hasToken = content.includes('DISCORD_TOKEN=') && !content.includes('your_bot_token_here');
    const prefixMatch = content.match(/PREFIX=(.+)/);
    if (prefixMatch) prefix = prefixMatch[1].trim();
  } catch {}
  res.json({ hasToken, prefix });
});

// Save bot token
app.post('/api/config/token', (req, res) => {
  const { token, prefix } = req.body;
  const envPath = path.join(process.cwd(), '.env');
  const content = `DISCORD_TOKEN=${token}\nPREFIX=${prefix || '!'}\n`;
  fs.writeFileSync(envPath, content);
  res.json({ success: true });
});

function startUI() {
  app.listen(PORT, () => {
    console.log(`Control panel running at http://localhost:${PORT}`);
  });
}

module.exports = { startUI, app };
