# End-to-end execution and verification

This procedure starts the gateway, submits the installed Anima workflow to the real ComfyUI instance, polls the gateway job, and downloads the gateway-owned artifact.

## Prerequisites

- ComfyUI is reachable at `http://10.0.0.180:8188/`.
- These files are available to ComfyUI:
  - `anima-turbo-v1.0.safetensors`
  - `qwen_3_06b_base.safetensors`
  - `qwen_image_vae.safetensors`
- Python 3.11+ and `uv` are installed locally.

Check ComfyUI before starting:

```bash
curl -fsS http://10.0.0.180:8188/system_stats
curl -fsS http://10.0.0.180:8188/queue
curl -fsS http://10.0.0.180:8188/models/diffusion_models
curl -fsS http://10.0.0.180:8188/models/text_encoders
curl -fsS http://10.0.0.180:8188/models/vae
```

## Start the gateway

From the repository root:

```bash
cp -n .env.example .env
uv sync --extra dev
uv run comfy-helper
```

In another shell, verify both the gateway and provider:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/api/v1/workflow-profiles/anima-turbo-t2i
```

## Submit a real generation

```bash
curl -fsS -X POST http://127.0.0.1:8000/api/v1/generations \
  -H 'content-type: application/json' \
  --data '{
    "profile_id": "anima-turbo-t2i",
    "prompt": "masterpiece, best quality, anime illustration, 1girl, solo, blue hair, golden eyes, white and navy futuristic jacket, standing on a rooftop at sunset, dramatic clouds, detailed city skyline, clean line art, vibrant colors",
    "negative_prompt": "worst quality, low quality, blurry, malformed hands, extra fingers, text, watermark, logo",
    "width": 1024,
    "height": 1024,
    "seed": 20260809,
    "steps": 10,
    "cfg": 1.0
  }'
```

Copy the returned gateway `id` into `JOB_ID`. The private ComfyUI `prompt_id` is intentionally not exposed.

## Poll execution status

```bash
JOB_ID='<gateway-job-id>'
while true; do
  BODY="$(curl -fsS "http://127.0.0.1:8000/api/v1/jobs/$JOB_ID")" || exit 1
  printf '%s\n' "$BODY"
  STATUS="$(printf '%s' "$BODY" | uv run python -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
  case "$STATUS" in
    succeeded) break ;;
    failed|cancelled) exit 1 ;;
  esac
  sleep 2
done
```

The status progresses through `queued` or `running` to `succeeded`. The successful job response contains one or more artifacts with gateway-relative URLs.

## Retrieve and verify the stored artifact

```bash
ARTIFACT_URL="$(printf '%s' "$BODY" | uv run python -c 'import json,sys; print(json.load(sys.stdin)["artifacts"][0]["url"])')"
curl -fsS "http://127.0.0.1:8000$ARTIFACT_URL" -o generated.png
file generated.png
```

Expected `file` output identifies a PNG image with the requested dimensions. The same bytes are stored below:

```text
$COMFY_HELPER_ARTIFACT_DIR/<gateway-job-id>/<artifact-id>.png
```

The artifact list can be queried separately:

```bash
curl -fsS "http://127.0.0.1:8000/api/v1/jobs/$JOB_ID/artifacts"
```

## Verified real run

A real run through the gateway was completed on 2026-08-09 against ComfyUI `0.30.0`:

- gateway job: `41a74088-e65f-462e-af57-e7aab740dedf`
- status: `succeeded`
- artifact: `5cb6a5c5-8036-4c51-b694-4de430c4edc3`
- provider filename: `anima-turbo_00001_.png`
- provider subfolder: `comfy-helper`
- stored size: `1,259,902` bytes
- image: PNG, 1024 × 1024, RGB
- SHA-256: `5e1aad314924e5656b75e86d3625f74139ec670d3cb9d49cfd996c42d6d6f286`

The bytes retrieved through `/api/v1/artifacts/{id}` matched the filesystem-stored bytes exactly. The output was visually checked and was a coherent anime illustration rather than a blank or corrupted image.

## Restart recovery note

After the SQLite persistence slice, job and artifact metadata survive gateway restarts when `COMFY_HELPER_DATABASE_PATH` and `COMFY_HELPER_ARTIFACT_DIR` are preserved. Verify with:

```bash
# after a generation succeeds and the gateway is restarted
curl -fsS "http://127.0.0.1:8000/api/v1/jobs/$JOB_ID"
curl -fsS "http://127.0.0.1:8000/api/v1/artifacts/$ARTIFACT_ID" -o restored.png
```
