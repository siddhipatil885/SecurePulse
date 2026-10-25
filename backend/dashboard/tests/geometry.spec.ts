import { test, expect } from '@playwright/test';
import { projectBox } from '../src/geometry';

test('letterboxing, cover crop, mirror and fullscreen resize preserve source coordinates', () => {
  const box = { x: .1, y: .2, width: .2, height: .3 };
  const contain = projectBox(box, 1920, 1080, 1000, 1000, 'contain')!;
  expect(contain.left).toBeCloseTo(100);
  expect(contain.top).toBeCloseTo(331.25);
  expect(contain.width).toBeCloseTo(200);
  expect(contain.height).toBeCloseTo(168.75);
  const cover = projectBox(box, 1920, 1080, 1000, 1000, 'cover')!;
  expect(cover.left).toBeCloseTo(-211.1111);
  expect(cover.top).toBeCloseTo(200);
  expect(projectBox(box, 1920, 1080, 1920, 1080, 'contain', true)!.left).toBeCloseTo(1344);
  expect(projectBox(box, 1920, 1080, 3840, 2160, 'contain')!.width).toBeCloseTo(768);
});
test('rejects invalid coordinates and missing dimensions', () => {
  expect(projectBox({ x: 0, y: 0, width: NaN, height: .2 }, 1920, 1080, 100, 100, 'cover')).toBeNull();
  expect(projectBox({ x: .9, y: 0, width: .5, height: .2 }, 1920, 1080, 100, 100, 'cover')).toBeNull();
  expect(projectBox({ x: 0, y: 0, width: .5, height: .2 }, 0, 1080, 100, 100, 'cover')).toBeNull();
});
