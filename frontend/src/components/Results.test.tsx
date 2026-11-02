import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { Result } from '../types'
import Consent from './Consent'
import Results from './Results'

const base: Result = {
  summary: 'Rules summary.', llm_used: false, possible_conditions: [], symptoms: [], conditions: [], medications: [], risk_factors: [],
  vitals: {}, risks: [], labs: [], risk_score: null, urgent_attention: false, recommended_actions: [], evidence: [], agent_trace: [],
  disclaimer: 'Prototype.', request_id: 'req-abcdef12',
}

afterEach(cleanup)

describe('Results', () => {
  it('lists every urgent reason', () => {
    render(<Results busy={false} result={{ ...base, urgent_attention: true, urgent_reasons: ['Low oxygen saturation (SpO2 86%)', 'qSOFA 3 (≥2: assess for sepsis)'] }} />)
    expect(screen.getByText(/Urgent attention signal/)).toBeTruthy()
    expect(screen.getByText('Low oxygen saturation (SpO2 86%)')).toBeTruthy()
    expect(screen.getByText(/qSOFA 3/)).toBeTruthy()
  })

  it('shows an incomplete NEWS2 as a lower bound', () => {
    const scores = {
      news2: { name: 'NEWS2', score: 5, risk: 'medium' as const, response: 'Urgent review.', components: { heart_rate: 3, spo2: 2 }, complete: false,
               missing: ['temperature'], note: 'Incomplete: temperature not documented, so 5 is a lower bound.', reference: '' },
      qsofa: { name: 'qSOFA', score: 0, positive: false, components: {}, complete: false, missing: [], interpretation: 'Below threshold.', note: null, reference: '' },
    }
    render(<Results busy={false} result={{ ...base, scores }} />)
    expect(screen.getByTitle('Incomplete: lower bound')).toBeTruthy()
    expect(screen.getByText(/5 is a lower bound/)).toBeTruthy()
  })

  it('warns when a model input is outside the training range', () => {
    const risk = { key: 'diabetes' as const, disease: 'Diabetes', available: true, model: 'LR', target: 't', probability: 0.8, level: 'high' as const,
                   reliability: 'low' as const, out_of_range: ['BMI=95 (trained on 18.2-67.1)'] }
    render(<Results busy={false} result={{ ...base, risks: [risk] }} />)
    expect(screen.getByText(/Low reliability/)).toBeTruthy()
    expect(screen.getByText(/BMI=95/)).toBeTruthy()
  })

  it('explains when the LLM was skipped for suspected prompt injection', () => {
    render(<Results busy={false} result={{ ...base, guardrails: { input_flags: ["Possible prompt injection: 'ignore all previous instructions'"], llm_skipped: true } }} />)
    expect(screen.getByText(/looks like instructions to an AI model/)).toBeTruthy()
  })

  it('offers clinician review controls tied to the request id', () => {
    const c = { condition: 'Hypertension', score: 2, likelihood: 'possible', supporting_findings: ['BP ≥130/80 mmHg'], evidence_ids: [] }
    render(<Results busy={false} result={{ ...base, possible_conditions: [c] }} />)
    expect(screen.getByLabelText('Review: Hypertension')).toBeTruthy()
  })
})

describe('Consent gate', () => {
  it('blocks the app until the intended use is acknowledged', () => {
    sessionStorage.clear()
    render(<Consent><p>app content</p></Consent>)
    expect(screen.queryByText('app content')).toBeNull()
    const button = screen.getByRole('button', { name: 'Continue' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(button)
    expect(screen.getByText('app content')).toBeTruthy()
  })
})
