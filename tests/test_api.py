import pytest

from comfy_helper.api import create_app
from comfy_helper.config import Settings
from tests.fakes import FakeProvider


@pytest.mark.asyncio
async def test_health_reports_gateway_and_provider_status(client_and_provider) -> None:
    client, _ = client_and_provider
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "comfy-helper",
        "provider": {
            "name": "comfyui",
            "status": "ok",
            "detail": None,
            "version": "test",
        },
    }


@pytest.mark.asyncio
async def test_core_resources_list_provider_and_workflow_profile(
    client_and_provider,
) -> None:
    client, _ = client_and_provider

    providers = await client.get("/api/v1/providers")
    profiles = await client.get("/api/v1/workflow-profiles")
    profile = await client.get("/api/v1/workflow-profiles/anima-turbo-t2i")

    assert providers.json()[0]["name"] == "comfyui"
    assert providers.json()[0]["models"]["diffusion_models"] == [
        "anima-turbo-v1.0.safetensors"
    ]
    profile_ids = {item["id"] for item in profiles.json()}
    assert profile_ids == {"anima-turbo-t2i", "wai-illustrious-t2i"}
    assert profile.json()["model_family"] == "anima"
    assert "template" not in profile.json()
    wai = await client.get("/api/v1/workflow-profiles/wai-illustrious-t2i")
    assert wai.json()["model_family"] == "wai"


def test_openapi_hides_provider_job_id(tmp_path) -> None:
    settings = Settings(
        artifact_dir=tmp_path / "artifacts", database_path=tmp_path / "openapi.db"
    )
    properties = create_app(settings=settings, provider=FakeProvider()).openapi()[
        "components"
    ]["schemas"]["GenerationJob"]["properties"]

    assert "provider_job_id" not in properties


@pytest.mark.asyncio
async def test_generation_submission_creates_refreshable_job(
    client_and_provider,
) -> None:
    client, provider = client_and_provider

    created = await client.post(
        "/api/v1/generations",
        json={
            "profile_id": "anima-turbo-t2i",
            "prompt": "1girl, blue hair",
            "seed": 123,
        },
    )
    assert created.status_code == 202
    job = created.json()
    assert job["status"] == "queued"
    assert "provider_job_id" not in job
    assert provider.submitted_workflow["4"]["inputs"]["text"] == "1girl, blue hair"

    refreshed = await client.get(f"/api/v1/jobs/{job['id']}")
    artifacts = await client.get(f"/api/v1/jobs/{job['id']}/artifacts")

    assert refreshed.json()["status"] == "succeeded"
    assert "provider_job_id" not in refreshed.json()
    assert artifacts.json()[0]["filename"] == "generated.png"


@pytest.mark.asyncio
async def test_stored_artifact_is_retrievable_through_gateway(
    client_and_provider,
) -> None:
    client, _ = client_and_provider
    created = await client.post(
        "/api/v1/generations",
        json={"profile_id": "anima-turbo-t2i", "prompt": "artifact test"},
    )
    refreshed = await client.get(f"/api/v1/jobs/{created.json()['id']}")

    artifact = refreshed.json()["artifacts"][0]
    response = await client.get(artifact["url"])

    assert artifact["url"] == f"/api/v1/artifacts/{artifact['id']}"
    assert response.status_code == 200
    assert response.content == b"generated-image"
    assert response.headers["content-type"] == "image/png"
