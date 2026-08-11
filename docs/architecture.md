# Architecture

## Intent

`comfy-helper` is a gateway, not a second workflow engine. Clients use stable domain resources (workflow profiles, generation jobs, and artifacts); provider adapters translate those resources to ComfyUI's prompt/history/view APIs. ComfyUI remains responsible for graph execution, queueing, and GPU lifecycle.

```text
Client
  │ REST /api/v1
  ▼
FastAPI transport ── health / profiles / generations / jobs / artifacts
  │
  ▼
GenerationService ── orchestration and gateway job state
  │                  │
  │                  └── WorkflowRegistry ── validated, named workflow profiles
  ▼
GenerationProvider (port)
  ▼
ComfyUIProvider (adapter) ── /system_stats /models/* /prompt /history/{id} /queue /view
  ▼
ComfyUI at 10.0.0.180:8188
```

## Boundaries

- **API (`api.py`)**: HTTP validation, response codes, resource routing. It does not know ComfyUI workflow node IDs.
- **Domain (`domain/models.py`)**: provider-neutral generation requests, jobs, statuses, and artifacts.
- **Application service (`services/generation.py`)**: renders a selected profile, submits it, and reconciles provider state into a gateway job.
- **Workflow profiles (`workflows/`)**: named, versionable graph templates plus defaults and parameter bindings. Node-specific knowledge stays here.
- **Provider port (`providers/base.py`)**: the contract required by the application service.
- **ComfyUI adapter (`providers/comfyui.py`)**: HTTP protocol details and translation of ComfyUI history outputs into artifacts.
- **Configuration (`config.py`)**: environment-backed process settings only.

Dependency direction is API → service/domain/ports; the ComfyUI adapter implements the provider port. Domain models do not import FastAPI or ComfyUI types.

## Resource lifecycle

1. A client discovers `/api/v1/workflow-profiles` and selects a profile.
2. `POST /api/v1/generations` validates provider-neutral inputs.
3. `GenerationService` renders a fresh API-format graph and submits it to the provider.
4. The gateway stores a job mapped to ComfyUI's `prompt_id` and returns HTTP 202.
5. `GET /api/v1/jobs/{id}` reconciles completed state from history and queued/running state from the ComfyUI queue.
6. The provider downloads completed outputs from ComfyUI `/view`.
7. `ArtifactStore` writes the bytes under the configured artifact directory using gateway-generated IDs.
8. Clients retrieve stored bytes from `/api/v1/artifacts/{id}` without direct access to ComfyUI.

If a newly submitted prompt is briefly absent from both history and queue, the adapter allows a five-second propagation grace period. After that, or immediately for an unknown prompt, it reports a failed provider job instead of leaving the gateway job queued forever.

## Current persistence and next boundary

Jobs and artifact metadata are persisted in SQLite (`COMFY_HELPER_DATABASE_PATH`). Artifact bytes are streamed from ComfyUI `/view` with a configurable size cap, written through a temporary file, and atomically renamed into `COMFY_HELPER_ARTIFACT_DIR`. Restarting the gateway restores job and artifact lookup from SQLite plus the on-disk files.

## Cancel and progress

- `POST /api/v1/jobs/{id}/cancel` deletes a pending ComfyUI prompt or interrupts a running one, then marks the gateway job `cancelled`.
- Job responses include optional `progress` (`value`, `max`, `node`, `percent`) populated from ComfyUI WebSocket `progress`/`executing` events when available.
- `GET /api/v1/jobs/{id}/events` is an SSE stream that repeatedly emits the refreshed job JSON until a terminal state, then sends `event: done`.

Likely next implementation slices:

- cancellation acknowledgement from ComfyUI history interrupted state edge-cases;
- workflow/profile schema versioning and stronger parameter bindings;
- automatic WAI checkpoint discovery once a checkpoint is installed;
- authentication, quotas, idempotency keys, and multi-provider routing.

## Live environment findings (2026-08-09 / 2026-08-11)

The configured ComfyUI endpoint previously reported:

- Windows, ComfyUI `0.30.0`;
- NVIDIA GeForce RTX 4060 Laptop GPU with 8 GB VRAM;
- diffusion model `anima-turbo-v1.0.safetensors`;
- text encoder `qwen_3_06b_base.safetensors`;
- VAE `qwen_image_vae.safetensors`;
- no checkpoint-format models in `models/checkpoints`.

As of 2026-08-11 the host has:

- Anima diffusion model for `anima-turbo-t2i`
- WAI checkpoint `waiNSFWIllustrious_v150.safetensors` for `wai-illustrious-t2i`

Both profiles have verified real gateway generations. See [wai-status.md](wai-status.md).

The Windows checkout contains an API-format workflow at `user/default/workflows/Anima_Turbo_T2I_api.json`. The registered `anima-turbo-t2i` profile follows that graph and uses only built-in node types. The registered `wai-illustrious-t2i` profile is a standard SDXL checkpoint graph using `waiNSFWIllustrious_v150.safetensors`.

## Decisions

- **Profiles, not arbitrary workflows, are public resources.** Accepting arbitrary graphs would expose custom-node execution and make validation/security unbounded.
- **Provider job IDs stay internal.** Gateway IDs remain stable if storage or provider routing changes later.
- **Polling is the first transport.** It is simple and maps directly to ComfyUI history. Streaming can be additive.
- **Anima and WAI are both verified live profiles.** Anima was first; WAI Illustrious v150 was installed and verified through the gateway on 2026-08-11.
- **SQLite is enough for single-process restart recovery.** No external database service is required for this slice.
