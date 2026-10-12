export type Risk = {
  key: 'heart' | 'diabetes'; disease: string; available: boolean; model: string; target: string
  probability?: number; level?: 'low' | 'moderate' | 'high'; label?: string; message?: string; caveat?: string
  drivers?: { feature: string; effect: 'raises' | 'lowers'; magnitude: number }[]; imputed?: string[]
  metrics?: { holdout_accuracy: number; holdout_roc_auc: number; cv_roc_auc_mean: number; rows: number }
}
export type Evidence = { id: string; title: string; source: string; text: string; url: string; relevance: number | null; kind?: 'guideline' | 'pubmed' }
export type Condition = { condition: string; score: number; likelihood: string; supporting_findings: string[]; evidence_ids: string[] }
export type Lab = { test: string; value: number; unit: string; reference: string | null; flag: 'high' | 'low' | 'normal' | 'borderline' | 'n/a' }
export type Action = { action: string; rationale: string; evidence_ids: string[] }
export type TraceStep = { step: string; tools: string[]; detail: string; ms: number }
export type Result = {
  summary: string; llm_used: boolean; llm_errors?: string[]; possible_conditions: Condition[]; symptoms: string[]; conditions: string[]
  medications: string[]; risk_factors: string[]; vitals: Record<string, number>; risks: Risk[]; labs: Lab[]
  risk_score: { value: number; level: string; disease: string } | null; urgent_attention: boolean
  recommended_actions: Action[]; evidence: Evidence[]; agent_trace: TraceStep[]; disclaimer: string
  extracted_text?: string; document_name?: string | null; input_modality?: string; image_note?: string | null
}
export type Message = { role: 'assistant' | 'user'; content: string; evidence?: Evidence[] }
export type Health = { status: string; llm_enabled: boolean; vector_store: string; embeddings: string; pubmed_live: boolean; evidence_documents: number; models: Record<string, boolean> }
