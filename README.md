# comfy-helper

A gateway-first FastAPI service for named ComfyUI generation workflows. The API exposes provider-neutral profiles, jobs, and artifacts while keeping ComfyUI graph details inside workflow profiles and provider adapters.

## Current scope

- environment-backed configuration;
- FastAPI application and OpenAPI schema;
- provider abstraction plus a ComfyUI REST adapter;
- generation/job/artifact domain models;
- SQLite job/artifact metadata persistence with filesystem-backed artifact bytes;
- atomic artifact writes with configurable size limits and streamed provider downloads;
- installed-model-compatible `anima-turbo-t2i` profile;
- verified `wai-illustrious-t2i` profile (WAI Illustrious SDXL checkpoint);
- health, provider, profile, generation, job, cancel, SSE progress, and artifact endpoints;
- unit/API tests and verified real Anima + WAI generation paths.

See [docs/architecture.md](docs/architecture.md) for boundaries and decisions. See [docs/end-to-end.md](docs/end-to-end.md) for the Anima run procedure. See [docs/wai-status.md](docs/wai-status.md) for the verified WAI path.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended)
- reachable ComfyUI server; default: `http://10.0.0.180:8188/`

## Run locally

```bash
cp .env.example .env
uv sync --extra dev
uv run comfy-helper
```

The gateway listens on `http://127.0.0.1:8000` by default. Interactive API docs are at `http://127.0.0.1:8000/docs`.

Alternative invocation:

```bash
uv run uvicorn comfy_helper.api:app --host 127.0.0.1 --port 8000
```

## Configuration

Settings use the `COMFY_HELPER_` prefix and can be placed in `.env`.

| Variable | Default | Purpose |
|---|---|---|
| `COMFY_HELPER_HOST` | `127.0.0.1` | Gateway bind address |
| `COMFY_HELPER_PORT` | `8000` | Gateway port |
| `COMFY_HELPER_COMFYUI_URL` | `http://10.0.0.180:8188/` | ComfyUI base URL |
| `COMFY_HELPER_COMFYUI_TIMEOUT_SECONDS` | `10` | Provider HTTP timeout |
| `COMFY_HELPER_ARTIFACT_DIR` | `artifacts` | Directory for gateway-owned output files |
| `COMFY_HELPER_DATABASE_PATH` | `data/comfy-helper.db` | SQLite path for jobs/artifact metadata |
| `COMFY_HELPER_MAX_ARTIFACT_BYTES` | `52428800` | Max downloaded/stored artifact size (50 MiB) |

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Gateway and provider health |
| `GET` | `/api/v1/providers` | Provider health and model inventory |
| `GET` | `/api/v1/workflow-profiles` | Available named profiles |
| `GET` | `/api/v1/workflow-profiles/{id}` | Profile metadata/defaults |
| `POST` | `/api/v1/generations` | Render and enqueue a generation |
| `GET` | `/api/v1/jobs/{id}` | Refresh and return a job |
| `GET` | `/api/v1/jobs/{id}/events` | SSE progress stream until terminal state |
| `POST` | `/api/v1/jobs/{id}/cancel` | Cancel queued/running job |
| `GET` | `/api/v1/jobs/{id}/artifacts` | Return generated artifacts |
| `GET` | `/api/v1/artifacts/{id}` | Retrieve stored artifact bytes |

Example submission:

```bash
curl -sS http://127.0.0.1:8000/api/v1/generations \
  -H 'content-type: application/json' \
  -d '{
    "profile_id": "anima-turbo-t2i",
    "prompt": "masterpiece, best quality, 1girl, blue hair, anime style",
    "width": 1024,
    "height": 1024,
    "seed": 42
  }'
```

## Development

```bash
uv run --extra dev pytest
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

Jobs and artifact metadata are stored in SQLite (`COMFY_HELPER_DATABASE_PATH`). Artifact bytes are stored under `COMFY_HELPER_ARTIFACT_DIR` using temporary files and atomic rename. Restarting the gateway keeps job and artifact lookup as long as the DB and artifact directory remain.
