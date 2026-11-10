import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem('clarity.consent.v1', 'yes'))
})

/** WCAG 2.1 A/AA checks. Fails on serious or critical violations. */
async function expectAccessible(page: Page, label: string) {
  // measure settled colours: let any fade-in finish before axe samples contrast
  await page.waitForFunction(() => document.getAnimations().every(a => a.playState !== 'running'))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter(v => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map(v => `${v.id}: ${v.help} (${v.nodes.length}) e.g. ${v.nodes[0]?.target} - ${v.nodes[0]?.any[0]?.message ?? ''}`), label).toEqual([])
}

async function expectNoHorizontalScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
}

test('intended-use gate blocks the app until acknowledged', async ({ page, context }) => {
  await context.clearCookies()
  await page.addInitScript(() => sessionStorage.removeItem('clarity.consent.v1'))
  await page.goto('/')
  const go = page.getByRole('button', { name: 'Continue' })
  await expect(go).toBeDisabled()
  await expectAccessible(page, 'consent gate')
  await page.getByRole('checkbox').check()
  await go.click()
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Clinical notes in.')
})

test('landing is accessible in light and dark themes, without horizontal scroll', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('[data-conn="online"]')).toBeVisible({ timeout: 15_000 })
  await expectAccessible(page, 'landing light')
  await expectNoHorizontalScroll(page)
  await page.getByRole('button', { name: /dark theme/ }).click()
  await expect(page.locator('html')).toHaveClass(/dark/)
  await expectAccessible(page, 'landing dark')
})

test('deteriorating-patient case: urgent triage, scores, explainability, evidence', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('[data-conn="online"]')).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: /Run the deteriorating-patient case/ }).click()

  const alert = page.getByRole('alert').filter({ hasText: 'Urgent attention signal' })
  await expect(alert).toContainText('Low oxygen saturation (SpO2 90%)')
  await expect(alert).toContainText('qSOFA 3')
  await expect(page.getByText('Sepsis / serious infection', { exact: true })).toBeVisible()
  await expect(page.getByText(/Medication safety: metformin/)).toBeVisible()
  await expect(page.getByText('Offline demo.')).toHaveCount(0)            // a live result, not the fallback
  await expectAccessible(page, 'overview')
  await expectNoHorizontalScroll(page)

  await page.getByRole('tab', { name: /Scores/ }).click()
  await expect(page.getByRole('table', { name: /NEWS2 points/ })).toContainText('new confusion / CVPU')
  await expectAccessible(page, 'scores')

  await page.getByRole('tab', { name: /Explain/ }).click()
  const negated = page.locator('mark', { hasText: 'chest pain' })
  await expect(negated).toHaveClass(/line-through/)
  await negated.click()   // tap works on touch screens, where there is no hover
  await expect(page.getByText(/Excluded: negated \(negation: 'Denies'\)/)).toBeVisible()
  await expectAccessible(page, 'explain')

  await page.getByRole('tab', { name: /Evidence/ }).click()
  await expect(page.locator('article', { hasText: 'Sepsis-3' })).toBeVisible()
})

test('own note via keyboard shortcut, shorthand understood, FHIR bundle built', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('[data-conn="online"]')).toBeVisible({ timeout: 15_000 })
  const notes = page.getByLabel('Symptoms, history and findings')
  await notes.fill('Pt c/o CP and SOB. Mother had MI. Denies fever. BP 150/95, HR 104, SpO2 94% on room air.')
  await notes.press('Control+Enter')
  await expect(page.getByRole('alert').filter({ hasText: 'Urgent attention signal' })).toContainText("'chest pain'")

  await page.getByRole('tab', { name: /Explain/ }).click()
  await expect(page.locator('mark', { hasText: 'MI' })).toHaveClass(/line-through/)        // relative, not the patient
  await expect(page.locator('mark', { hasText: 'SOB' })).not.toHaveClass(/line-through/)

  await page.getByRole('tab', { name: /Export/ }).click()
  await page.getByRole('button', { name: 'Build FHIR bundle' }).click()
  await expect(page.getByText(/Observation × \d+/)).toBeVisible()
  await expect(page.getByText(/DetectedIssue × 1/)).toBeVisible()
})

test('model cards dialog shows calibration and closes on Escape', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /Model cards & calibration/ }).click()
  const dialog = page.getByRole('dialog', { name: 'Model cards' })
  await expect(dialog.getByRole('img', { name: /Reliability diagram/ }).first()).toBeVisible()
  await expectAccessible(page, 'model cards')
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
})

test('server asleep: waking banner and a clearly labelled offline demo', async ({ page }) => {
  await page.route('**/v1/**', route => route.abort())
  await page.goto('/')
  await expect(page.getByText(/Waking the analysis server/)).toBeVisible({ timeout: 15_000 })
  await page.locator('[data-sample="ed-shorthand"]').click()
  await expect(page.getByText('Offline demo.')).toBeVisible()
  await expect(page.getByLabel(/^Review:/)).toHaveCount(0)                  // no audit-trail actions on canned output
  await expect(page.getByText('Acute coronary syndrome / ischaemic heart disease', { exact: true })).toBeVisible()
})
