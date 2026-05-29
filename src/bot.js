const { Client, GatewayIntentBits, Events } = require('discord.js');
const { joinVoiceChannel, VoiceConnectionStatus, entersState, getVoiceConnection } = require('@discordjs/voice');
const { SessionRecorder } = require('./recorder');
const { loadCharacterMap } = require('./utils');
const path = require('path');
require('dotenv').config();

// Load DAVE encryption support
let DAVESession;
try {
  DAVESession = require('@snazzah/davey');
} catch {
  console.warn('Warning: @snazzah/davey not found. DAVE encryption may not work.');
}

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.GuildVoiceStates,
    GatewayIntentBits.MessageContent,
  ],
});

const PREFIX = process.env.PREFIX || '!';
const activeSessions = new Map(); // guildId -> SessionRecorder
let voiceConnections = new Map(); // guildId -> VoiceConnection
const intentionalDisconnects = new Set(); // guildIds where we intentionally left

client.once(Events.ClientReady, () => {
  console.log(`Bot ready! Logged in as ${client.user.tag}`);
});

client.on(Events.MessageCreate, async (message) => {
  if (message.author.bot) return;
  if (!message.content.startsWith(PREFIX)) return;

  const args = message.content.slice(PREFIX.length).trim().split(/ +/);
  const command = args.shift().toLowerCase();

  switch (command) {
    case 'join':
      await handleJoin(message);
      break;
    case 'leave':
      await handleLeave(message);
      break;
    case 'session':
      await handleSession(message, args);
      break;
    case 'status':
      await handleStatus(message);
      break;
    case 'help':
      await handleHelp(message);
      break;
    default:
      break;
  }
});

async function handleJoin(message) {
  const voiceChannel = message.member?.voice.channel;
  if (!voiceChannel) {
    return message.reply('You need to be in a voice channel for me to join!');
  }

  try {
    const connection = joinVoiceChannel({
      channelId: voiceChannel.id,
      guildId: voiceChannel.guild.id,
      adapterCreator: voiceChannel.guild.voiceAdapterCreator,
      selfDeaf: false,
      selfMute: true,
    });

    // Debug: log all state transitions
    connection.on('stateChange', (oldState, newState) => {
      console.log(`Voice connection: ${oldState.status} -> ${newState.status}`);
    });

    // Handle disconnection with reconnect logic
    connection.on(VoiceConnectionStatus.Disconnected, async () => {
      // Don't reconnect if we intentionally left
      if (intentionalDisconnects.has(message.guild.id)) {
        intentionalDisconnects.delete(message.guild.id);
        connection.destroy();
        voiceConnections.delete(message.guild.id);
        return;
      }
      try {
        await Promise.race([
          entersState(connection, VoiceConnectionStatus.Signalling, 5_000),
          entersState(connection, VoiceConnectionStatus.Connecting, 5_000),
        ]);
      } catch (error) {
        connection.destroy();
        voiceConnections.delete(message.guild.id);
      }
    });

    // Wait for the connection to be ready
    await entersState(connection, VoiceConnectionStatus.Ready, 30_000);

    voiceConnections.set(message.guild.id, connection);
    console.log(`Successfully joined voice channel: ${voiceChannel.name}`);
    message.reply(`Joined **${voiceChannel.name}**! Use \`${PREFIX}session start "Session Title"\` to begin recording.`);
  } catch (error) {
    console.error('Failed to join voice channel:', error);
    message.reply(`Failed to join the voice channel. Connection state debug has been logged. Make sure the bot has **Connect** and **Speak** permissions on this specific channel.`);
  }
}

async function handleLeave(message) {
  const guildId = message.guild.id;

  // Stop any active session first
  if (activeSessions.has(guildId)) {
    const session = activeSessions.get(guildId);
    await session.stop();
    activeSessions.delete(guildId);
    message.channel.send('Active session stopped and saved.');
  }

  const connection = voiceConnections.get(guildId);
  if (connection) {
    intentionalDisconnects.add(guildId);
    connection.destroy();
    voiceConnections.delete(guildId);
    message.reply('Left the voice channel.');
  } else {
    message.reply("I'm not in a voice channel.");
  }
}

async function handleSession(message, args) {
  const guildId = message.guild.id;
  const subcommand = args.shift()?.toLowerCase();

  if (!subcommand) {
    return message.reply(`Usage: \`${PREFIX}session start "Title"\` or \`${PREFIX}session stop\``);
  }

  switch (subcommand) {
    case 'start': {
      if (activeSessions.has(guildId)) {
        return message.reply('A session is already being recorded! Use `!session stop` first.');
      }

      const connection = voiceConnections.get(guildId);
      if (!connection) {
        return message.reply(`I need to be in a voice channel first. Use \`${PREFIX}join\``);
      }

      // Parse title from remaining args (supports quotes)
      const title = args.join(' ').replace(/^["']|["']$/g, '') || `Session ${Date.now()}`;
      const characterMap = loadCharacterMap();

      const session = new SessionRecorder(connection, guildId, title, characterMap);
      await session.start();
      activeSessions.set(guildId, session);

      message.reply(`🔴 **Recording started!** Session: "${title}"\nUse \`${PREFIX}session stop\` to end recording.`);
      break;
    }

    case 'stop': {
      if (!activeSessions.has(guildId)) {
        return message.reply('No active session to stop.');
      }

      const session = activeSessions.get(guildId);
      const outputPath = await session.stop();
      activeSessions.delete(guildId);

      message.reply(`⏹️ **Recording stopped!** Audio saved.\nFiles at: \`${outputPath}\`\nRun \`npm run transcribe\` to generate the transcript.`);
      break;
    }

    default:
      message.reply(`Unknown subcommand. Use \`${PREFIX}session start "Title"\` or \`${PREFIX}session stop\``);
  }
}

async function handleStatus(message) {
  const guildId = message.guild.id;
  const session = activeSessions.get(guildId);

  if (!session) {
    const inChannel = voiceConnections.has(guildId);
    return message.reply(inChannel
      ? 'In voice channel, but not recording. Use `!session start "Title"` to begin.'
      : 'Not connected to any voice channel.');
  }

  const duration = session.getDuration();
  const speakers = session.getSpeakerCount();
  message.reply(`🔴 **Recording in progress**\nSession: "${session.title}"\nDuration: ${duration}\nSpeakers detected: ${speakers}`);
}

async function handleHelp(message) {
  const help = [
    '**D&D Session Recorder**',
    '',
    `\`${PREFIX}join\` — Join your current voice channel`,
    `\`${PREFIX}leave\` — Leave voice channel (stops recording if active)`,
    `\`${PREFIX}session start "Title"\` — Start recording the session`,
    `\`${PREFIX}session stop\` — Stop recording and save audio`,
    `\`${PREFIX}status\` — Check recording status`,
    `\`${PREFIX}help\` — Show this message`,
  ].join('\n');

  message.reply(help);
}

client.login(process.env.DISCORD_TOKEN);
