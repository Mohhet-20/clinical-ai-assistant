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

export type Sample = { name: string; text: string; features: Record<string, string> }
export const SAMPLES: Sample[] = [
  {
    name: 'Possible diabetes',
    text: 'Female, 45-year-old. Reports increased thirst, frequent urination and fatigue for 3 weeks, with blurred vision. BMI 33. Fasting glucose 182 mg/dL, HbA1c 8.1%. BP 128/84 mmHg. Family history of diabetes. Not currently on any treatment.',
    features: { DiabetesPedigreeFunction: '0.55', Pregnancies: '2' },
  },
  {
    name: 'Cardiac presentation',
    text: '62-year-old male smoker with hypertension, taking lisinopril and aspirin. Presents with chest pressure radiating to the left arm, shortness of breath and sweating since this morning. BP 168/98 mmHg. Total cholesterol 262 mg/dL.',
    features: { age: '62', sex: '1', cp: '4', trestbps: '168', chol: '262', fbs: '0', restecg: '2', thalach: '112', exang: '1', oldpeak: '2.4', slope: '2', ca: '2', thal: '7' },
  },
]
