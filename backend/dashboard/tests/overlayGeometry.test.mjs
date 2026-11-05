import assert from 'node:assert/strict';
import test from 'node:test';
import { projectBox } from '../src/components/overlayGeometry.ts';

test('normalized coordinates stay aligned when playback exceeds detector resolution', () => {
  // A box normalized from a 640x360 detector occupies the same fraction of
  // 1920x1080 playback, rather than shrinking by the resolution ratio.
  assert.deepEqual(projectBox({ x: 0.25, y: 0.25, width: 0.5, height: 0.5 }, 960, 540, 1920, 1080, 'cover'),
    { x: 240, y: 135, width: 480, height: 270 });
});

test('cover offsets coordinates into the cropped video rectangle', () => {
  assert.deepEqual(projectBox({ x: 0.25, y: 0.25, width: 0.5, height: 0.5 }, 640, 480, 1280, 720, 'cover'),
    { x: 106.66666666666669, y: 120, width: 426.66666666666663, height: 240 });
});

test('contain offsets coordinates past the letterbox', () => {
  assert.deepEqual(projectBox({ x: 0.25, y: 0.25, width: 0.5, height: 0.5 }, 640, 480, 1280, 720, 'contain'),
    { x: 160, y: 150, width: 320, height: 180 });
});
