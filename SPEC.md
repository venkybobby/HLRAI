# HLRAI Product Spec v0.1: Human-Led Responsible AI Governance Platform

Status: draft for approval by Venky R (sole approver). Date: 2026-10-14.
Basis: repo state at v0.2 (register, schema, checker 80/80, pipeline tests 12/12), `HANDOFF.md`, `migration-status.md`.

## 0. Requirement (confirmed by the owner)

The goal is the **EU AI Act policy-as-code register with a Drafter/Verifier workflow**. That system already exists as files (register YAML, JSON Schema, checker, pipeline). This spec therefore treats it as the product and describes what is needed to finish it and to put layers around it:

- **Core (must come first):** register + schema + checker + Drafter/Verifier pipeline, extended beyond the single pilot obligation, proven on a live model, and covering the 63 unmigrated rows over time.
- **Layers around the core:** API, database for workflow state and audit, review front end, auth, deployment. These wrap the core; they never re-implement its rules.

Problem: law can be split into what code can check (A), what is measured against an approved threshold (B), and what needs a named human (C, A+C). Today the system is a YAML file plus a CLI. A reviewer cannot browse obligations, see why an evaluation is blocked, review a model-drafted patch next to its source quotes, or export evidence for an auditor without reading YAML and JSON.

Primary user: governance lead / approver (Venky R today). Secondary: legal counsel (verifies readings), control owners (ml_lead etc.), auditor (read only).

## 1. Research findings

Method: internal analysis of the repository. External market and legal research could not be done in this environment (outbound access is limited by the proxy), so nothing below claims knowledge of competitor products or of the Official Journal text.

Findings that drive the design:

1. The core value is the gate, not the dashboard. `verification.status == verified_primary` is the only way an automated conclusion is produced. All 5 obligations are `verified_secondary` or `unverified`, so all 4 evaluations derive `blocked_unverified_interpretation`. A UI that hides this would mislead; the UI must make "blocked, and why, and who can unblock it" the first thing seen.
2. Four decisions are already separated (applicability, evidence validity, control result, assurance), plus `completion` kept apart from `operating_permission`. The data model and screens must keep them as separate fields.
3. The workflow is already a state machine: propose -> validate (max 2 repairs) -> verify -> human review -> approve (bound to patch hash, source hashes, base revision) -> idempotent commit with receipt. Statuses: ready_for_review, needs_revision, no_change, escalated, verifier_invalid, budget_exceeded. Only ready_for_review is approvable. This maps directly to a review queue.
4. Only 6 of 69 register rows are migrated; 63 are not. Row migration is the largest body of work and is currently manual.
5. Known weak points stated in HANDOFF section 7: approver is a name check, not authentication; no live model run has happened; a date change in a patch can break expected evaluation outcomes; reasoning models can exhaust the 1500-token cap; cloud workspace cannot reach NVIDIA.
6. The workflow is hard-scoped to one obligation: `workflow_config.json` has `scope.obligation = OBL-ART50-2` and `allowed_paths` listing only that obligation and two controls. Covering the other four obligations, and later the 63 rows, needs per-obligation scope, not a global one.
7. Unverified legal items (Art 6(1a)-(1c), Art 111(2) public-authority date, Art 73 periods) are human tasks outside the workflow and must be tracked, not forgotten.

## 2. Feature list

Priority: M = must (v1), S = should (v1.x), C = could (later), W = won't (explicitly out).

### 2.1 Register
- F1 (M) Browse and search obligations, controls, evaluations, retention items, migration index; filter by actor, category (A/B/A+C/C), verification status.
- F2 (M) Obligation detail: legal source, trigger, duty, effective dates and transitions, exceptions, verification block, linked controls, linked evaluations.
- F3 (M) Verification banner and "blocked reason" on every view where an automated conclusion would otherwise appear.
- F4 (M) Revision history: sha256 revision list, diff between any two revisions, receipt links.
- F5 (S) Migration board: the 69 rows by register and migration state, with the "not yet migrated" list.

