import json

import httpx
import pytest

from comfy_helper.domain.models import Artifact, JobStatus
from comfy_helper.providers.comfyui import ComfyUIProvider


@pytest.mark.asyncio
async def test_comfyui_provider_submits_workflow_and_reads_artifacts() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/prompt":
            seen.update(json.loads(request.content))
            return httpx.Response(200, json={"prompt_id": "prompt-123", "number": 7})
        if request.url.path == "/history/prompt-123":
            return httpx.Response(
                200,
                json={
                    "prompt-123": {
                        "status": {"status_str": "success", "completed": True},
                        "outputs": {
                            "9": {
                                "images": [
                                    {
                                        "filename": "image.png",
                                        "subfolder": "comfy-helper",
                                        "type": "output",
                                    }
                                ]
                            }
                        },
                    }
                },
            )
        raise AssertionError(f"unexpected path: {request.url.path}")

    client = httpx.AsyncClient(
        base_url="http://comfy/", transport=httpx.MockTransport(handler)
    )
    provider = ComfyUIProvider("http://comfy/", client=client)

    submission = await provider.submit(
        {"1": {"class_type": "Example", "inputs": {}}}, "client-1"
    )
    snapshot = await provider.get_job(submission.id)

    assert seen["client_id"] == "client-1"
    assert submission.id == "prompt-123"
    assert submission.queue_number == 7
    assert snapshot.status == JobStatus.succeeded
    assert snapshot.artifacts[0].filename == "image.png"
    assert "view?" in snapshot.artifacts[0].source_url
    await provider.close()


@pytest.mark.asyncio
async def test_comfyui_provider_downloads_artifact_bytes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/view"
        assert request.url.params["filename"] == "image.png"
        assert request.url.params["subfolder"] == "comfy-helper"
        assert request.url.params["type"] == "output"
        return httpx.Response(
            200,
            content=b"png-bytes",
            headers={"content-type": "image/png; charset=binary"},
        )

    client = httpx.AsyncClient(
        base_url="http://comfy/", transport=httpx.MockTransport(handler)
    )
    provider = ComfyUIProvider("http://comfy/", client=client)
    artifact = Artifact(
        filename="image.png", subfolder="comfy-helper", storage_type="output"
    )

    content = await provider.download_artifact(artifact)

    assert content.content == b"png-bytes"
    assert content.content_type == "image/png"
    await provider.close()


@pytest.mark.asyncio
async def test_comfyui_provider_reports_installed_model_inventory() -> None:
    models = {
        "/models/checkpoints": [],
        "/models/diffusion_models": ["anima-turbo-v1.0.safetensors"],
        "/models/vae": ["qwen_image_vae.safetensors"],
        "/models/text_encoders": ["qwen_3_06b_base.safetensors"],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=models[request.url.path])

    client = httpx.AsyncClient(
        base_url="http://comfy/", transport=httpx.MockTransport(handler)
    )
    provider = ComfyUIProvider("http://comfy/", client=client)

    assert await provider.model_inventory() == {
        "checkpoints": [],
        "diffusion_models": ["anima-turbo-v1.0.safetensors"],
        "vae": ["qwen_image_vae.safetensors"],
        "text_encoders": ["qwen_3_06b_base.safetensors"],
    }
    await provider.close()


@pytest.mark.asyncio
async def test_comfyui_provider_reports_running_prompt_from_queue() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/history/prompt-123":
            return httpx.Response(200, json={})
        if request.url.path == "/queue":
            return httpx.Response(
                200,
                json={
                    "queue_running": [[7, "prompt-123", {}, {}, []]],
                    "queue_pending": [],
                },
            )
        raise AssertionError(f"unexpected path: {request.url.path}")

    client = httpx.AsyncClient(
        base_url="http://comfy/", transport=httpx.MockTransport(handler)
    )
    provider = ComfyUIProvider("http://comfy/", client=client)

    snapshot = await provider.get_job("prompt-123")

    assert snapshot.status == JobStatus.running
    await provider.close()


