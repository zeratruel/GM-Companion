const { EndBehaviorType } = require('@discordjs/voice');
const { pipeline } = require('stream/promises');
const { createWriteStream, mkdirSync } = require('fs');
const { join } = require('path');
const { OpusDecodingStream } = require('./opus-decoder');
const { v4: uuidv4 } = require('uuid');

class SessionRecorder {
  constructor(connection, guildId, title, characterMap) {
    this.connection = connection;
    this.guildId = guildId;
    this.title = title;
    this.characterMap = characterMap;
    this.sessionId = uuidv4();
    this.startTime = null;
    this.speakers = new Map(); // userId -> { username, stream, filePath }
    this.outputDir = null;
    this.receiver = null;
  }

  async start() {
    this.startTime = Date.now();
    const dateStr = new Date().toISOString().split('T')[0];
    this.outputDir = join(process.cwd(), 'recordings', `${dateStr}_${this.sanitizeTitle(this.title)}`);
    mkdirSync(this.outputDir, { recursive: true });

    this.receiver = this.connection.receiver;

    // Listen for new speakers
    this.receiver.speaking.on('start', (userId) => {
      if (!this.speakers.has(userId)) {
        this.startRecordingUser(userId);
      }
    });

    // Save session metadata
    const metadata = {
      sessionId: this.sessionId,
      title: this.title,
      date: dateStr,
      startTime: new Date().toISOString(),
      guildId: this.guildId,
      speakers: {},
    };

    const metaPath = join(this.outputDir, 'session_meta.json');
    require('fs').writeFileSync(metaPath, JSON.stringify(metadata, null, 2));

    console.log(`Recording started: ${this.title} -> ${this.outputDir}`);
  }

  startRecordingUser(userId) {
    const opusStream = this.receiver.subscribe(userId, {
      end: {
        behavior: EndBehaviorType.Manual,
      },
    });

    // Resolve username from the connection's guild
    const member = this.connection.joinConfig;
    const filename = `${userId}.pcm`;
    const filePath = join(this.outputDir, filename);
    const writeStream = createWriteStream(filePath);

    const decoder = new OpusDecodingStream();

    this.speakers.set(userId, {
      odStream: opusStream,
      decoder: decoder,
      writeStream: writeStream,
      filePath: filePath,
      startedAt: Date.now(),
    });

    // Pipe: Opus packets -> PCM decoder -> file
    opusStream.pipe(decoder).pipe(writeStream);

    opusStream.on('error', (err) => {
      console.error(`Opus stream error for user ${userId}:`, err.message);
    });

    writeStream.on('error', (err) => {
      console.error(`Write stream error for user ${userId}:`, err.message);
    });

    console.log(`Started recording user: ${userId}`);
  }

  async stop() {
    // End all user subscriptions
    for (const [userId, speaker] of this.speakers) {
      try {
        speaker.odStream.destroy();
        speaker.decoder.destroy();
        speaker.writeStream.end();
      } catch (err) {
        console.error(`Error stopping stream for ${userId}:`, err.message);
      }
    }

    // Update metadata with speaker info and end time
    const metaPath = join(this.outputDir, 'session_meta.json');
    const metadata = JSON.parse(require('fs').readFileSync(metaPath, 'utf-8'));
    metadata.endTime = new Date().toISOString();
    metadata.durationMs = Date.now() - this.startTime;

    // Map user IDs to speaker info
    const speakerInfo = {};
    for (const [userId, speaker] of this.speakers) {
      speakerInfo[userId] = {
        file: `${userId}.pcm`,
        characterName: this.characterMap[userId] || null,
        offsetMs: speaker.startedAt - this.startTime,
      };
    }
    metadata.speakers = speakerInfo;
    metadata.characterMap = this.characterMap;

    require('fs').writeFileSync(metaPath, JSON.stringify(metadata, null, 2));

    console.log(`Recording stopped. Files saved to: ${this.outputDir}`);
    return this.outputDir;
  }

  getDuration() {
    if (!this.startTime) return '0:00';
    const elapsed = Math.floor((Date.now() - this.startTime) / 1000);
    const minutes = Math.floor(elapsed / 60);
    const seconds = elapsed % 60;
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
  }

  getSpeakerCount() {
    return this.speakers.size;
  }

  sanitizeTitle(title) {
    return title.replace(/[^a-zA-Z0-9_-]/g, '_').substring(0, 50);
  }
}

module.exports = { SessionRecorder };