### 2.0 Core completion (before any UI)
- F27 (M) Per-obligation scope in config: `allowed_paths` and limits keyed by obligation id, so the pipeline can run on OBL-ART4A, OBL-ART53-1A, OBL-ART53-1C and OBL-ART73 without editing code.
- F28 (M) Live smoke test and one live propose with genuine Art 50(2) text (core lane, section 6.2); result recorded as a receipt.
- F29 (S) Row-migration assistant: draft a structured record from one of the 63 register rows using the same Drafter/Verifier path, never writing `verification.status`.
- F30 (S) CI workflow running `check_register.py` (80) and `workflow/test_pipeline.py` (12).

### 2.2 Verification (human act)
- F6 (M) Verification queue listing every obligation below `verified_primary` and the open legal items from HANDOFF section 3.
- F7 (M) Verification action: a named human with a legal-reviewer role records reviewer, `verified_at`, primary sources and source version; the system then re-derives dependent evaluations. Never available to a model or to the workflow.
- F8 (S) Demotion: any change to an obligation's `trigger`, `duty`, `effective` or `exceptions` after verification resets status to `verified_secondary` until re-verified.

### 2.3 Drafter/Verifier workflow
- F9 (M) Create a packet (obligation id plus sources with ids and text), subject to the 12,000-char limit.
- F10 (M) Run propose with chosen drafter and verifier models; same model refused unless explicitly allowed; show budget used against limits.
- F11 (M) Review screen: patch ops as a diff; for each op the source id, locator and quote shown in context; verifier verdict (supported / contradicted / unverifiable); deterministic flags (`binding_upgrade`, `date_change`, `same_model`).
- F12 (M) Approve: authenticated approver acknowledges every flag and types the 8+ character patch-hash prefix; commit rechecks hash, source hashes, base revision, schema and checker; atomic write; history copy; receipt.
- F13 (M) Reject / request revision with reason. Replay of an approved commit returns `already_committed`.
- F14 (S) Crash recovery view for intent files left by an interrupted commit.

### 2.4 Evaluations
- F15 (M) Record an evaluation for a system, obligation and control: the four decisions, evidence references, `as_of`, law version.
- F16 (M) Server-side `derive()` and `forbidden()` (checker F1-F9) on save; show "now" versus "if every reading were verified" side by side, as `migration-status.md` does.
- F17 (S) Evidence attachment (file or URL) with sha256, provenance and freshness check.
- F18 (S) Exemption workflow: approved `not_applicable` with approver, expiry, forced reassessment on relevant change. Never counted as satisfied.
- F19 (C) Incident clock: awareness time versus ticket creation time, late reports stay `closed_late`.

### 2.5 Reporting and audit
- F20 (M) Coverage and pass-rate report using the existing denominator rules (approved exemptions leave the denominator, late reports count in the denominator but not as satisfied).
- F21 (M) Append-only audit log of every state change, hash-chained.
- F22 (S) Export: register as YAML (byte-identical to canonical), evaluation pack as PDF/CSV for an auditor.
- F23 (C) Retention schedule view with `needs_legal_decision` items.

### 2.6 Platform
- F24 (M) Authentication (OIDC) and roles: viewer, control_owner, legal_reviewer, approver, admin.
- F25 (M) Model configuration screen reading `workflow_config.json` values; API key from environment only, never stored or displayed.
- F26 (W) Excluded: SARO and Assurance Mesh (parked per HANDOFF); automatic raising of verification status; any model-set completion, permission or threshold; multi-tenant SaaS.

## 3. Pressure test

Each row attacks a feature or assumption, states the result, and records the change made to the spec.

