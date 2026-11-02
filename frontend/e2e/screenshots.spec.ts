import { expect, test, type Page } from '@playwright/test'

/** README screenshots. Skipped in normal runs; regenerate with:  npm run screenshots */
test.skip(!process.env.SCREENSHOTS, 'set SCREENSHOTS=1 to regenerate docs/screenshots')
test.use({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 })

const OUT = '../docs/screenshots'

async function open(page: Page, scheme: 'light' | 'dark') {
  await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' })
  await page.addInitScript(() => sessionStorage.setItem('clarity.consent.v1', 'yes'))
  await page.goto('/')
  await expect(page.locator('[data-conn="online"]')).toBeVisible({ timeout: 15_000 })
}

async function runSample(page: Page, id: string) {
  await page.locator(`[data-sample="${id}"]`).click()
  await expect(page.getByRole('tab', { name: /Overview/ })).toBeVisible()
  await page.evaluate(() => window.scrollTo(0, 0))
}

const results = (page: Page) => page.locator('section.card').filter({ has: page.getByRole('tablist') })

test('landing', async ({ page, browserName }, info) => {
  test.skip(info.project.name !== 'desktop' || browserName !== 'chromium')
  await open(page, 'light')
  await page.screenshot({ path: `${OUT}/landing.png` })
})

test('overview and tabs', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop')
  await open(page, 'light')
  await runSample(page, 'sepsis')
  await page.screenshot({ path: `${OUT}/overview.png`, clip: { x: 0, y: 0, width: 1440, height: 1180 }, fullPage: true })

  await open(page, 'dark')
  await runSample(page, 'ed-shorthand')
  await page.getByRole('tab', { name: /Explain/ }).click()
  await page.locator('mark', { hasText: /^MI/ }).click()
  await results(page).screenshot({ path: `${OUT}/explain-dark.png` })

  await runSample(page, 'sepsis')
  await page.getByRole('tab', { name: /Scores/ }).click()
  await results(page).screenshot({ path: `${OUT}/scores-dark.png` })
})

test('model cards', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop')
  await open(page, 'light')
  await page.getByRole('button', { name: /Model cards & calibration/ }).click()
  const dialog = page.getByRole('dialog', { name: 'Model cards' })
  await expect(dialog.getByRole('img', { name: /Reliability diagram/ }).first()).toBeVisible()
  await dialog.locator('article').nth(1).screenshot({ path: `${OUT}/model-card.png` })
})

test('mobile', async ({ page }, info) => {
  test.skip(info.project.name !== 'mobile')
  await open(page, 'light')
  await runSample(page, 'sepsis')
  await results(page).scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${OUT}/mobile.png` })
})
