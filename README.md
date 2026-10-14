# HLRAI

EU AI Act policy-as-code register with a Drafter/Verifier workflow, plus an API and review front end.
Product spec: `SPEC.md`. Handoff and decisions: `HANDOFF.md`. API contract: `openapi/openapi.yaml`.

| Path | What |
|---|---|
| `eu-ai-act-register.yaml`, `.schema.json`, `check_register.py` | Core: register, contract, checker (single implementation of the rules) |
| `workflow/` | Core: Drafter/Verifier pipeline (CLI) |
| `openapi/openapi.yaml` | The one API contract shared by back end and front end |
| `backend/` | FastAPI wrapper over the core; slices S1 (read) and S2 (propose and review) implemented |
| `frontend/` | React + TypeScript; client types are generated from the contract |

## Run (PowerShell)

```powershell
pip install -r backend/requirements.txt
python check_register.py            # expect 80 passed
python workflow\test_pipeline.py    # expect 12 passed
python -m pytest backend -q         # contract-validated API tests

# two terminals
python -m uvicorn backend.app.main:app --port 8000
cd frontend; npm install; npm run dev    # http://localhost:5173

# end to end (starts both servers itself)
cd frontend; npx playwright install chromium; npm run test:e2e
```

When the contract changes: edit `openapi/openapi.yaml`, run `npm run gen:api` in `frontend/`, commit the regenerated `src/api/schema.d.ts`. CI fails if it is stale.

## Models (live runs)

`workflow/workflow_config.json` defaults: drafter `z-ai/glm-5.3`, verifier `meta/muse-glimmer-30b` (two families; the same model for both is refused). Endpoint `https://integrate.api.nvidia.com/v1`.
The key is read only from the environment, never from files or arguments:

```powershell
$env:NVIDIA_API_KEY = "nvapi-..."    # this session only
python workflow\pipeline.py propose --packet packet.json --live
```

The pipeline fixes sampling at temperature 0.1, top_p 1 and a 1500-token cap per call (`workflow_config.json` limits). Per-model settings from the NVIDIA samples (GLM 0.5 / 1024, Muse 1.0 / top_p 0.95 / 8192) are not applied; raise limits only deliberately (HANDOFF section 7, item 5).

## Propose and review (slice S2)

`POST /packets` then `POST /runs` runs the pipeline's `propose` in the background; `GET /runs/{id}` returns the review (diff, quotes, verdicts, flags, budget). Propose never writes the register; approval and commit arrive in S3.

- `HLRAI_MODEL_MODE=live` (default) uses the models you name and needs `NVIDIA_API_KEY`; without it the API answers `503 model_unavailable`.
- `HLRAI_MODEL_MODE=stub` uses scripted models named `stub:draft-supported`, `stub:draft-fabricated`, `stub:draft-nochange` (drafter) and `stub:verify-supported`, `stub:verify-contradicted`, `stub:verify-unverifiable` (verifier). No network, no key. They prove plumbing, not model quality.
- Run and packet records are JSON files under `.workflow-state/api/` (set `HLRAI_STATE` to relocate). Postgres is deferred until there are multi-user writes.

```powershell
$env:HLRAI_MODEL_MODE = "stub"
python -m uvicorn backend.app.main:app --port 8000
```

## Auth

Slice S1 uses a dev identity stub (`HLRAI_DEV_USER`, `HLRAI_DEV_ROLE`; refused when `HLRAI_ENV` is not `dev`). It is not authentication. OIDC arrives with slice S3.
