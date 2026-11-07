import { defineConfig } from '@playwright/test';

const python = process.env.DASHBOARD_TEST_PYTHON ?? (process.platform === 'win32' ? '../.venv/Scripts/python.exe' : '../.venv/bin/python');

export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  use: { baseURL: 'http://127.0.0.1:15173', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium', ...(process.env.PLAYWRIGHT_CHROME_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHROME_CHANNEL } : {}) } },
    { name: 'webkit', use: { browserName: 'webkit' } },
  ],
  webServer: [
    { command: `"${python}" -m uvicorn dashboard_test_server:app --app-dir ../tests --host 127.0.0.1 --port 18081`,
      env: { PYTHONPATH: '..' }, url: 'http://127.0.0.1:18081/health', reuseExistingServer: false },
    { command: 'npm run dev -- --host 127.0.0.1 --port 15173 --strictPort',
      env: { VITE_BACKEND_URL: 'http://127.0.0.1:18081' }, url: 'http://127.0.0.1:15173', reuseExistingServer: false },
  ],
});
