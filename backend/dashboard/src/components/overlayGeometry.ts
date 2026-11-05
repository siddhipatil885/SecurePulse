export interface NormalizedBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export function projectBox(
  box: NormalizedBox,
  containerWidth: number,
  containerHeight: number,
  videoWidth: number,
  videoHeight: number,
  fitMode: 'cover' | 'contain',
): NormalizedBox {
  const scale = fitMode === 'contain'
    ? Math.min(containerWidth / videoWidth, containerHeight / videoHeight)
    : Math.max(containerWidth / videoWidth, containerHeight / videoHeight);
  const width = videoWidth * scale;
  const height = videoHeight * scale;
  return {
    x: (containerWidth - width) / 2 + box.x * width,
    y: (containerHeight - height) / 2 + box.y * height,
    width: box.width * width,
    height: box.height * height,
  };
}
