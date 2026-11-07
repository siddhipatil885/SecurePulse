import { expect, test } from '@playwright/test';

const password = 'Dashboard-test-pass123';
test.beforeEach(async ({ request }) => {
  const response = await request.post('http://127.0.0.1:18081/__test/reset');
  expect(response.ok()).toBeTruthy();
  expect((await response.json()).mode).toBe('isolated-browser-test');
});
async function signIn(page, email = 'owner@example.test') {
  await page.goto('/');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByLabel('Select property')).toBeVisible();
  await expect(page.getByText('Live updates connected', { exact: true })).toBeVisible();
}

test('registration validates passwords, collects property details and persists a refresh-safe session', async ({ page, context }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Create an account', exact: true }).click();
  await page.getByLabel('Full name').fill('New dashboard owner');
  const email = `new-${Date.now()}@example.test`;
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByLabel('Confirm password').fill('different-password123');
  await page.getByRole('button', { name: 'Continue to property details' }).click();
  await expect(page.getByRole('alert')).toHaveText('Passwords do not match.');
  await page.getByLabel('Confirm password').fill(password);
  await page.getByRole('button', { name: 'Continue to property details' }).click();
  await page.getByLabel('Property name', { exact: true }).fill('New test residence');
  await page.getByLabel('Property address', { exact: true }).fill('44 Example Road');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'New test residence', exact: true })).toBeVisible();
  await expect(page.getByText('No cameras are configured.')).toBeVisible();
  const cookies = await context.cookies();
  const cookie = cookies.find(item => item.name === 'securepulse_dashboard');
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe('Strict');
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'New test residence', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
});

