import type { Allergies, MedicationDetail } from '../types'

export function Medications({ meds, allergies }: { meds: MedicationDetail[]; allergies?: Allergies }) {
  if (!meds.length && !allergies) return null
  return (
    <div>
      {meds.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead><tr className="label"><th className="py-1 pr-3 font-normal">Medication</th><th className="pr-3 font-normal">Dose</th><th className="font-normal">Frequency</th></tr></thead>
            <tbody>{meds.map(m => (
              <tr key={m.name} className="border-t border-slate-100"><td className="py-1.5 pr-3 font-medium">{m.name}</td>
                <td className="pr-3 tabular-nums">{m.dose != null ? `${m.dose} ${m.unit}` : <span className="text-slate-400">not stated</span>}</td>
                <td>{m.frequency ?? <span className="text-slate-400">not stated</span>}</td></tr>))}</tbody>
          </table>
        </div>
      )}
      {allergies && (
        <p className={`mt-2 text-xs ${allergies.status === 'documented' ? 'text-red-700' : 'text-slate-600'}`}>
          <b>Allergies:</b> {allergies.status === 'nkda' ? 'No known drug allergies documented.' : allergies.status === 'documented' ? allergies.items.join(', ') : 'Not documented — confirm with the patient.'}
        </p>
      )}
    </div>
  )
}