| # | Attack | Verdict | Change |
|---|---|---|---|
| 1 | The UI shows a green "compliant" tile somewhere (executive instinct). | Violates the gate; with every evaluation blocked it would be false. | No pass/fail tile without verification; default tile reads "Blocked: N of M readings unverified". F3 made Must. |
| 2 | Database as source of truth conflicts with sha256-of-bytes revisions, ruamel comment preservation and git history. Two sources of truth will drift. | Real risk. A single approver and one register do not justify the cost. | v1 keeps the YAML file in git canonical behind a `RegisterStore` interface; Postgres holds workflow state, users, audit and indexes only. Swap later if multi-user editing demands it. |
| 3 | Name-check approval is not authentication (known limit 2). A web app makes it reachable by others. | Blocker for any deployment beyond localhost. | F24 Must. Approver identity comes from OIDC subject; the config `approvers` list maps to OIDC identities. Approval still needs the typed patch-hash prefix. |
| 4 | Roles: can an admin raise `verified_primary`? | Would defeat the gate. | Only `legal_reviewer` with a named human can verify (F7); admin cannot; database CHECK constraint requires reviewer, `verified_at` and sources for `verified_primary`. |
| 5 | Prompt injection through source text (test t3 covers an injected instruction). | Handled in the pipeline by path allow-list and replace-only ops; a UI must not weaken it. | Source text is rendered as inert text (no HTML, no links followed); packet size capped; allowed paths stay in config, not editable from the UI by non-admins. |
| 6 | No live model run has happened; tests prove plumbing, not quality. Building a UI around an unproven drafter is premature. | Valid, but it does not block parallel work. | The core lane runs F28 (live smoke test on the user's machine; NVIDIA is unreachable from this cloud environment) while the front end builds the review screen against stub-model fixtures and the contract. No live demo before F28. |
| 7 | Reasoning models exhaust the 1500-token cap and truncated JSON is unrecoverable. | Real. | Run result shows `budget_exceeded` clearly; raising `max_tokens_per_call` is an admin config change with an audit entry, not a UI slider on the run form. |
| 8 | Concurrent edits: two proposals against the same base revision. | Pipeline rechecks base revision at commit. | Second commit fails with "base revision changed"; UI offers re-propose. Add a unique constraint on one in-flight commit per register. |
| 9 | A patch that changes a date can make stored evaluations' expected outcomes wrong, and the checker then rejects it (limit 3). | Real; blocks commits with no guidance. | F11 shows "evaluations affected" from the checker output and tells the human which expected values must be updated first. |
| 10 | Report numbers mislead if approved exemptions or late reports are counted wrongly. | Rules exist and are tested. | F20 reuses `check_register.py` logic by import; no re-implementation in the frontend. |
| 11 | Real system data and incident data in the database may be personal or confidential. All current data is fictional. | Out of scope now, in scope the day real data arrives. | v1 labels the instance `pilot`, refuses evidence uploads flagged as personal data, and states that real data needs a DPIA before use. |
| 12 | Legal facts in the register are secondary-source. The app could look authoritative. | Real reputational risk. | Persistent footer: "Not legal advice. Readings unverified against the Official Journal unless marked verified_primary." Unverified Art 6(1a)-(1c), 111(2), 73 items appear in the F6 queue. |
| 13 | Scope creep to 69 rows at once. | Row migration is judgment work. | v1 stays scoped to the 5 existing obligations; F5 only tracks the rest. |
| 14 | Audit log tampering by a database admin. | Possible. | Hash chain (each row stores the previous hash) plus nightly export of the chain head to the git repo; detects, does not prevent. |
| 15 | Single approver is a bus-factor of one and a separation-of-duties gap (the approver also verifies). | Acceptable for a personal pilot, not for an organisation. | Documented; roles are separate in the data model so a second person can be added without a schema change. |

Result: 15 attacks, 0 reasons to change the core decisions; 11 concrete changes folded into the features and architecture below.

## 4. Architecture

```
Browser (React SPA)
   | HTTPS, OIDC session cookie
FastAPI service (Python 3.11+)
   |-- domain/    check_register.py (derive, forbidden), pipeline.py (propose, approve, commit) imported as libraries
   |-- RegisterStore (file-backed YAML in git; interface allows DB later)
   |-- LLMGateway (OpenAI-compatible client, Budget/Metered, no hardcoded model names)
   |-- Worker (in-process task queue for propose runs)
   |-- Postgres: users, runs, reviews, approvals, receipts index, evaluations index, audit chain
   |-- Object storage (local disk v1): packets, review JSON, evidence files, receipts
```

Principle: the existing Python modules stay the single implementation of the rules. The API wraps them; it does not copy them.

### 4.1 Frontend
- React 18 + TypeScript + Vite; TanStack Query; React Router; a plain component library (no design-system dependency in v1).
- Screens: Overview (blocked summary, coverage), Register (list and detail), Verification queue, Workflow (packets, runs, review, approve), Evaluations (list, record, derive view), Reports, Audit log, Settings (models, budgets read-only for non-admins).
- Rules enforced in the UI as well as server: Approve button disabled until every flag is acknowledged and the hash prefix matches; blocked states cannot be dismissed; source text rendered as plain text only.
- Accessibility: WCAG 2.1 AA, keyboard-complete review screen, colour never the sole carrier of state.
- Tests: Vitest for logic, Playwright against a stub-model backend for the review-and-approve path.

### 4.2 Backend API (REST, JSON, OpenAPI generated)
- `GET /register`, `/obligations/{id}`, `/controls/{id}`, `/revisions`, `/revisions/{sha}/diff/{sha}`
- `POST /packets`, `GET /packets/{id}`
- `POST /runs` {packet_id, drafter, verifier, allow_same_model}; `GET /runs/{id}` (status, budget, review)
- `POST /reviews/{id}/approve` {patch_hash_prefix, acknowledged_flags}; `POST /reviews/{id}/reject`
- `POST /approvals/{id}/commit` (idempotent; replay returns `already_committed`)
- `POST /obligations/{id}/verify` (legal_reviewer only)
- `GET/POST /evaluations`, `POST /evaluations/{id}/derive`
- `GET /reports/coverage`, `GET /audit`, `GET /export/register.yaml`
- Errors use problem+json with a stable `code` (`base_revision_changed`, `unacknowledged_flag`, `verification_required`, ...).
- Long operations (propose) run as background tasks; the client polls `GET /runs/{id}`.
- Server-side invariants (not trusting the client): replace-only ops on allowed paths; no write to `verification.status`, evaluations, completion or permission from the workflow; approver identity from the session.

### 4.3 Database (Postgres 15+)
Canonical register stays in the YAML file (section 6, row 2). Tables:
- `users(id, oidc_sub, name, role)`; `role` in viewer, control_owner, legal_reviewer, approver, admin.
- `packets(id, obligation_id, sources jsonb, source_hashes jsonb, created_by, created_at)`
- `runs(id, packet_id, base_revision, drafter, verifier, status, budget jsonb, review_path, created_at)`; `status` is the enum of the six review statuses plus `running`.
- `approvals(id, run_id, approver_id, patch_hash, acknowledged_flags, created_at)`; unique `(run_id)`.
- `commits(id, approval_id, before_revision, after_revision, receipt_path, status, recovered bool)`; partial unique index allowing one `in_flight` commit.
- `verifications(id, obligation_id, reviewer_id, verified_at, sources jsonb, source_version, created_at)`; CHECK that reviewer, `verified_at` and sources are non-null.
- `evaluations(id, system_id, obligation_id, control_id, as_of, decisions jsonb, recorded jsonb, evidence_ids)`; derived outcome is computed, not stored as truth.
- `evidence(id, sha256, uri, provenance, collected_at, flagged_personal_data)`
- `audit(seq, ts, actor_id, action, entity, payload jsonb, prev_hash, hash)`; insert-only via a role without UPDATE/DELETE.
- Migrations with Alembic; every enum mirrors `eu-ai-act-register.schema.json`.

### 4.4 Other layers
- **Auth**: OIDC provider of choice (Entra ID, Google or Keycloak); sessions are HTTP-only cookies; CSRF token on mutating calls.
- **LLM gateway**: NVIDIA NIM OpenAI-compatible endpoint (`https://integrate.api.nvidia.com/v1`) as configured; key read from `NVIDIA_API_KEY` env only; model names supplied at run time; per-run and per-day spend ceilings in addition to the existing per-run budget.
- **Secrets**: environment or the host secret store; none in the repo, DB or logs; logs redact `Authorization`.
- **Observability**: structured JSON logs with run id and revision; metrics for run status counts, tokens per run, commit failures; alert on any `commit` status `in_flight` older than 10 minutes.
- **Deployment**: one container for API+worker, one for static frontend, managed Postgres. Must run where NVIDIA is reachable (not the cloud workspace, which gets a proxy 403). Environments: local, pilot.
- **CI**: `pip install -r requirements.txt`; `check_register.py` (expect 80), `workflow/test_pipeline.py` (expect 12), API tests, frontend tests, schema/OpenAPI drift check. There is currently no CI workflow in the repo.
- **Backup**: nightly Postgres dump; the register is already in git; audit chain head committed to git daily.

## 5. Non-functional requirements
- Integrity: no automated conclusion without `verified_primary`; enforced in domain code, DB constraints and UI (defence in depth).
- Reproducibility: any past evaluation can be re-derived from the stored revision and evaluation record.
- Performance: register under 1 MB; all read endpoints under 300 ms p95; a propose run is bounded by 4 calls and 4,000 completion tokens.
- Security: OWASP ASVS L2 as the target for the pilot; dependency scanning in CI.
- Privacy: fictional data only in v1 (section 3, row 11).

## 6. Delivery plan: front end and back end in parallel

Decision (owner): drive front end and back end in parallel so there are no gaps between them. This replaces the earlier "core first, UI later" ordering. The core (register, checker, pipeline) is a third lane that both depend on.

### 6.1 Gap-prevention rules
1. **One contract.** `openapi/openapi.yaml` is the only description of the API. Register record shapes are `$ref`'d from `eu-ai-act-register.schema.json`, never copied. A change to either file is a contract change and needs both lanes' review.
2. **Generated, not hand-written, glue.** Front end generates its TypeScript client from the contract; back end generates request/response models (or validates against the contract in tests). Neither side writes types by hand.
3. **Mock first.** The front end builds against a mock server generated from the contract (for example Prism) with fixtures taken from the real register and the 12 pipeline test scenarios. The back end ships a stub-model mode so the same fixtures are reachable from the real server.
4. **Contract tests in CI.** Back end: every response in tests is validated against the contract (schemathesis or equivalent). Front end: mock and real server must both pass the same Playwright specs.
5. **Error codes are part of the contract.** Every `Problem.code` has a front-end handler and a back-end test; the traceability matrix below lists them.
6. **Definition of done is a vertical slice.** A feature is done only when contract, back end, front end and one end-to-end test (stub models) all exist.
7. **Core stays the single rule implementation.** The back end imports `check_register.py` and `workflow/pipeline.py`; neither lane re-implements derive(), forbidden() or the approval checks.

### 6.2 Lanes

| Lane | Owns | Starts with |
|---|---|---|
| Contract | `openapi/openapi.yaml`, error-code list, fixtures | Merge this contract (v0.1, 19 paths, validates) |
| Core | F27 per-obligation scope, F28 live smoke test, F30 CI, F29 row migration | Per-obligation `allowed_paths`; CI running both suites |
| Back end | FastAPI wrapper, Postgres, auth, audit chain, `RegisterStore`, async runs | Read endpoints on the real register, then workflow endpoints on stub models |
| Front end | React app, generated client, mock server, Playwright | Overview + register screens on the mock, then review/approve screen |

### 6.3 Vertical slices (each slice is built by all lanes at once)

| Slice | Features | Endpoints | Screens | End-to-end test |
|---|---|---|---|---|
| S1 Read the register | F1-F4, F21 (read) | getRegister, getObligation, getControl, listRevisions, diffRevisions, getMe | Overview, Register list, Obligation detail, Revisions | Blocked banner appears for all 5 obligations |
| S2 Propose and review | F9-F11, F25 | createPacket, getPacket, startRun, listRuns, getRun | Packet form, Run list, Review (diff, quotes, verdicts, flags) | Stub run reaches `ready_for_review`; fabricated quote shows rejected |
| S3 Approve and commit | F12-F14, F24 | approveReview, rejectReview, commitApproval, exportRegister | Approve dialog, Commit result, Receipt | Replay returns `already_committed`; stale base returns `base_revision_changed` |
| S4 Verify | F6-F8 | getVerificationQueue, verifyObligation | Verification queue, Verify dialog | Non-reviewer gets 403; verifying re-derives evaluations |
| S5 Evaluate and report | F15-F16, F20 | listEvaluations, createEvaluation, getCoverage | Evaluations (now vs if verified), Reports | Pass rate is null while unverified; matches checker after verification |
| S6 Audit | F21 | listAudit | Audit log | Chain verifies; tampered row is flagged |
| S7 Later | F17-F19, F22-F23 | extend contract first | Evidence, exemptions, retention | Defined when scheduled |

Slices S1 to S3 are the first release candidate; S4 to S6 follow. The core lane's F27/F28/F30 land alongside S1 and must be done before S2 is run against a live model.

### 6.4 Traceability (contract error codes to behaviour)

| `Problem.code` | Raised by | Front-end handling | Slice |
|---|---|---|---|
| verification_required | any automated conclusion without `verified_primary` | Show blocked reason, link to verification queue | S1 |
| base_revision_changed | commitApproval | Banner, offer re-propose | S3 |
| unacknowledged_flag | approveReview | Highlight unticked flags | S3 |
| patch_hash_mismatch | approveReview | Field error on hash prefix | S3 |
| source_hash_mismatch | commitApproval | Block, show which source changed | S3 |
| not_approvable | approveReview | Hide approve for non-`ready_for_review` | S3 |
| forbidden_role | verifyObligation, approveReview | 403 page with required role | S3, S4 |
| checker_rejected / schema_invalid | commitApproval, createEvaluation | List violations; show affected evaluations | S3, S5 |
| budget_exceeded / same_model_refused | startRun | Show budget used; explain refusal | S2 |
| already_committed | commitApproval (replay) | Show original receipt | S3 |

### 6.5 Parallel-delivery risks
- **Contract churn.** Mitigation: freeze v0.1 for S1-S3; additive changes only (new optional fields, new endpoints) until S3 ships.
- **Mock drift from real behaviour.** Mitigation: both servers run the same Playwright suite in CI; fixtures come from the real register and test scenarios.
- **Core change breaks the contract** (for example a new obligation field). Mitigation: contract references the register schema, so a schema change fails contract tests on the back end first.
- **Live model behaviour differs from stubs** (truncation, slow runs, odd verdicts). Mitigation: F28 before any live demo; the review screen handles `budget_exceeded` and `verifier_invalid` from day one.

## 7. Open questions for the approver
1. (Resolved) Goal is the register plus Drafter/Verifier workflow, with front end and back end delivered in parallel (section 6).
2. Which OIDC provider will be used, and where will the app be hosted (it must reach NVIDIA)?
3. Should a second person (legal reviewer) be added in v1, or does the single-approver pilot continue?
4. Which two model families for drafter and verifier (the supplied IDs are unverified)?
5. Is a React + FastAPI + Postgres stack acceptable, given the Windows/PowerShell development machine?

## 8. Risks not resolved by this spec
- Model quality is untested until F28 completes.
- Legal readings stay secondary-source until a human checks the Official Journal.
- The audit chain detects tampering by a database admin; it does not prevent it.
