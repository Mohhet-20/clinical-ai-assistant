export type Metrics = {
  holdout_accuracy: number; holdout_roc_auc: number; cv_roc_auc_mean: number; rows: number
  holdout_sensitivity?: number | null; holdout_specificity?: number | null; holdout_brier?: number
}
export type Risk = {
  key: 'heart' | 'diabetes'; disease: string; available: boolean; model: string; target: string
  probability?: number; level?: 'low' | 'moderate' | 'high'; label?: string; message?: string; caveat?: string
  drivers?: { feature: string; effect: 'raises' | 'lowers'; magnitude: number }[]; imputed?: string[]
  out_of_range?: string[]; reliability?: 'standard' | 'low'; version?: string; metrics?: Metrics
}
export type Evidence = { id: string; title: string; source: string; text: string; url: string; relevance: number | null; kind?: 'guideline' | 'pubmed' }
export type Condition = { condition: string; score: number; likelihood: string; supporting_findings: string[]; evidence_ids: string[] }
export type Lab = { test: string; value: number; unit: string; reference: string | null; flag: 'high' | 'low' | 'normal' | 'borderline' | 'n/a' }
export type Action = { action: string; rationale: string; evidence_ids: string[] }
export type TraceStep = { step: string; tools: string[]; detail: string; ms: number }
export type Privacy = { phi_redacted: number; categories: string[]; note: string }
export type Provenance = { service_version: string; pipeline: string; models: Record<string, string | null>; retrieval: string; evidence_corpus: string; llm: string | null }
export type Result = {
  summary: string; llm_used: boolean; llm_errors?: string[]; possible_conditions: Condition[]; symptoms: string[]; conditions: string[]
  medications: string[]; risk_factors: string[]; vitals: Record<string, number>; risks: Risk[]; labs: Lab[]
  risk_score: { value: number; level: string; disease: string } | null; urgent_attention: boolean; urgent_reasons?: string[]
  recommended_actions: Action[]; evidence: Evidence[]; agent_trace: TraceStep[]; disclaimer: string
  privacy?: Privacy; provenance?: Provenance; request_id?: string; case_id?: string | null
  scores?: Scores; medication_details?: MedicationDetail[]; allergies?: Allergies; guardrails?: Guardrails
  analyzed_text?: string; annotations?: Annotation[]; demo?: boolean
  extracted_text?: string; document_name?: string | null; input_modality?: string; image_note?: string | null
}
export type Message = { role: 'assistant' | 'user'; content: string; evidence?: Evidence[] }
export type Health = {
  status: string; version?: string; llm_enabled: boolean; vector_store: string; embeddings: string; pubmed_live: boolean
  evidence_documents: number; models: Record<string, boolean>; auth?: string; audit_log?: boolean; phi_redaction?: boolean; case_store?: boolean
}
export type Verdict = 'agree' | 'disagree' | 'unsure'
export type Feedback = { request_id: string; target: 'summary' | 'condition' | 'action' | 'risk' | 'extraction' | 'evidence' | 'chat'; item: string; verdict: Verdict; comment?: string }

export type ScoreParts = Record<string, number>
export type News2 = { name: string; score: number; risk: 'low' | 'low-medium' | 'medium' | 'high'; response: string; components: ScoreParts; complete: boolean; missing: string[]; note: string | null; reference: string }
export type Qsofa = { name: string; score: number; positive: boolean; components: ScoreParts; complete: boolean; missing: string[]; interpretation: string; note: string | null; reference: string }
export type Egfr = { name: string; value: number | null; unit?: string; stage?: string; complete: boolean; missing: string[]; interpretation?: string; note?: string; reference?: string }
export type Scores = { news2: News2; qsofa: Qsofa; egfr?: Egfr }
export type MedicationDetail = { name: string; dose: number | null; unit: string | null; frequency: string | null }
export type Allergies = { status: 'nkda' | 'documented' | 'not documented'; items: string[] }
export type Guardrails = { input_flags: string[]; llm_skipped: boolean; summary_check?: { rejected: boolean; unknown_citations_removed: string[]; uncited: boolean } | null }
export type AuthConfig = { mode: string; oidc: { issuer: string; client_id: string | null; scope: string } | null }
export type Me = { actor: string; role: 'clinician' | 'admin'; name: string | null }
export type CaseSummary = { id: string; owner: string; created: number; expires: number; modality: string | null; conditions: string[]; urgent: boolean; news2: number | null }
export type CaseDetail = CaseSummary & { result: Result | null; error?: string }
export type Annotation = {
  start: number; end: number; kind: 'finding' | 'measurement' | 'phi'; label: string
  category?: string; status?: 'affirmed' | 'negated' | 'family' | 'ignored'; reason?: string | null; expanded?: string
}
export type ModelCard = {
  label: string; available: boolean; model: string; target: string; features: string[]; version: string | null; trained: string | null; data_sha256: string | null
  metrics: (Metrics & { cv_roc_auc_std?: number; holdout_rows?: number; positive_rate?: number; holdout_ece?: number
    calibration_table?: { bin: string; n: number; mean_predicted: number; observed_rate: number }[] }) | null
  card: { intended_use: string; out_of_scope: string[]; population: string; limitations: string[] }
}