test('property switching replaces cameras, incidents and details; delayed responses cannot restore previous property data', async ({ page }) => {
  await signIn(page);
  await page.getByRole('button', { name: /^Incidents \(/ }).click();
  await expect(page.getByRole('button', { name: /#1 · NORTH INTRUSION/ })).toBeVisible();
  await page.getByRole('button', { name: /#1 · NORTH INTRUSION/ }).click();
  await expect(page.getByRole('heading', { name: 'Camera incident #1', exact: true })).toBeVisible();
  await page.route('**/dashboard/properties/1/cases?**', async route => {
    const response = await route.fetch();
    await new Promise(resolve => setTimeout(resolve, 800));
    await route.fulfill({ response }).catch(() => {});
  });
  await page.getByRole('button', { name: 'Refresh incidents' }).click();
  await page.getByLabel('Select property').selectOption('2');
  await expect(page.getByRole('heading', { name: 'South office', exact: true })).toBeVisible();
  await page.getByRole('button', { name: /^Incidents \(/ }).click();
  await expect(page.getByRole('button', { name: /#2 · SOUTH LOITERING/ })).toBeVisible();
  await page.waitForTimeout(1000);
  await expect(page.getByRole('button', { name: /NORTH INTRUSION/ })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Camera incident #1', exact: true })).toHaveCount(0);
  const denied = await page.request.get('/api/v1/dashboard/properties/2/incidents/1');
  expect(denied.status()).toBe(404);
  expect((await page.request.get('/api/v1/dashboard/properties/3/incidents')).status()).toBe(403);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'South office', exact: true })).toBeVisible();
});

test('incident actions update durable history, counts, filters and authenticated evidence', async ({ page }) => {
  await signIn(page);
  await page.getByRole('button', { name: /^Incidents \(/ }).click();
  await page.getByRole('button', { name: /#1 · NORTH INTRUSION/ }).click();
  await page.getByRole('button', { name: 'View evidence', exact: true }).click();
  const image = page.getByAltText('Incident evidence 1');
  await expect(image).toBeVisible();
  await expect.poll(() => image.evaluate((item: HTMLImageElement) => item.naturalWidth)).toBeGreaterThan(0);
  await page.getByLabel('Action', { exact: true }).selectOption('acknowledge');
  await expect(page.getByRole('button', { name: 'Confirm action' })).toBeDisabled();
  await page.getByLabel('Reason', { exact: true }).fill('Reviewed camera evidence');
  await page.getByRole('button', { name: 'Confirm action' }).click();
  await expect(page.getByText('Incident updated to ACKNOWLEDGED.')).toBeVisible();
  await expect(page.getByText('OPEN → ACKNOWLEDGED')).toBeVisible();
  await page.getByLabel('Action', { exact: true }).selectOption('resolve');
  await page.getByLabel('Reason', { exact: true }).fill('Situation checked and resolved');
  await page.getByRole('button', { name: 'Confirm action' }).click();
  await expect(page.getByText('ACKNOWLEDGED → RESOLVED')).toBeVisible();
  await page.getByLabel('Status', { exact: true }).selectOption('OPEN');
  await expect(page.getByText('No incidents match these filters.')).toBeVisible();
  await page.reload();
  await page.getByRole('button', { name: /^Incidents \(/ }).click();
  await page.getByRole('button', { name: /#1 · NORTH INTRUSION/ }).click();
  await expect(page.getByText('ACKNOWLEDGED → RESOLVED')).toBeVisible();
});

test('read-only membership cannot change incidents and revoked sessions return to sign-in', async ({ page }) => {
  await signIn(page, 'reader@example.test');
  await page.getByRole('button', { name: /^Incidents \(/ }).click();
  await page.getByRole('button', { name: /#1 · NORTH INTRUSION/ }).click();
  await expect(page.getByText('You have read-only access to this property.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Confirm action' })).toHaveCount(0);
  const response = await page.request.post('/api/v1/dashboard/properties/1/incidents/1/commands', {
    headers: { 'X-Dashboard-Request': '1' }, data: { command: 'reopen', reason: 'Forbidden attempt', correlation_id: 'reader-attempt' },
  });
  expect(response.status()).toBe(403);
  await page.request.post('/api/v1/dashboard/auth/logout', { headers: { 'X-Dashboard-Request': '1' } });
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible({ timeout: 20000 });
  await expect(page.getByLabel('Select property')).toHaveCount(0);
});

test('existing owner can add a property without inheriting cameras or incidents', async ({ page }) => {
  await signIn(page);
  await page.getByRole('button', { name: 'Add property', exact: true }).click();
  await page.getByLabel('Property name', { exact: true }).fill('Additional property');
  await page.getByLabel('Property address', { exact: true }).fill('55 Additional Road');
  await page.getByRole('button', { name: 'Save property', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Additional property', exact: true })).toBeVisible();
  await expect(page.getByText('No cameras are configured.')).toBeVisible();
  await page.getByRole('button', { name: /^Incidents \(/ }).click();
  await expect(page.getByText('0 matching incidents')).toBeVisible();
  await page.getByLabel('Select property').selectOption('1');
  await expect(page.getByRole('heading', { name: 'North residence', exact: true })).toBeVisible();
});

test('mobile reports stream into the operator queue with evidence, actions and marshal progress', async ({ page }) => {
  await signIn(page);
  await page.getByRole('button', { name: /^Incidents \(/ }).click();
  const login = await page.request.post('/api/v1/auth/login', { data: { email: 'reader@example.test', password } });
  const bearer = { Authorization: `Bearer ${(await login.json()).access_token}` };
  const created = await page.request.post('/api/v1/reporter/incidents', {
    headers: { ...bearer, 'X-Idempotency-Key': 'browser-mobile-report' },
    data: { property_id: 1, incident_type: 'THEFT', address: '11 North Street', description: 'Package taken at entrance' },
  });
  expect(created.status()).toBe(201);
  const report = await created.json();
  const uploaded = await page.request.post(`/api/v1/reporter/incidents/${report.id}/evidence`, {
    headers: bearer, multipart: { file: { name: 'mobile-evidence.png', mimeType: 'image/png',
      buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64') } },
  });
  expect(uploaded.status()).toBe(200);
  // No refresh click: creation/upload events must refresh the selected property.
  await page.getByRole('button', { name: new RegExp(`#${report.id} · THEFT`) }).click();
  await expect(page.getByRole('heading', { name: `Reported incident #${report.id}`, exact: true })).toBeVisible();
  await expect(page.getByText('Package taken at entrance', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'View evidence', exact: true }).click();
  const evidenceId = (await uploaded.json()).evidence[0].id;
  await expect.poll(() => page.getByAltText(`Incident evidence ${evidenceId}`).evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
  await page.getByLabel('Action', { exact: true }).selectOption('acknowledge');
  await page.getByLabel('Reason', { exact: true }).fill('Reviewing mobile report evidence');
  await page.getByRole('button', { name: 'Confirm action' }).click();
  await expect(page.getByText('Incident updated to ACKNOWLEDGED.')).toBeVisible();
  await page.getByRole('button', { name: 'Offer assignment', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Cancel assignment', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Cancel assignment', exact: true }).click();
  await expect(page.getByText('Assignment cancelled.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Offer assignment', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Cancel assignment', exact: true })).toBeVisible();
  const detail = await (await page.request.get(`/api/v1/reporter/incidents/${report.id}`, { headers: bearer })).json();
  let assignment = { id: detail.dispatch.assignment_id, version: detail.dispatch.version };
  const marshalLogin = await page.request.post('/api/v1/auth/login', { data: { email: 'marshal@example.test', password } });
  const marshalHeaders = { Authorization: `Bearer ${(await marshalLogin.json()).access_token}` };
  for (const status of ['ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'COMPLETED']) {
    const response = await page.request.post(`/api/v1/dispatch/offers/${assignment.id}/${status === 'ACCEPTED' ? 'accept' : 'progress'}`, {
      headers: marshalHeaders, data: { expected_version: assignment.version, ...(status === 'ACCEPTED' ? {} : { status }) },
    });
    expect(response.status()).toBe(200); assignment = await response.json();
  }
  await expect(page.getByText(/Assignment #\d+ · COMPLETED · Marshal #1/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Cancel assignment', exact: true })).toHaveCount(0);
  expect((await (await page.request.get(`/api/v1/reporter/incidents/${report.id}`, { headers: bearer })).json()).status).toBe('RESOLVED');
});
