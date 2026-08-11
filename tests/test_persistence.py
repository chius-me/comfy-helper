from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from comfy_helper.api import create_app
from comfy_helper.config import Settings
from comfy_helper.domain.models import Artifact
from comfy_helper.providers.base import ProviderArtifactContent
from comfy_helper.services.artifacts import ArtifactStore, ArtifactTooLargeError
from comfy_helper.services.repository import SqliteJobRepository
from tests.fakes import FakeProvider


def test_artifact_store_writes_atomically_and_rejects_oversized_payload(
    tmp_path,
) -> None:
    store = ArtifactStore(tmp_path, max_bytes=8)
    job_id = uuid4()
    artifact = Artifact(filename="ok.png")

    stored = store.store(
        job_id,
        artifact,
        ProviderArtifactContent(content=b"12345678", content_type="image/png"),
    )
    assert stored.local_path is not None
    path = Path(stored.local_path)
    assert path.exists()
    assert path.read_bytes() == b"12345678"
    assert not list(path.parent.glob("*.partial"))

    with pytest.raises(ArtifactTooLargeError):
        store.store(
            job_id,
            Artifact(filename="too-big.png"),
            ProviderArtifactContent(content=b"123456789", content_type="image/png"),
        )


@pytest.mark.asyncio
async def test_jobs_and_artifacts_survive_app_restart(tmp_path) -> None:
    db_path = tmp_path / "jobs.db"
    artifact_dir = tmp_path / "artifacts"
    settings = Settings(database_path=db_path, artifact_dir=artifact_dir)
    provider = FakeProvider()

    first_app = create_app(settings=settings, provider=provider)
    transport = httpx.ASGITransport(app=first_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/generations",
            json={"profile_id": "anima-turbo-t2i", "prompt": "persist me"},
        )
        job_id = created.json()["id"]
        refreshed = await client.get(f"/api/v1/jobs/{job_id}")
        artifact = refreshed.json()["artifacts"][0]
        artifact_id = artifact["id"]
        first_bytes = (await client.get(artifact["url"])).content

    # New process-equivalent app reuses the same durable store and files.
    second_provider = FakeProvider()
    second_app = create_app(
        settings=settings,
        provider=second_provider,
        repository=SqliteJobRepository(db_path),
    )
    transport = httpx.ASGITransport(app=second_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        restored_job = await client.get(f"/api/v1/jobs/{job_id}")
        restored_artifact = await client.get(f"/api/v1/artifacts/{artifact_id}")

    assert restored_job.status_code == 200
    assert restored_job.json()["status"] == "succeeded"
    assert restored_job.json()["artifacts"][0]["id"] == artifact_id
    assert restored_artifact.status_code == 200
    assert restored_artifact.content == first_bytes == b"generated-image"
