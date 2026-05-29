const { Transform } = require('stream');
const OpusScript = require('opusscript');

/**
 * Transforms incoming Opus packets into raw PCM audio data.
 * Discord sends per-user audio as: 48kHz, mono (1 channel), 16-bit signed LE
 * Frame size: 960 samples per frame (20ms at 48kHz)
 */
class OpusDecodingStream extends Transform {
  constructor() {
    super();
    // Discord voice is 48kHz, mono per user
    this.decoder = new OpusScript(48000, 1, OpusScript.Application.AUDIO);
    this.frameSize = 960; // 20ms at 48kHz
  }

  _transform(chunk, encoding, callback) {
    try {
      const decoded = this.decoder.decode(chunk, this.frameSize);
      this.push(Buffer.from(decoded));
      callback();
    } catch (err) {
      // Skip corrupted packets rather than crashing
      callback();
    }
  }

  _destroy(err, callback) {
    this.decoder.delete();
    callback(err);
  }
}

module.exports = { OpusDecodingStream };
