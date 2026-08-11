# WAI profile status

## Intent

`wai-illustrious-t2i` is a gateway workflow profile for WAI Illustrious-family SDXL checkpoints. It uses a standard ComfyUI API graph:

- `CheckpointLoaderSimple`
- positive/negative `CLIPTextEncode`
- `EmptyLatentImage`
- `KSampler` (`euler_ancestral`, `normal`)
- `VAEDecode`
- `SaveImage`

Default checkpoint name:

```text
waiNSFWIllustrious_v150.safetensors
```

Defaults target portrait anime generation: `832x1216`, `28` steps, `CFG 5.0`.

## Install path used by this host

Windows ComfyUI checkpoint path:

```text
C:\Chius\repo\github\ComfyUI\models\checkpoints\waiNSFWIllustrious_v150.safetensors
```

Source:

```text
https://huggingface.co/IbarakiDouji/WAI-NSFW-illustrious-SDXL/resolve/main/waiNSFWIllustrious_v150.safetensors
```

Size: **6,938,040,682 bytes (~6.46 GiB)**.

Note: the Windows host could not reach Hugging Face directly. Download on the Linux gateway host, then `scp` to Windows.

## Verified inventory

```bash
curl -fsS http://10.0.0.180:8188/models/checkpoints
# ["waiNSFWIllustrious_v150.safetensors"]
```

## Verified real generation (2026-08-11)

Gateway job:

```text
41556f61-7ea0-41a4-97c2-20830b3ec62e
```

Artifact:

```text
2928c40b-eceb-4a71-a865-b174906854ea
```

Stored at:

```text
artifacts/41556f61-7ea0-41a4-97c2-20830b3ec62e/2928c40b-eceb-4a71-a865-b174906854ea.png
```

Request:

- profile: `wai-illustrious-t2i`
- size: `832x1216`
- seed: `20260811`
- steps: `16`
- cfg: `5.0`

Result:

- status: `succeeded`
- PNG `832x1216` RGB
- size: `1,401,761` bytes
- SHA-256: `6d2f0c29ba58901084db144f05633ce2a4988cf9ef439206f774fe9828a70265`
- gateway download matched stored bytes
- progress reached `16/16` (`percent: 100.0`) via provider progress tracking
- visual check: coherent anime girl on a rooftop at sunset

Reproduce:

```bash
curl -fsS -X POST http://127.0.0.1:8000/api/v1/generations \
  -H 'content-type: application/json' \
  --data '{
    "profile_id": "wai-illustrious-t2i",
    "prompt": "masterpiece, best quality, anime illustration, 1girl, solo, blue hair, golden eyes, white jacket, standing on rooftop at sunset, dramatic clouds, city skyline",
    "negative_prompt": "worst quality, low quality, bad anatomy, bad hands, text, watermark, blurry",
    "width": 832,
    "height": 1216,
    "seed": 20260811,
    "steps": 16,
    "cfg": 5.0
  }'

# optional progress stream
curl -N "http://127.0.0.1:8000/api/v1/jobs/$JOB_ID/events"

# poll / download
curl -fsS "http://127.0.0.1:8000/api/v1/jobs/$JOB_ID"
curl -fsS "http://127.0.0.1:8000/api/v1/artifacts/$ARTIFACT_ID" -o wai.png
```

Cancel example:

```bash
curl -fsS -X POST "http://127.0.0.1:8000/api/v1/jobs/$JOB_ID/cancel"
```

## Notes

- Anima remains the previously verified live path.
- WAI is now also verified on this host with the v150 checkpoint.
- On an 8 GB laptop GPU, moderate resolution/steps reduce OOM risk.
