import { defineConfig, devices } from '@playwright/test'

/** End-to-end tests against the real API and the Vite dev server.
 *  E2E_PYTHON points at the backend interpreter (CI: python; locally e.g. ../backend/.venv/Scripts/python). */
const python = process.env.E2E_PYTHON ?? 'python'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  // reducedMotion: axe must measure settled colours, not elements mid fade-in
  use: { baseURL: 'http://localhost:5173', trace: 'retain-on-failure', reducedMotion: 'reduce' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
  webServer: [
    {
      command: `"${python}" -m uvicorn app.main:app --port 8000`,
      cwd: '../backend',
      url: 'http://127.0.0.1:8000/v1/ready',
      env: { PUBMED_LIVE: 'false', PYTHON_DOTENV_DISABLED: '1', RATE_LIMIT_PER_MINUTE: '0', AUDIT_LOG: 'false' },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    { command: 'npm run dev -- --port 5173 --strictPort', url: 'http://localhost:5173', reuseExistingServer: !process.env.CI, timeout: 60_000 },
  ],
})
