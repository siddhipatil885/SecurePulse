import { spawn, type ChildProcess } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { once } from 'node:events';
import { afterAll, beforeAll, expect, it } from 'vitest';
import { createApi } from '../src/api/client';

// Runs the real mobile HTTP client against an isolated FastAPI process and
// temporary database/media directory. No deployment credentials are loaded.
const backend = fileURLToPath(new URL('../../../backend', import.meta.url));
const base = 'http://127.0.0.1:18082';
const password = 'Dashboard-test-pass123';
let server: ChildProcess;
let output = '';
beforeAll(async () => {
  const python = process.env.DASHBOARD_TEST_PYTHON ?? `${backend}/.venv/${process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'}`;
  server = spawn(python, ['-m', 'uvicorn', 'dashboard_test_server:app', '--app-dir', 'tests', '--host', '127.0.0.1', '--port', '18082'], {
    cwd: backend, env: { ...process.env, PYTHONPATH: backend }, stdio: ['ignore', 'pipe', 'pipe'],
  });
  server.on('error', error => { output += error.message; });
  for (const stream of [server.stdout, server.stderr]) stream?.on('data', value => { output = (output + value).slice(-6000); });
  for (let attempt = 0; attempt < 100; attempt++) {
    if (server.exitCode !== null) throw new Error(`Test backend exited: ${output}`);
    try { if ((await fetch(`${base}/health`)).ok) return; } catch { /* startup */ }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Test backend did not start: ${output}`);
}, 15000);
afterAll(async () => {
  if (server?.exitCode === null) { const ended = once(server, 'exit'); server.kill('SIGTERM'); await ended; }
});

it('integrates mobile sessions, reports, evidence, dashboard dispatch and marshal completion', async () => {
  let token: string | null = null;
  const api = createApi(base, () => token, () => { token = null; });
  token = (await api.login('reader@example.test', password)).access_token;
  expect((await api.profile()).properties).toEqual([{ id: 1, name: 'North residence', role: 'reporter' }]);
  expect((await api.cameras(1))[0]?.id).toBe(1);
  await expect(api.cameras(2)).rejects.toMatchObject({ status: 403 });
  await expect(api.createIncident({ property_id: 2, incident_type: 'THEFT', address: 'Forbidden site' }, 'integration-forbidden')).rejects.toMatchObject({ status: 403 });
  expect((await api.updateProfile('Mobile integration reporter')).name).toBe('Mobile integration reporter');
  expect((await api.updateNotificationPreference('DISPATCH_UPDATES', false)).enabled).toBe(false);
  expect((await api.notificationPreferences()).find(item => item.category === 'DISPATCH_UPDATES')?.enabled).toBe(false);
  const draft = { property_id: 1, incident_type: 'THEFT', address: '11 North Street', description: 'Mobile integration report' };
  const report = await api.createIncident(draft, 'integration-report-key');
  expect((await api.createIncident(draft, 'integration-report-key')).id).toBe(report.id);
  await expect(api.createIncident({ ...draft, address: 'Different address' }, 'integration-report-key')).rejects.toMatchObject({ status: 409 });
  const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64');
  const upload = async () => {
    const form = new FormData(); form.append('file', new Blob([image], { type: 'image/png' }), 'incident.png');
    const response = await fetch(`${base}/api/v1/reporter/incidents/${report.id}/evidence`, {
      method: 'POST', headers: { Authorization: `Bearer ${token}`, 'X-Idempotency-Key': 'integration-upload-key' }, body: form,
    });
    expect(response.status).toBe(200); return response.json();
  };
  const uploaded = await upload();
  expect((await upload()).evidence).toHaveLength(1);
  const grant = await api.reporterEvidenceAccess(report.id, uploaded.evidence[0].id);
  expect((await fetch(base + grant.url)).status).toBe(401);
  const media = await fetch(base + grant.url, { headers: { Authorization: `Bearer ${token}` } });
  expect(media.status).toBe(200); expect(Buffer.from(await media.arrayBuffer())).toEqual(image);

  const login = await fetch(`${base}/api/v1/dashboard/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Dashboard-Request': '1' },
    body: JSON.stringify({ email: 'owner@example.test', password }),
  });
  expect(login.status).toBe(200);
  const cookie = login.headers.get('set-cookie')!.split(';')[0]!;
  const casePath = `${base}/api/v1/dashboard/properties/1/cases/reporter/${report.id}`;
  expect((await (await fetch(casePath, { headers: { Cookie: cookie } })).json()).location.address).toBe(draft.address);
  const offered = await fetch(casePath + '/offers', { method: 'POST',
    headers: { Cookie: cookie, 'Content-Type': 'application/json', 'X-Dashboard-Request': '1' },
    body: JSON.stringify({ marshal_profile_id: 1, expires_in_seconds: 60, idempotency_key: 'integration-offer-key' }),
  });
  expect(offered.status).toBe(201); let assignment = await offered.json();
  expect((await api.incidents(1, { has_active_assignment: 'true' })).items.map(item => item.id)).toContain(report.id);
  const marshal = createApi(base, () => null, () => {});
  const marshalToken = (await marshal.login('marshal@example.test', password)).access_token;
  // A real mixed-role response must parse even though the reporter app only
  // permits selecting memberships with report access.
  expect((await marshal.profile(marshalToken)).properties[0]?.role).toBe('marshal');
  for (const status of ['ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'COMPLETED']) {
    const response = await fetch(`${base}/api/v1/dispatch/offers/${assignment.id}/${status === 'ACCEPTED' ? 'accept' : 'progress'}`, {
      method: 'POST', headers: { Authorization: `Bearer ${marshalToken}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_version: assignment.version, ...(status === 'ACCEPTED' ? {} : { status }) }),
    });
    expect(response.status, await response.clone().text()).toBe(200); assignment = await response.json();
  }
  const resolved = await api.incident(report.id);
  expect(resolved.status).toBe('RESOLVED'); expect(resolved.dispatch?.status).toBe('COMPLETED');
  expect((await (await fetch(casePath, { headers: { Cookie: cookie } })).json()).status).toBe('RESOLVED');
  expect(resolved.timeline.some(item => item.status === 'RESOLVED')).toBe(true);
  await expect(api.changePassword('wrong-password', 'Replacement-test-pass123')).rejects.toMatchObject({ status: 400 });
  expect(token).not.toBeNull();
  await api.changePassword(password, 'Replacement-test-pass123');
  await expect(api.profile()).rejects.toMatchObject({ status: 401 });
  token = (await api.login('reader@example.test', 'Replacement-test-pass123')).access_token;
  await api.logout(token);
  await expect(api.profile()).rejects.toMatchObject({ status: 401 });
}, 20000);