@pytest.mark.asyncio
async def test_comfyui_provider_reports_pending_prompt_from_queue() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/history/prompt-123":
            return httpx.Response(200, json={})
        if request.url.path == "/queue":
            return httpx.Response(
                200,
                json={
                    "queue_running": [],
                    "queue_pending": [[7, "prompt-123", {}, {}, []]],
                },
            )
        raise AssertionError(f"unexpected path: {request.url.path}")

    client = httpx.AsyncClient(
        base_url="http://comfy/", transport=httpx.MockTransport(handler)
    )
    provider = ComfyUIProvider("http://comfy/", client=client)

    snapshot = await provider.get_job("prompt-123")

    assert snapshot.status == JobStatus.queued
    await provider.close()


@pytest.mark.asyncio
async def test_comfyui_provider_fails_unknown_prompt_absent_from_queue_and_history() -> (
    None
):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/history/lost-prompt":
            return httpx.Response(200, json={})
        if request.url.path == "/queue":
            return httpx.Response(200, json={"queue_running": [], "queue_pending": []})
        raise AssertionError(f"unexpected path: {request.url.path}")

    client = httpx.AsyncClient(
        base_url="http://comfy/", transport=httpx.MockTransport(handler)
    )
    provider = ComfyUIProvider("http://comfy/", client=client)

    snapshot = await provider.get_job("lost-prompt")

    assert snapshot.status == JobStatus.failed
    assert snapshot.error == "ComfyUI prompt is absent from history and queue"
    await provider.close()


@pytest.mark.asyncio
async def test_comfyui_provider_fails_submitted_prompt_missing_beyond_grace() -> None:
    now = [100.0]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "lost-prompt", "number": 1})
        if request.url.path == "/history/lost-prompt":
            return httpx.Response(200, json={})
        if request.url.path == "/queue":
            return httpx.Response(200, json={"queue_running": [], "queue_pending": []})
        raise AssertionError(f"unexpected path: {request.url.path}")

    client = httpx.AsyncClient(
        base_url="http://comfy/", transport=httpx.MockTransport(handler)
    )
    provider = ComfyUIProvider(
        "http://comfy/",
        client=client,
        missing_prompt_grace_seconds=5,
        clock=lambda: now[0],
    )
    submission = await provider.submit({}, "client-1")

    recent = await provider.get_job(submission.id)
    now[0] += 6
    expired = await provider.get_job(submission.id)

    assert recent.status == JobStatus.queued
    assert expired.status == JobStatus.failed
    assert expired.error == "ComfyUI prompt is absent from history and queue"
    await provider.close()


@pytest.mark.asyncio
async def test_comfyui_provider_surfaces_execution_error_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "prompt-123": {
                    "status": {
                        "status_str": "error",
                        "completed": True,
                        "messages": [
                            ["execution_start", {"prompt_id": "prompt-123"}],
                            [
                                "execution_error",
                                {
                                    "prompt_id": "prompt-123",
                                    "exception_type": "RuntimeError",
                                    "exception_message": "CUDA out of memory",
                                },
                            ],
                        ],
                    },
                    "outputs": {},
                }
            },
        )

    client = httpx.AsyncClient(
        base_url="http://comfy/", transport=httpx.MockTransport(handler)
    )
    provider = ComfyUIProvider("http://comfy/", client=client)

    snapshot = await provider.get_job("prompt-123")

    assert snapshot.status == JobStatus.failed
    assert snapshot.error == "RuntimeError: CUDA out of memory"
    await provider.close()


@pytest.mark.asyncio
async def test_comfyui_provider_cancels_pending_prompt() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/queue" and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "queue_running": [],
                    "queue_pending": [[1, "prompt-123", {}, {}, []]],
                },
            )
        if request.url.path == "/queue" and request.method == "POST":
            seen["delete"] = json.loads(request.content)
            return httpx.Response(200, json={})
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    client = httpx.AsyncClient(
        base_url="http://comfy/", transport=httpx.MockTransport(handler)
    )
    provider = ComfyUIProvider("http://comfy/", client=client)
    await provider.cancel("prompt-123")
    assert seen["delete"] == {"delete": ["prompt-123"]}
    await provider.close()
