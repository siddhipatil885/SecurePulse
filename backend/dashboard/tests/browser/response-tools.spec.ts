import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';

const password = 'Dashboard-test-pass123';
test.beforeEach(async ({ request }) => {
  expect((await request.post('http://127.0.0.1:18081/__test/reset')).ok()).toBeTruthy();
});
test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: 'wait' }); });

async function openIncident(page: Page, accept = true) {
  await page.goto('/');
  await page.getByLabel('Email', { exact: true }).fill('owner@example.test');
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByLabel('Select property')).toBeVisible();
  const ownerLogin = await page.request.post('/api/v1/auth/login', { data: { email: 'owner@example.test', password } });
  const owner = { Authorization: `Bearer ${(await ownerLogin.json()).access_token}` };
  const created = await page.request.post('/api/v1/reporter/incidents', { headers: { ...owner, 'X-Idempotency-Key': 'response-tools-report' },
    data: { property_id: 1, incident_type: 'THEFT', address: '11 North Street', latitude: 19.01, longitude: 72.01 } });
  expect(created.status()).toBe(201);
  const incident = await created.json();
  const offered = await page.request.post('/api/v1/dispatch/offers', { headers: owner,
    data: { property_id: 1, reporter_incident_id: incident.id, marshal_profile_id: 1, expires_in_seconds: 300, idempotency_key: 'response-tools-offer' } });
  expect(offered.status()).toBe(201);
  let assignment = await offered.json();
  const login = await page.request.post('/api/v1/auth/login', { data: { email: 'marshal@example.test', password } });
  const marshal = { Authorization: `Bearer ${(await login.json()).access_token}` };
  if (accept) {
    const accepted = await page.request.post(`/api/v1/dispatch/offers/${assignment.id}/accept`, { headers: marshal, data: { expected_version: assignment.version } });
    expect(accepted.status()).toBe(200); assignment = await accepted.json();
  }
  await page.getByRole('button', { name: /^Incidents \(/ }).click();
  await page.getByRole('button', { name: new RegExp(`#${incident.id} · THEFT`) }).click();
  await expect(page.getByRole('heading', { name: `Reported incident #${incident.id}`, exact: true })).toBeVisible();
  return { incident, assignment, marshal };
}

test('live marshal positions refresh without a click, export in the report and disappear after completion', async ({ page }) => {
  const { incident, assignment, marshal } = await openIncident(page);
  await expect(page.getByText('Waiting for the responder to share a location.')).toBeVisible();
  const locationUrl = `/api/v1/marshal/assignments/${assignment.id}/location`;
  expect((await page.request.post(locationUrl, { headers: marshal, data: { latitude: 19, longitude: 72, accuracy_m: 5, speed_mps: 8 } })).status()).toBe(200);
  await expect(page.getByText('19.00000, 72.00000', { exact: true })).toBeVisible({ timeout: 5000 });
  await expect(page.getByText('Location updated recently')).toBeVisible();
  await expect(page.getByText(/Estimated arrival:/)).toBeVisible();
  await expect.poll(async () => (await page.request.post(locationUrl, { headers: marshal,
    data: { latitude: 19.001, longitude: 72.001, accuracy_m: 5, speed_mps: 8 } })).status(), { intervals: [1000], timeout: 10000 }).toBe(200);
  await expect(page.getByText('19.00100, 72.00100', { exact: true })).toBeVisible({ timeout: 5000 });
  await expect(page.getByRole('link', { name: 'Open reported position in maps' })).toHaveAttribute('href', /19.001.*72.001/);
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download incident report', exact: true }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe(`property-1-reporter-incident-${incident.id}-report.json`);
  const report = JSON.parse(await readFile((await download.path())!, 'utf8'));
  expect(report.incident.source_id).toBe(incident.id);
  expect(report.incident.latest_assignment.responder_location.latitude).toBe(19.001);
  expect(report.tracking.location_history_included).toBe(false);
  let version = assignment.version;
  for (const status of ['EN_ROUTE', 'ON_SCENE', 'COMPLETED']) {
    const result = await page.request.post(`/api/v1/dispatch/offers/${assignment.id}/progress`, { headers: marshal, data: { expected_version: version, status } });
    expect(result.status()).toBe(200); version = (await result.json()).version;
  }
  await expect(page.getByLabel('Responder location', { exact: true })).toHaveCount(0);
});

