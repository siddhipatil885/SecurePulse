// Generate our own offline two-tone alert, with an envelope to prevent clicks.
import { mkdirSync, writeFileSync } from 'node:fs';
const rate = 22050;
const samples = rate * 2;
const data = Buffer.alloc(44 + samples * 2);
data.write('RIFF'); data.writeUInt32LE(data.length - 8, 4); data.write('WAVEfmt ', 8);
data.writeUInt32LE(16, 16); data.writeUInt16LE(1, 20); data.writeUInt16LE(1, 22);
data.writeUInt32LE(rate, 24); data.writeUInt32LE(rate * 2, 28);
data.writeUInt16LE(2, 32); data.writeUInt16LE(16, 34); data.write('data', 36); data.writeUInt32LE(samples * 2, 40);
for (let i = 0; i < samples; i++) {
  const t = i / rate;
  const phase = t % .5;
  const envelope = phase < .28 ? Math.min(1, phase / .01, (.28 - phase) / .02) : 0;
  const frequency = Math.floor(t / .5) % 2 ? 1100 : 850;
  data.writeInt16LE(Math.round(Math.sin(2 * Math.PI * frequency * t) * .72 * envelope * 32767), 44 + i * 2);
}
mkdirSync(new URL('../assets/', import.meta.url), { recursive: true });
writeFileSync(new URL('../assets/assignment-alarm.wav', import.meta.url), data);
