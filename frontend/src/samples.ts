export const HEART_FIELDS: { key: string; hint: string }[] = [
  { key: 'age', hint: 'years' }, { key: 'sex', hint: '1 male, 0 female' }, { key: 'cp', hint: 'chest pain type 1–4' },
  { key: 'trestbps', hint: 'resting BP mmHg' }, { key: 'chol', hint: 'cholesterol mg/dL' }, { key: 'fbs', hint: 'fasting sugar >120: 1/0' },
  { key: 'restecg', hint: 'rest ECG 0–2' }, { key: 'thalach', hint: 'max heart rate' }, { key: 'exang', hint: 'exercise angina 1/0' },
  { key: 'oldpeak', hint: 'ST depression' }, { key: 'slope', hint: 'ST slope 1–3' }, { key: 'ca', hint: 'vessels 0–3' }, { key: 'thal', hint: '3 normal, 6 fixed, 7 reversible' },
]
export const DIABETES_FIELDS: { key: string; hint: string }[] = [
  { key: 'Pregnancies', hint: 'count' }, { key: 'Glucose', hint: 'mg/dL' }, { key: 'BloodPressure', hint: 'diastolic mmHg' },
  { key: 'SkinThickness', hint: 'mm' }, { key: 'Insulin', hint: 'µU/mL' }, { key: 'BMI', hint: 'kg/m²' },
  { key: 'DiabetesPedigreeFunction', hint: 'family-risk score' }, { key: 'Age', hint: 'years' },
]

import samples from './samples.json'

export type Sample = { id: string; name: string; blurb: string; text: string; features: Record<string, string> }
/** Single source shared with backend/export_demo.py, which precomputes the offline demo results. */
export const SAMPLES = samples as Sample[]
