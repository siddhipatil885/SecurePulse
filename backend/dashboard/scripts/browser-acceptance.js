// Paste this entire file into the dashboard browser's DevTools console.
// During the next 60 seconds, walk through each camera and leave its view.
// This reads DOM/video timing only; it saves no imagery and sends no requests.
(async () => {
  const cameras = new Map();
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  for (let sample = 0; sample < 120; sample += 1) {
    for (const container of document.querySelectorAll('.camera-feed-container')) {
      const id = container.dataset.cameraId;
      const video = container.querySelector('video');
      if (!id || !video) continue;
      const state = cameras.get(id) ?? {
        camera_id: id, playback_advanced: false, boxes_seen: false,
        boxes_moved: false, boxes_cleared: false, invalid_confidence: false,
        consecutive_advancing_samples: 0,
        lastTime: video.currentTime, previousBoxes: new Map(),
      };
      const advancing = video.readyState >= 2 && video.videoWidth > 0 && video.currentTime > state.lastTime + 0.05;
      state.playback_advanced ||= advancing;
      state.consecutive_advancing_samples = advancing ? state.consecutive_advancing_samples + 1 : 0;
      state.lastTime = video.currentTime;
      const boxes = [...container.querySelectorAll('.detection-box')];
      if (state.boxes_seen && boxes.length === 0) state.boxes_cleared = true;
      state.boxes_seen ||= boxes.length > 0;
      for (const box of boxes) {
        const key = box.dataset.trackId;
        const position = [box.style.left, box.style.top, box.style.width, box.style.height].join(',');
        if (state.previousBoxes.has(key) && state.previousBoxes.get(key) !== position) state.boxes_moved = true;
        state.previousBoxes.set(key, position);
        const confidence = box.querySelector('.person-box-label')?.textContent?.match(/(-?\d+)%/);
        if (confidence && (Number(confidence[1]) < 0 || Number(confidence[1]) > 100)) state.invalid_confidence = true;
      }
      cameras.set(id, state);
    }
    await wait(500);
  }
  const results = [...cameras.values()].map(({ lastTime: _lastTime, previousBoxes: _previousBoxes, ...state }) => ({
    ...state,
    playback: state.consecutive_advancing_samples >= 6 ? 'pass' : 'fail',
    overlay: state.boxes_seen && state.boxes_moved && state.boxes_cleared && !state.invalid_confidence ? 'pass' : 'not_verified',
  }));
  const report = { observed_at: new Date().toISOString(), cameras: results,
    expected_camera_count: 2, both_cameras_observed: results.length === 2 };
  window.securePulseAcceptance = report;
  console.log(JSON.stringify(report, null, 2));
  return report;
})();
