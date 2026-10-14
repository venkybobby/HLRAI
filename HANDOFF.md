# Handoff: EU AI Act policy-as-code register + Drafter/Verifier workflow

Date of state: 2026-10-07. Owner and sole approver: Venky R.
Use this file as the first message of a new Claude chat, or as CLAUDE.md context for Claude Code in the project folder.

## 0. Working preferences (apply silently)
- Lead with the answer, no preamble or filler. Stay in scope. Ask rather than assume. Simplest solution first.
- Show only changed code, not full files. Confirm before destructive actions.
- End every coding task with: FILES CHANGED / NOT TOUCHED / CONCERNS.
- Integrated delivery only: single repo github.com/venkybobby/HLRAI for this project. "Execute" or "proceed" means act now.
- Say "I don't know" rather than guess. Windows/PowerShell with Miniconda on the user's machine.
- Never put API keys in files, chats or arguments. Key lives in `NVIDIA_API_KEY` env var only.

## 1. Purpose and context
Venky is a senior technology leader (Accenture Technology Strategy Lead; job search for Forward Deployed *leadership* roles). This project is a worked example of "human-led responsible AI governance": split what law can be executed as code from what needs human judgment, and record rule -> evidence -> human attestation. SARO / Assurance Mesh are parked until the role search lands.

Core idea: policy-as-code works for deterministic checks (A) and measured-vs-approved-threshold checks (B). Judgment (C) and checkable-artifact-plus-human-attestation (A+C) need a named human. Nothing is concluded automatically unless the legal reading itself was verified against a primary source by a named human.

## 2. Decisions already made (do not reopen without reason)
- Four separate decisions: applicability, evidence validity, control result, assurance. `completion` (where the obligation stands) is kept apart from `operating_permission` (may the system keep operating).
- Approved `not_applicable` is never counted as satisfied. Late incident reports stay `closed_late`. Restricted operation never marks an obligation fully satisfied.
- **Verification gate:** an obligation yields an automated conclusion only if `verification.status == verified_primary` (needs named `reviewer`, `verified_at`, sources). All current obligations are `verified_secondary` or `unverified`, so every stored evaluation derives `blocked_unverified_interpretation`.
- Three records: obligations, controls (each requirement has its own `legal_status`: binding_law / voluntary_code / internal_policy), evaluations.
- Models never set `verified_primary`, never set completion or permission, never invent thresholds. Raising verification status is a manual human act outside the workflow.
- Revisions are sha256 of register bytes; `history/` holds previous copies; `receipts/` hold JSON receipts. The register files are also version-controlled in the HLRAI repo.

## 3. Legal facts used (as of Oct 2026; secondary-source, NOT verified against the Official Journal)
- Omnibus Reg (EU) 2026/1744: OJ 24 Jul 2026, in force 27 Jul 2026.
- Annex III high-risk applies 2 Dec 2027; Annex I 2 Aug 2028. Art 50 transparency live 2 Aug 2026; Art 50(2) legacy marking grace to 2 Dec 2026. New Art 5 prohibitions from 2 Dec 2026.
- Art 4 reworded; Art 4a replaced old 10(5); Art 53(2) exemption covers only 53(1)(a),(b); Art 111 legacy GPAI to 2 Aug 2027.
- EN 18286 approved June 2026 (some sources say 12 July), NEN 31 July; not OJ-cited.
- **Unverified by me:** Art 6(1a)-(1c); Art 111(2) public-authority date (a reviewer claimed 2 Aug 2030); Art 73 reporting periods. Treat as open until a human checks the OJ / consolidated text.

## 4. Artifacts
- Claude Doc "EU AI Act Policy-as-Code Register" (id 990a4b77-0fca-4c0a-93d2-dc047de135a5): ~69 rows across 4 registers, decision model, adversarial pilot (12 scenarios), coverage 26/69 (38%) automatable after approvals. 6 rows migrated to structured records (R-17, R-33, R-51, R-52, R-62, R-64).
- Project folder `/home/claude/eu-ai-act-register/` (delivered as `eu-ai-act-workflow.tgz`):
  - `eu-ai-act-register.yaml` v0.2: 5 obligations (OBL-ART50-2, OBL-ART4A, OBL-ART53-1A, OBL-ART53-1C, OBL-ART73), 6 controls, 4 evaluations (EVAL-0001..0004), retention schedule, migration index (69 rows). All systems/thresholds/incidents are FICTIONAL pilot data.
  - `eu-ai-act-register.schema.json`: JSON Schema 2020-12 contract with conditionals.
  - `check_register.py`: derive()/forbidden() F1-F9, negative fixtures. **80/80 pass.** CLI: `--register FILE --no-report`.
  - `migration-status.md`: generated.
  - `workflow/pipeline.py`, `models.py`, `prompts.py`, `workflow_config.json`, `test_pipeline.py` (12 tests, all pass, stub models only).

