import { test, expect } from '@playwright/test';
import type { Page, WebSocketRoute } from '@playwright/test';

async function fixture(page: Page) {
  let status = 'OPEN', down = false;
  const sockets: WebSocketRoute[] = [];
  const incident = () => ({ id: 42, property_id: 1, camera_id: 1, event_type: 'INTRUSION', object_type: 'person',
    confidence: .9, timestamp: new Date().toISOString(), severity: 'HIGH', status, reason: 'Restricted zone', zone: 'Entrance',
    frigate_event_id: 'fixture-person-1', created_at: new Date().toISOString(), metadata: { snapshot_url: 'https://untrusted.invalid/track' } });
  await page.route('**/health/ready', route => route.fulfill({ status: 503, json: { status: 'not_ready', checks: { database: 'ok', mqtt: 'unavailable' } } }));
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (down) return route.fulfill({ status: 503, json: {} });
    if (path.endsWith('/dashboard/session')) return route.fulfill({ json: { subject: 'test', scopes: ['read', 'write'], property_ids: [1, 2] } });
    if (path.endsWith('/properties')) return route.fulfill({ json: [{ id: 1, name: 'North' }, { id: 2, name: 'South' }] });
    if (path.endsWith('/cameras')) return route.fulfill({ json: [1, 2].map(id => ({ id, property_id: id, name: `Camera ${id}`, frigate_camera_name: `cam${id}`, enabled: false, health_status: null, health_observed_at: null })) });
    if (path.endsWith('/tracks')) return route.fulfill({ json: {} });
    if (path.endsWith('/commands')) { status = JSON.parse(route.request().postData()!).command === 'resolve' ? 'RESOLVED' : 'ACKNOWLEDGED'; return route.fulfill({ json: incident() }); }
    if (path.endsWith('/history')) return route.fulfill({ json: [{ id: 1, previous_status: null, new_status: status, actor_subject: 'fixture', reason: 'Restricted zone', correlation_id: 'fixture-person-1', occurred_at: new Date().toISOString() }] });
    if (path.endsWith('/evidence')) return route.fulfill({ json: [{ id: 8, type: 'SNAPSHOT' }] });
    if (path.includes('/evidence/8/access')) return route.fulfill({ status: 404, json: {} });
    if (path.endsWith('/incidents')) return route.fulfill({ json: { items: [incident()], total: 1, page: 1, page_size: 100 } });
    return route.fulfill({ json: incident() });
  });
  await page.routeWebSocket('**/events/stream', ws => { sockets.push(ws); ws.send(JSON.stringify({ version: 1, type: 'resync_required' })); });
  return { sockets, resolve: () => { status = 'RESOLVED'; }, fail: () => { down = true; } };
}
test('property selection, persisted details, commands, readiness and expired evidence', async ({ page }) => {
  await fixture(page); await page.goto('/');
  await expect(page.getByText('Incident 42: INTRUSION')).toBeVisible();
  await expect(page.getByText('MQTT consumer: offline')).toBeVisible();
  await page.screenshot({ path: 'test-results/dashboard-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 700, height: 900 });
  await expect(page.locator('.primary .camera-name')).toBeVisible();
  expect((await page.locator('.camera-feed-container.primary').boundingBox())!.height).toBeGreaterThan(250);
  await page.screenshot({ path: 'test-results/dashboard-narrow.png', fullPage: true });
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.getByLabel('Property', { exact: true }).selectOption('2');
  await expect(page.getByText('Incident 42: INTRUSION')).toHaveCount(0);
  await expect(page.getByLabel('Active camera').locator('option')).toHaveText(['Camera 2']);
  await page.getByLabel('Property', { exact: true }).selectOption('1');
  await page.getByText('Incident 42: INTRUSION').click();
  await expect(page.getByRole('region', { name: 'Incident details' })).toContainText('fixture-person-1');
  await page.getByRole('button', { name: 'View SNAPSHOT evidence 8' }).click();
  await expect(page.getByText('Evidence unavailable, expired, or forbidden.', { exact: false })).toBeVisible();
  await expect(page.locator('img[src*="untrusted"]')).toHaveCount(0);
  await page.getByLabel('Command reason').fill('Reviewed test evidence');
  await page.getByRole('button', { name: 'resolve', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Incident details' })).toContainText('HIGH / RESOLVED');
});
test('out of order/duplicate invalidations use REST truth, reconnect recovers and failures clear stale data', async ({ page }) => {
  const state = await fixture(page); await page.goto('/');
  await expect(page.getByText('Incident 42: INTRUSION')).toBeVisible();
  state.resolve();
  for (const sequence of [3, 3, 1]) state.sockets.at(-1)!.send(JSON.stringify({ version: 1, type: 'security_event', event_id: `fixture:${sequence}`, sequence }));
  await expect(page.getByText('No active security alerts')).toBeVisible();
  state.sockets.at(-1)!.close({ code: 1012 });
  await expect.poll(() => state.sockets.length).toBeGreaterThan(1);
  await expect(page.getByText('Incident 42: INTRUSION')).toBeVisible();
  state.fail(); state.sockets.at(-1)!.send(JSON.stringify({ version: 1, type: 'resync_required' }));
  await expect(page.getByText('Data unavailable.', { exact: false })).toBeVisible();
  await expect(page.getByText('Incident 42: INTRUSION')).toHaveCount(0);
});
test('authenticated requests use memory token and expired socket ends session', async ({ page }) => {
  const state = await fixture(page); await page.goto('/');
  await expect(page.getByText('Incident 42: INTRUSION')).toBeVisible();
  await page.getByLabel('Access token', { exact: true }).fill('test-token');
  const request = page.waitForRequest(r => r.url().includes('/dashboard/session') && r.headers().authorization === 'Bearer test-token');
  await page.getByRole('button', { name: 'Use session', exact: true }).click(); await request;
  await expect(page.getByText('Incident 42: INTRUSION')).toBeVisible();
  state.sockets.at(-1)!.close({ code: 4401 });
  await expect(page.getByText('Session expired or access denied.', { exact: false })).toBeVisible();
  await expect(page.getByText('Incident 42: INTRUSION')).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
});

test('simulated playback grant expiry, reconnect, fullscreen and resize states are visible', async ({ page }) => {
  await fixture(page);
  await page.route('**/api/v1/cameras?*', route => route.fulfill({ json: [{ id: 1, property_id: 1, name: 'Playback fixture', frigate_camera_name: 'fixture', enabled: true, health_status: null, health_observed_at: null }] }));
  let expired = true;
  await page.route('**/playback-access', route => route.fulfill({ status: expired ? 401 : 200,
    json: { grant: 'test-only-grant', expires_at: new Date(Date.now() + 60000).toISOString() } }));
  await page.route('**/webrtc', route => route.fulfill({ body: 'test-sdp', contentType: 'application/sdp' }));
  await page.addInitScript(() => {
    class FakePeer {
      iceGatheringState = 'complete'; connectionState = 'connected';
      localDescription = { sdp: 'test-offer' }; onconnectionstatechange: (() => void) | null = null;
      constructor() { Object.assign(window, { fixturePeer: this }); }
      addTransceiver() {}
      async createOffer() { return this.localDescription; }
      async setLocalDescription() {}
      async setRemoteDescription() { document.querySelector('video')?.dispatchEvent(new Event('playing')); }
      close() {}
    }
    Object.assign(window, { RTCPeerConnection: FakePeer });
  });
  await page.goto('/');
  await expect(page.getByText('Playback access expired or forbidden')).toBeVisible();
  expired = false; await page.getByRole('button', { name: 'Reconnect', exact: true }).click();
  await expect(page.getByText('LIVE · MUTED')).toBeVisible();
  await page.getByRole('button', { name: 'Fullscreen', exact: true }).click();
  await expect.poll(() => page.evaluate(() => !!document.fullscreenElement)).toBeTruthy();
  await page.evaluate(() => document.exitFullscreen());
  await page.setViewportSize({ width: 700, height: 900 });
  await expect(page.locator('.person-box')).toHaveCount(0);
  await page.evaluate(() => {
    const peer = (window as unknown as { fixturePeer: { connectionState: string; onconnectionstatechange: () => void } }).fixturePeer;
    peer.connectionState = 'disconnected'; peer.onconnectionstatechange();
  });
  await expect(page.getByText('Camera offline; reconnecting')).toBeVisible();
  await expect(page.getByText('LIVE · MUTED')).toHaveCount(0);
});
