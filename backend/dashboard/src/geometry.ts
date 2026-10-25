import type { BoundingBox } from './types';

// Use only with metadata tied to the displayed frame/snapshot.
export function projectBox(box: BoundingBox, sourceWidth: number, sourceHeight: number,
  viewportWidth: number, viewportHeight: number, fit: 'cover' | 'contain', mirrored = false) {
  const values = [box.x, box.y, box.width, box.height, sourceWidth, sourceHeight, viewportWidth, viewportHeight];
  if (!values.every(Number.isFinite) || Math.min(sourceWidth, sourceHeight, viewportWidth, viewportHeight) <= 0
    || box.x < 0 || box.y < 0 || box.width <= 0 || box.height <= 0 || box.x + box.width > 1.001 || box.y + box.height > 1.001) return null;
  const scale = (fit === 'contain' ? Math.min : Math.max)(viewportWidth / sourceWidth, viewportHeight / sourceHeight);
  const width = sourceWidth * scale, height = sourceHeight * scale;
  return { left: (viewportWidth - width) / 2 + (mirrored ? 1 - box.x - box.width : box.x) * width,
    top: (viewportHeight - height) / 2 + box.y * height, width: box.width * width, height: box.height * height };
}
