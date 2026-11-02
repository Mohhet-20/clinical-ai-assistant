# Clinical Safety Case

Status: **research prototype, not a medical device.** This document records the hazards identified so far, the controls built into the software, and the test that verifies each control. It follows the structure of ISO 14971 / DCB0129 hazard logs so that the work carries forward if the product is ever taken through a regulated pathway. It is **not** a regulatory submission.

## Intended use

Clarity helps a qualified clinician review a de-identified or synthetic clinical note, report, or image transcription. It extracts findings, computes published clinical scores (NEWS2, qSOFA, eGFR), retrieves reference evidence, shows two research risk-model signals, and drafts possible conditions and next steps **for the clinician to verify**. Users must acknowledge this intended use before entering any data. Every output is advisory, explains its basis, and can be checked against the source record and cited evidence. That is the transparency criterion the FDA uses in its CDS guidance to separate decision support from device software.

**Out of scope:** autonomous diagnosis, triage, or prescribing; emergency use; use by patients; identifiable patient data in any deployment without the controls listed under [Before clinical use](#before-clinical-use).

## Hazard log

| # | Hazard | Cause | Controls | Verified by |
|---|---|---|---|---|
| H1 | Emergency is missed | Warning-sign language not recognised; dangerous vitals not parsed | Urgent-term lexicon with negation handling; vital-sign thresholds for BP >180/120, SBP <90, SpO2 <92%, HR >130 or <40, RR ≥30 or <8, temp ≥40 or <35 °C, glucose ≥400 or <54 mg/dL; urgent action always listed first | `test_urgent_detection`, `test_new_vitals_and_explainable_urgency`, `test_hypoglycaemia_is_urgent` |
| H2 | Urgent flag is not trusted because it is unexplained | Opaque alerting | `urgent_reasons` lists every trigger; the reasons also feed the action rationale and the FHIR `DetectedIssue` | `test_new_vitals_and_explainable_urgency`, `test_fhir_bundle_export` |
| H3 | Negated finding reported as present | "Denies chest pain" read as chest pain | NegEx-style negation triggers, scoped to the clause | `test_negation_and_extraction`, `test_negation_scope` |
| H4 | Present finding dropped | Negation scope runs past "but" or "reports" | Scope terminators (but, however, reports, complains of…) | `test_negation_scope` ("Denies fever but reports cough") |
| H5 | Family history read as patient diagnosis | "Family history of diabetes" | "family history of" acts as a negation trigger for the patient; captured separately as a risk factor | `test_family_history_is_not_reported_as_patient_condition` |
| H6 | Lab-report boilerplate read as patient conditions | Interpretation tables list diseases | Boilerplate stripping before entity extraction | `test_lab_report_parsing_and_boilerplate` |
| H7 | Model output over-trusted | Probability read as a personal risk | Labelled as a "model signal"; caveat on every prediction; model cards with intended use, population, and limitations; holdout sensitivity, specificity, and Brier score shown | `test_model_cards_and_metrics` |
| H8 | Model applied outside its training data | Implausible or unusual inputs | Per-feature training ranges; out-of-range inputs set `reliability: low` with a visible warning | `test_out_of_range_inputs_lower_reliability` |
| H9 | Misleading explanation | Imputed or defaulted values reported as "drivers" | Drivers are limited to values the clinician supplied; assumed Pregnancies=0 is disclosed | `test_imputed_or_assumed_inputs_are_never_drivers` |
| H10 | Wrong or tampered model served | Corrupted or substituted artifact | SHA-256 sidecar verified **before** deserialisation; models trained at image build; version string tied to the training-data hash in every result | `test_tampered_model_artifact_is_not_loaded`, `test_provenance_in_every_result` |
| H11 | Hallucinated LLM content | Generation is ungrounded | LLM limited to the supplied evidence with inline `[id]` citations; patient text marked as untrusted data, not instructions; deterministic rules-mode fallback | `test_image_service_failure_falls_back_to_notes`, rules-mode tests |
| H12 | Cited source is missing | Action cites evidence not in the response | Every cited evidence id is guaranteed present in `evidence` | `test_vitals_feed_diabetes_model_and_differential` |
| H13 | PHI disclosed to a third party | Text sent to the LLM, embeddings, or PubMed | Pattern de-identification on every outbound path; PubMed queried only with recognised clinical vocabulary | `test_no_phi_reaches_the_llm`, `test_pubmed_query_is_redacted`, `test_deidentify_*` |
| H14 | PHI retained by the service | Logs or audit records copy notes | Logs hold method, route, status, and latency only; the audit log stores hashes and structured outcomes; validation errors do not echo input | `test_analysis_is_audited_without_clinical_text`, `test_validation_errors_do_not_echo_input` |
| H15 | Malicious upload | Executable disguised as an image; PDF bomb | Magic-byte sniffing; 12 MiB size cap; PDF page cap | `test_spoofed_file_types_are_rejected`, `test_pdf_page_limit` |
| H16 | Unauthorised use or review tampering | Open API; edited audit log | API keys with clinician and admin roles; production fails closed without keys; SHA-256 hash-chained audit log with verification | `test_auth_*`, `test_admin_routes_need_admin_role`, `test_production_without_keys_refuses_to_start`, `test_audit_chain_detects_tampering` |
| H17 | Partial result displayed after a UI fault | Rendering error | React error boundary replaces the page rather than showing a half-drawn result | manual |
| H18 | Deterioration missed when no single vital is extreme | Several moderately abnormal vitals | NEWS2 (RCP 2017) aggregate scoring: ≥5 or a single 3 prompts urgent review, ≥7 an emergency response. qSOFA ≥2 prompts sepsis assessment. Both appear as urgent reasons and actions | `test_news2_matches_rcp_banding`, `test_news2_thresholds`, `test_qsofa_and_sepsis_action` |
| H19 | Partial score taken as reassurance | Missing vitals produce a low total | Incomplete scores are labelled as a lower bound ("5+") and list the missing parameters | `test_incomplete_news2_is_a_lower_bound_not_reassurance`, UI test |
| H20 | Abbreviated findings missed | "c/o SOB and CP" not recognised | Case-sensitive abbreviation and shorthand expansion before extraction and urgency checks; guards against false matches inside words (CPR, SOBER) | `test_abbreviations_and_attribution`, gold set `abbr-*` |
| H21 | Low SpO2 read as heart rate | "pulse ox 89%" matched the pulse pattern | Pulse pattern excludes "pulse ox", and the SpO2 pattern includes it | `test_pulse_ox_is_saturation_not_heart_rate` |
| H22 | Relative's diagnosis attributed to the patient | "Mother has diabetes" | Relative-attribution negation trigger; captured as Family history | gold set `fam-01` |
| H23 | Resolved or excluded finding reported as current | "Chest pain resolved", "MI ruled out" | Post-negation triggers | gold set `neg-04`, `neg-05` |
| H24 | Instructions in a note manipulate the LLM | Prompt injection in uploaded text | Input screening; the LLM is skipped for that request and the local pipeline still runs | `test_prompt_injection_skips_llm` |
| H25 | LLM output prescribes or doses | Model writes "start metformin 500 mg" | Output guardrail rejects directive language and falls back to rules mode. Citations to sources that were not retrieved are stripped | `test_directive_llm_summary_is_rejected`, `test_unknown_citations_are_stripped`, `test_chat_reply_guardrail` |
| H26 | Stored cases exposed | Database file copied; another user's case opened | Fernet encryption at rest with key rotation; owner-scoped access that returns 404 rather than 403; every view and delete audited; retention purge | `test_case_lifecycle_with_owner_isolation`, `test_case_retention_purge`, `test_key_rotation_keeps_old_cases_readable` |
| H27 | Forged identity | JWT `alg: none`, HS256 key confusion, token for another app, expired token | Asymmetric algorithms only; issuer, audience and expiry required; role mapping required (no role → 403); OIDC refuses to start without an audience | `test_oidc_rejections`, `test_oidc_rejects_alg_none_and_hs256_confusion`, `test_oidc_requires_audience` |
| H28 | Silent quality regression | A code change degrades extraction or urgency | 43-case annotated gold set; `evaluate.py --gate` fails CI below the floors (urgent sensitivity floor = 1.0) | `test_evaluation_gate_passes`, CI step |
| H29 | Septic patient gets no condition suggestion | The differential had no infection or sepsis rule (NEWS2 16 and qSOFA 3 produced an empty list) | Sepsis / serious infection, lower respiratory tract infection and kidney impairment rules, each citing evidence; "confusion" added to the lexicon | gold set `sep-04`, `renal-02`, `neg-11` |
| H30 | Renally contraindicated drug not flagged | Metformin listed with eGFR <30 | Medication-safety action citing the FDA 2016 labelling change | `export_demo.py` sepsis case; reviewed in UI |
| H31 | Clinician mistakes or misunderstands what the NLP read | Opaque extraction | Explain view shows every span with its status and trigger; a test guarantees highlighted spans never contradict extracted findings | `test_annotations_explain_every_decision`, `test_annotations_agree_with_extraction`, `Explain.test.tsx` |
| H32 | Precomputed demo output mistaken for a live analysis | Server asleep at first visit | Demo results are labelled "Offline demo", review buttons that write to the audit trail are disabled, and FHIR export is unavailable until the server is live | `Explain.test.tsx` (offline demo tests) |

## Measured quality

`python backend/evaluate.py` runs the pipeline in rules mode against [backend/eval/gold.jsonl](../backend/eval/gold.jsonl): 43 synthetic notes, with labels written as clinical truth rather than copied from system output. It covers negation, post-negation, relatives, abbreviations, vitals, urgency, NEWS2, eGFR, and the top condition.

| Metric | Current | CI floor |
|---|---|---|
| Entity precision / recall | 1.00 / 1.00 | 0.95 / 0.95 |
| Negation accuracy | 1.00 | 0.95 |
| Urgent sensitivity / specificity | 1.00 / 1.00 | 1.00 / 0.90 |
| Vitals accuracy | 1.00 | 0.95 |
| Top-condition accuracy | 1.00 | 0.90 |
| Score accuracy (NEWS2, eGFR) | 1.00 | 1.00 |

**Read these figures as a regression baseline, not a performance claim.** The set is small and synthetic, and it was written by the developers. Its first version scored 1.00 while missing every common abbreviation; adversarial probing then exposed four real defects (H20 to H23), which are now fixed and included in the set. Real-world accuracy can only be established on an independent set of de-identified notes annotated by clinicians. That is item 1 below.

## Residual risks (accepted for a prototype, open for production)

- **De-identification is pattern- and lexicon-based.** It catches labelled identifiers, common given names, and structured identifiers, but not every free-text name or rare identifier. A validated de-identification service (for example Philter, or Presidio with a clinical NER model) is required before real PHI is processed.
- **The models are small, old cohorts.** Neither is externally validated or recalibrated for any deployment population. `class_weight="balanced"` pushes probabilities toward 50%.
- **The differential is a transparent rule set**, not a validated diagnostic model. Coverage is limited to eight condition groups.
- **The abbreviation lexicon resolves ambiguity toward acute readings** (CP = chest pain, not cerebral palsy). This errs toward over-flagging and needs review for specialty settings.
- **The audit log is a local file.** It detects tampering, but someone with write access can delete it. Production should ship records to WORM storage (for example S3 Object Lock) or a SIEM.
- **The rate limiter is per process.** Multi-replica deployments need a gateway or Redis limiter.
- **Image interpretation** depends on a third-party vision model. Images cannot be redacted before they are sent.

## Before clinical use

1. Run a clinical validation study on the target population: an independent, clinician-annotated set of de-identified notes, with sensitivity and specificity for urgent-flag detection reported against clinician review. Add it to `evaluate.py` as a second gate.
2. Classify under the applicable framework (FDA CDS guidance / SaMD, EU MDR Rule 11, UK MHRA) and set up a quality management system (ISO 13485) and software lifecycle (IEC 62304).
3. Sign a BAA/DPA with any LLM provider, or deploy a model inside the organisation's boundary.
4. Turn on OIDC single sign-on (already implemented) and restrict API keys to service accounts, so every clinical action is attributed to a named person.
5. Use a validated de-identification service and WORM audit storage.
6. Hold a named clinical safety officer review of this hazard log.