## 5. Workflow design (scope: OBL-ART50-2 and controls CTL-MARK-PATHS, CTL-MARK-DETECT)
Drafter (isolated call) -> deterministic validation, up to 2 repairs -> Verifier (fresh context) -> human review -> approval bound to patch hash + source hashes + base revision -> idempotent commit + receipt.
- Only `replace` ops on allowed paths (config). `verification.status`, evaluations, completion etc. are rejected.
- Each op needs support: source_id, locator that appears verbatim in the source, quote at/after the locator within 2000 chars. Fabricated quotes are rejected.
- Verifier verdicts: supported / contradicted / unverifiable. Must cover every op; "supported" without a valid quote is downgraded to unverifiable.
- Deterministic flags: `binding_upgrade` (requirement newly binding_law), `date_change` (effective.*), `same_model`. Approval must acknowledge every flag.
- Review statuses: ready_for_review, needs_revision, no_change, escalated, verifier_invalid, budget_exceeded. Only ready_for_review is approvable.
- Approval: name must be in config `approvers` (["Venky R"]) plus typed 8+ char patch-hash prefix. Commit rechecks hash, source hashes, base revision, re-validates (schema + checker), preserves YAML comments via ruamel, atomic write, history copy, receipt; replay returns `already_committed`; crash after write recovers via intent file.
- Budget (minimum): max 4 calls/run, 1500 tokens/call, 4000 completion tokens/run, 12000 source chars, 6 ops, temperature 0.1.
- Live models: NVIDIA NIM OpenAI-compatible, base_url `https://integrate.api.nvidia.com/v1`. Default models are set in `workflow_config.json` (drafter `z-ai/glm-5.3`, verifier `meta/muse-glimmer-30b`); `--drafter-model` / `--verifier-model` override them. Same model for both is refused unless `--allow-same-model`.
- Candidate models the user supplied (IDs unverified by me): `z-ai/glm-5.3`, `z-ai/glm-5.3-flash`, `google/gemma-4-31b-it`, `meta/muse-glimmer-30b`. Prefer two different families, e.g. Gemma drafter + Meta verifier.

## 6. How to run
```powershell
pip install openai ruamel.yaml jsonschema
python check_register.py                      # expect 80 passed
python workflow\test_pipeline.py              # expect 12 passed
$env:NVIDIA_API_KEY = "nvapi-..."             # session only
python workflow\pipeline.py propose --packet packet.json --live --drafter-model google/gemma-4-31b-it --verifier-model meta/muse-glimmer-30b
python workflow\pipeline.py approve --review <review dir> --reviewer "Venky R" --patch-hash <8+ chars> --acknowledge <flags>
python workflow\pipeline.py commit --approval <approval file>
```
`packet.json`: `{"obligation_id":"OBL-ART50-2","sources":[{"source_id":"S1","text":"<real Art 50(2) text>"}]}`.
State is written to `.workflow-state/` (reviews, approvals, receipts, history, intents).

## 7. Known limits and open items
1. The Cowork/cloud workspace cannot reach NVIDIA (proxy 403). Live runs must happen on Venky's machine. No live run has been done; tests prove plumbing and guard rails, not model quality.
2. Approver is a name check, not authentication.
3. A patch that changes a date can break the evaluations' expected outcomes; checker then rejects the patch until a human updates them.
4. Next real step: run the smoke test per model, then one live propose with genuine Art 50(2) text from the Official Journal / consolidated text, and paste back `review.json` if status is escalated / verifier_invalid / budget_exceeded.
5. Reasoning-heavy models may exhaust the 1500-token cap; `extract_json` strips `<think>` blocks but cannot recover truncated JSON. Raise `max_tokens_per_call` only deliberately.
6. Human tasks outside the workflow: verify the unverified provisions in section 3 against primary text, then (and only then) raise `verification.status` with reviewer and date; decide retention items flagged `needs_legal_decision`.
7. Possible extensions, only if asked: more obligations in scope, migrate more of the 69 rows, extend schema for new fields.

## 8. Paste-in starter for a new chat
> Continue the EU AI Act policy-as-code project described in the attached HANDOFF.md. The register, schema, checker (80/80) and Drafter/Verifier workflow with stub tests (12/12) exist; no live model run has happened. I will run live calls on my machine with NVIDIA_API_KEY and paste back review.json. Follow my working preferences in section 0. First, ask me for whatever you need from my live run; do not assume model names or reopen the decisions in section 2.