test('stale positions are labelled and their arrival estimates are hidden', async ({ page }) => {
  await page.route('**/cases/reporter/*', async route => {
    if (!/\/cases\/reporter\/\d+$/.test(new URL(route.request().url()).pathname)) return route.continue();
    const response = await route.fetch(); const body = await response.json();
    if (body.latest_assignment) body.latest_assignment.responder_location = { latitude: 19, longitude: 72,
      updated_at: new Date(Date.now() - 120000).toISOString(), eta_seconds: 180, accuracy_m: 5 };
    await route.fulfill({ response, json: body });
  });
  await openIncident(page);
  await expect(page.getByText(/Location is stale/)).toBeVisible();
  await expect(page.getByText('19.00000, 72.00000', { exact: true })).toBeVisible();
  await expect(page.getByText(/Estimated arrival:/)).toHaveCount(0);
});

test('pending offers do not expose responder locations', async ({ page }) => {
  await openIncident(page, false);
  await expect(page.getByText(/Assignment #\d+ · OFFERED/)).toBeVisible();
  await expect(page.getByLabel('Responder location', { exact: true })).toHaveCount(0);
});

test('report errors allow retry and a property switch cancels a pending export', async ({ page }) => {
  const { incident } = await openIncident(page);
  const reportPath = `**/cases/reporter/${incident.id}/report`;
  await page.route(reportPath, route => route.fulfill({ status: 503, json: { error: { message: 'Report temporarily unavailable' } } }));
  await page.getByRole('button', { name: 'Download incident report', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText('Report temporarily unavailable');
  await expect(page.getByRole('button', { name: 'Download incident report', exact: true })).toBeEnabled();
  await page.unroute(reportPath);
  let release!: () => void;
  let entered!: () => void;
  const waiting = new Promise<void>(resolve => { release = resolve; });
  const requested = new Promise<void>(resolve => { entered = resolve; });
  await page.route(reportPath, async route => {
    const response = await route.fetch(); entered(); await waiting;
    await route.fulfill({ response }).catch(() => {});
  });
  let downloads = 0; page.on('download', () => { downloads++; });
  await page.getByRole('button', { name: 'Download incident report', exact: true }).click();
  await requested;
  await expect(page.getByRole('button', { name: 'Preparing report…', exact: true })).toBeDisabled();
  await page.getByLabel('Select property').selectOption('2');
  await expect(page.getByRole('heading', { name: 'South office', exact: true })).toBeVisible();
  release();
  await page.unroute(reportPath);
  expect(downloads).toBe(0);
});

test('dashboard offers default to five minutes and reject longer deadlines', async ({ page }) => {
  await openIncident(page, false);
  await page.getByRole('button', { name: 'Cancel assignment', exact: true }).click();
  const timeout = page.getByLabel('Offer timeout (seconds)');
  await expect(timeout).toHaveValue('300');
  await expect(timeout).toHaveAttribute('max', '300');
  await timeout.fill('301');
  await page.getByRole('button', { name: 'Offer assignment', exact: true }).click();
  expect(await timeout.evaluate((input: HTMLInputElement) => input.validity.rangeOverflow)).toBe(true);
  await expect(page.getByRole('button', { name: 'Cancel assignment', exact: true })).toHaveCount(0);
  await timeout.fill('300');
  await page.getByRole('button', { name: 'Offer assignment', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Cancel assignment', exact: true })).toBeVisible();
});
