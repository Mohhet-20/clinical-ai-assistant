import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import demo from '../demo-results.json'
import samples from '../samples.json'
import type { Annotation, Result } from '../types'
import Explain from './Explain'
import Results from './Results'

afterEach(cleanup)

const TEXT = 'Name: Ravi Kumar. Denies fever but reports cough. BP 150/95.'
const ANN: Annotation[] = [
  { start: 6, end: 16, kind: 'phi', label: 'NAME' },
  { start: 25, end: 30, kind: 'finding', label: 'Fever', category: 'symptom', status: 'negated', reason: "negation: 'Denies'" },
  { start: 43, end: 48, kind: 'finding', label: 'Cough', category: 'symptom', status: 'affirmed', reason: null },
  { start: 50, end: 59, kind: 'measurement', label: 'BP 150/95' },
]

describe('Explain', () => {
  it('renders the note verbatim with every decision marked', () => {
    const { container } = render(<Explain text={TEXT} annotations={ANN} />)
    expect(container.querySelector('.whitespace-pre-wrap')!.textContent).toBe(TEXT.replace('Ravi Kumar', 'NAMERavi Kumar'))
    expect(screen.getByLabelText('redacted NAME')).toBeTruthy()
    expect(screen.getByText('fever').className).toMatch(/line-through/)
    expect(screen.getByText('cough').className).not.toMatch(/line-through/)
  })

  it('explains a highlight on hover and on keyboard focus', () => {
    render(<Explain text={TEXT} annotations={ANN} />)
    fireEvent.focus(screen.getByText('fever'))
    expect(screen.getByText(/Excluded: negated \(negation: 'Denies'\)/)).toBeTruthy()
    fireEvent.mouseEnter(screen.getByText('cough'))
    expect(screen.getByText(/Cough · Symptom · Counted as present/)).toBeTruthy()
  })

  it('counts findings, exclusions, measurements and identifiers', () => {
    render(<Explain text={TEXT} annotations={ANN} />)
    for (const label of ['Findings counted', 'Findings excluded', 'Measurements', 'Identifiers redacted']) expect(screen.getByText(label)).toBeTruthy()
  })
})

describe('offline demo results', () => {
  const results = demo as unknown as Record<string, Result>

  it('exist for every sample and were generated from the current sample text', () => {
    for (const s of samples) {
      expect(results[s.id], `missing demo for ${s.id}: run backend/export_demo.py`).toBeTruthy()
      expect(results[s.id].analyzed_text, `stale demo for ${s.id}: run backend/export_demo.py`).toBe(s.text)
    }
  })

  it('are labelled as offline demos and never offer audit-trail reviews', () => {
    render(<Results busy={false} result={{ ...results.sepsis, demo: true }} />)
    expect(screen.getByText(/Offline demo\./)).toBeTruthy()
    expect(screen.queryByLabelText(/^Review:/)).toBeNull()
    expect(screen.getByText('Urgent attention signal')).toBeTruthy()
  })

  it('tabs are keyboard navigable', () => {
    render(<Results busy={false} result={{ ...results.sepsis, demo: true }} />)
    const overview = screen.getByRole('tab', { name: /Overview/ })
    fireEvent.keyDown(overview, { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: /Explain/ }).getAttribute('aria-selected')).toBe('true')
    expect(screen.getByText('Findings counted')).toBeTruthy()
    fireEvent.keyDown(screen.getByRole('tab', { name: /Explain/ }), { key: 'ArrowLeft' })
    expect(overview.getAttribute('aria-selected')).toBe('true')
  })
})

describe('Explain on touch screens', () => {
  it('a tap pins the explanation so it survives the pointer leaving', () => {
    render(<Explain text={TEXT} annotations={ANN} />)
    const fever = screen.getByText('fever')
    fireEvent.click(fever)
    fireEvent.mouseLeave(fever)
    expect(screen.getByText(/Excluded: negated/)).toBeTruthy()
  })
})
