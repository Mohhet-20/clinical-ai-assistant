# Security

## Reporting a vulnerability

Please report suspected vulnerabilities privately to the maintainer (balakamohit@gmail.com) rather than in a public issue. Include steps to reproduce and the affected version (`GET /v1/health` → `version`). Expect an acknowledgement within 5 working days.

**Do not include real patient data in any report.**

## Security controls

| Area | Control | Where |
|---|---|---|
| Authentication | **OIDC single sign-on**: JWTs verified against the IdP's JWKS (discovered from the issuer); asymmetric algorithms only (`none` and HS* rejected); `iss`, `aud`, `exp` and `sub` required, with 30 s leeway; the UI uses authorization-code + PKCE (S256) with no client secret and session-only token storage. **API keys** for service accounts: constant-time comparison, logged only as SHA-256 fingerprints | `backend/app/security.py`, `frontend/src/oidc.ts` |
| Authorisation | Two roles, *clinician* and *admin*, mapped from IdP roles (`OIDC_ROLE_CLAIM`) or key lists. A token with no Clarity role gets 403. `ENVIRONMENT=production` refuses to start without auth; `OIDC_ISSUER` refuses to start without `OIDC_AUDIENCE` | `security.py`, `main.py` lifespan |
| Data at rest | Case history is off by default. When enabled it requires a Fernet key and fails closed without one. Records use AES-128-CBC + HMAC-SHA256 with key rotation (`MultiFernet`). Only non-identifying index metadata is stored in clear. Access is owner-scoped and returns 404 rather than 403, so case IDs can't be probed. Every view and delete is audited; retention purge runs on startup and on every write | `backend/app/cases.py` |
| LLM safety | Prompt-injection screening skips the LLM for that request. Outputs with prescribing or dosing directives are rejected; citations to unretrieved sources are stripped | `backend/app/guardrails.py` |
| Abuse limits | Per-client sliding-window rate limit (`429` + `Retry-After`); 12 MiB upload cap; 30,000-character text cap; PDF page cap | `security.py`, `main.py` |
| Input handling | Upload type taken from magic bytes, not the client header or extension; Pydantic schemas with bounded lengths; finite-number checks on model features; XML entity declarations rejected | `main.py`, `rag.py` |
| Privacy | PHI de-identification before every LLM, embedding, and PubMed call; PubMed is queried with clinical vocabulary only; no persistence of notes or files | `backend/app/phi.py`, `agent.py` |
| Logging | Structured JSON with request id, method, route template, status, and latency only. No bodies; exception *types* only, never messages | `backend/app/observability.py` |
| Audit | Append-only JSONL, SHA-256 hash chain, `GET /v1/audit/verify` integrity check; stores input hashes and outcomes, not clinical text | `backend/app/audit.py` |
| Supply chain | Model artifacts integrity-checked before deserialisation; models built into the image; `pip-audit` and `npm audit` in CI; ruff with bandit (`S`) rules; Trivy image scan (fails on fixable critical/high); CycloneDX SBOM; Dependabot for pip, npm, Docker and Actions | `ml.py`, `.github/` |
| Transport and browser | HSTS, `nosniff`, `X-Frame-Options: DENY`, a strict CSP on API responses and on the UI (`connect-src` limited to the configured API), `Cache-Control: no-store` on API responses, CORS limited to configured origins with no credentials | `main.py`, `frontend/nginx.conf` |
| Containers | API: non-root UID 10001. UI: unprivileged nginx (UID 101, port 8080). Read-only root filesystem, all capabilities dropped, `no-new-privileges`, seccomp `RuntimeDefault`, health checks. Kubernetes manifests enforce the *restricted* Pod Security Standard and default-deny NetworkPolicies | `Dockerfile`s, `docker-compose.yml`, `deploy/kubernetes/` |

## Known limitations

- API keys are shared secrets. With SSO enabled, use them only for service accounts.
- The rate limiter, audit chain head and SQLite case store are per process or per volume, so the Kubernetes API runs as one replica. Scaling out needs a gateway limiter, centralised WORM audit storage and a shared encrypted database.
- The SSO access token lives in session storage, which script running in the page could read. The strict CSP (`script-src 'self'`) is the mitigation. A backend-for-frontend with HttpOnly cookies removes the exposure entirely.
- De-identification is pattern-based and not guaranteed complete. See [docs/SAFETY_CASE.md](docs/SAFETY_CASE.md).
- TLS termination is expected at the platform edge (Render, Vercel, or an ingress controller).
